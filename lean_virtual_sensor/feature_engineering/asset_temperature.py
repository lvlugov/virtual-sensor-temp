"""Asset thermal state, wetness, and Active CUI Hours.

Per-asset CUI feature pipeline in five steps, plus an end-to-end driver:

    Step 1  Skin temperature from a 1-D radial heat balance (internal film,
            insulation, external film):
                T_skin = T_process - k * (T_process - T_ambient)
                k         = R_inside / (R_inside + R_ins + R_ambient)
                R_inside  = 1 / (2 * pi * r_pipe_inner  * h_internal)
                R_ins     = ln(r_outer_total / r_pipe_outer) / (2 * pi * lambda)
                R_ambient = 1 / (2 * pi * r_outer_total * h_external)

    Step 2  NACE SP0198-2010 Figure 1 damage factor f(T_skin), two variants:
                f_closed(T_skin)   linear fit to the "Closed System" line
                f_open(T_skin)     PCHIP through the "Open System" digitised points
            Both return 0 outside the active band [nace_t_low_c, nace_t_high_c].

    Step 3  Surface dew point via Magnus, plus a piecewise wetness factor:
                T_dew = b * gamma / (a - gamma)
                gamma = ln(RH / 100) + a * T_ambient / (b + T_ambient)
                w(T_skin, T_dew) = 1 below T_dew, 0 above T_dew + band,
                                   linear in between.

    Step 4  Hourly damage score, multiplicative AND of "hot enough" and
            "wet enough":
                hour_score(t) = f(T_skin(t)) * w(T_skin(t), T_dew(t))

    Step 5  Active CUI Hours, raw sum over the trailing ACH window:
                ACH = sum of hour_score(t)
            Window length comes from ``asset_temperature.ach_window_days``
            in config (default 90).

End-to-end entry point :func:`compute_ach_for_asset` takes an asset mapping
(the raw inventory row, synthetic-data field names), an hourly ``weather_df``,
an hourly ``process_history_df``, and two dates;
it slices both DataFrames to the trailing ACH window itself, joins on
``datetime``, and chains Steps 1-5 to one ACH value.

Material constants (insulation thermal conductivity, Magnus coefficients,
NACE damage-curve calibration) and the default film coefficients are read
from the ``asset_temperature`` section of ``config.yaml`` via
:mod:`lean_virtual_sensor.config`.
"""

from __future__ import annotations

import math
from typing import Iterable

import numpy as np
import pandas as pd
from scipy.interpolate import PchipInterpolator

from lean_virtual_sensor.config import load_section
from lean_virtual_sensor.feature_engineering.system_flag_feature import is_open_system


CONFIG_SECTION = "asset_temperature"
REQUIRED_KEYS = (
    "insulation_lambda_w_per_mk",
    "default_h_external_w_per_m2k",
    "default_h_internal_w_per_m2k",
    "magnus_a",
    "magnus_b",
    "nace_t_low_c",
    "nace_t_high_c",
    "nace_slope_closed",
    "nace_open_t_points_c",
    "nace_open_r_points",
    "wetness_transition_band_c",
    "ach_window_days",
)

# ====================================== Step 1: Surface temperature ======================================


def _film_resistance(radius_m: float, h: float) -> float:
    """Convective film thermal resistance per unit length: 1 / (2π·r·h)."""
    return 1 / (2 * math.pi * radius_m * h)


def _insulation_resistance(
    r_inner_m: float, r_outer_m: float, lambda_w_per_mk: float
) -> float:
    """Radial conductive resistance of an insulation annulus per unit length:
    ln(r_outer / r_inner) / (2π·λ).
    """
    return math.log(r_outer_m / r_inner_m) / (2 * math.pi * lambda_w_per_mk)


def compute_k(
    insulation_type: str,
    insulation_thickness_mm: float,
    pipe_diameter_mm: float,
    wall_thickness_mm: float,
    h_internal: float | None = None,
    h_external: float | None = None,
) -> float:
    """Compute the temperature-attenuation factor k from the 1-D radial heat balance.

        T_skin    = T_process - k * (T_process - T_ambient)
        k         = R_inside / (R_inside + R_ins + R_ambient)
        R_inside  = 1 / (2 * pi * r_pipe_inner  * h_internal)
        R_ins     = ln(r_outer_total / r_pipe_outer) / (2 * pi * lambda)
        R_ambient = 1 / (2 * pi * r_outer_total * h_external)

    The bore radius is derived from the recorded component OD and the original
    (furnished) wall thickness: r_pipe_inner = (pipe_diameter − 2·wall_thickness) / 2.
    Steel itself contributes negligible thermal resistance (λ_steel ≈ 1000·λ_insulation),
    so the metal wall is not modelled as its own series resistance.

    Args:
        insulation_type: Insulation material identifier. Must be a key in the
            ``asset_temperature.insulation_lambda_w_per_mk`` config table
            (case-insensitive).
        insulation_thickness_mm: Insulation jacket thickness in mm.
        pipe_diameter_mm: Pipe outer diameter in mm (the recorded component
            diameter; also the inner diameter of the insulation).
        wall_thickness_mm: Original/furnished metal wall thickness in mm,
            used to derive the bore radius.
        h_internal: Internal heat transfer coefficient in W/m²·K. Varies
            strongly by service: ~1000 for liquid, ~50 for low-velocity gas.
            If ``None``, uses ``asset_temperature.default_h_internal_w_per_m2k``
            from config.
        h_external: External convection coefficient in W/m²·K. If ``None``, uses
            ``asset_temperature.default_h_external_w_per_m2k`` from config.
            Typical values: 10 (still air), 15 (light wind), 25 (windy).

    Returns:
        k as a dimensionless float in (0, 1). Low k → good insulation and/or
        good internal film, T_skin ≈ T_process. High k → poor insulation
        and/or poor internal film, T_skin pulled toward T_ambient.

    Raises:
        ValueError: If ``insulation_type`` is not in the config table, if any
            geometry dimension is non-positive, or if ``wall_thickness_mm``
            leaves no bore (≥ ``pipe_diameter_mm / 2``).
    """
    if insulation_thickness_mm <= 0:
        raise ValueError(
            f"insulation_thickness_mm must be > 0, got {insulation_thickness_mm}"
        )
    if pipe_diameter_mm <= 0:
        raise ValueError(f"pipe_diameter_mm must be > 0, got {pipe_diameter_mm}")
    if wall_thickness_mm <= 0:
        raise ValueError(f"wall_thickness_mm must be > 0, got {wall_thickness_mm}")
    if wall_thickness_mm >= pipe_diameter_mm / 2:
        raise ValueError(
            f"wall_thickness_mm ({wall_thickness_mm}) leaves no bore: "
            f"must be < pipe_diameter_mm / 2 ({pipe_diameter_mm / 2})."
        )

    cfg = load_section(CONFIG_SECTION, REQUIRED_KEYS)
    lambda_table: dict[str, float] = cfg["insulation_lambda_w_per_mk"]
    if h_internal is None:
        h_internal = float(cfg["default_h_internal_w_per_m2k"])
    if h_external is None:
        h_external = float(cfg["default_h_external_w_per_m2k"])

    key = insulation_type.upper()
    if key not in lambda_table:
        raise ValueError(
            f"Unknown insulation type: {key!r}. "
            f"Expected one of {sorted(lambda_table)}."
        )
    lambda_ins = float(lambda_table[key])

    r_pipe_outer = (pipe_diameter_mm / 2) / 1000
    r_pipe_inner = ((pipe_diameter_mm - 2 * wall_thickness_mm) / 2) / 1000
    r_outer_total = r_pipe_outer + (insulation_thickness_mm / 1000)

    r_inside = _film_resistance(r_pipe_inner, h_internal)
    r_ins = _insulation_resistance(r_pipe_outer, r_outer_total, lambda_ins)
    r_ext = _film_resistance(r_outer_total, h_external)

    return r_inside / (r_inside + r_ins + r_ext)


def compute_t_skin(t_process: float, t_ambient: float, k: float) -> float:
    """Compute the steel surface temperature under the insulation.

        T_skin = T_process - k * (T_process - T_ambient)

    Args:
        t_process: Process fluid temperature in °C (from historian).
        t_ambient: Ambient air temperature in °C (from weather API).
        k: Attenuation factor from :func:`compute_k`.

    Returns:
        T_skin in °C. Sits between T_process (k → 0) and T_ambient (k → 1).
    """
    return t_process - k * (t_process - t_ambient)


# ====================================== Step 2: NACE SP0198 damage factor ======================================


def compute_f_closed(t_skin: float) -> float:
    """Closed-system damage factor from the NACE SP0198 Fig 1 closed-system line.

        f_closed(T_skin) = nace_slope_closed * (T_skin - nace_t_low_c)
                          for nace_t_low_c ≤ T_skin ≤ nace_t_high_c
                        = 0  otherwise

    Linear fit through (nace_t_low_c, 0); the closed-system line in NACE Fig 1
    is essentially straight across the active band, peaking at the dryness
    boundary because the trapped water film keeps oxygen available.

    Args:
        t_skin: Steel surface temperature in °C.

    Returns:
        Damage factor in mm/y. Zero outside the active band.
    """
    cfg = load_section(CONFIG_SECTION, REQUIRED_KEYS)
    t_low = float(cfg["nace_t_low_c"])
    t_high = float(cfg["nace_t_high_c"])
    if t_skin < t_low or t_skin > t_high:
        return 0.0
    return float(cfg["nace_slope_closed"]) * (t_skin - t_low)


def compute_f_open(t_skin: float) -> float:
    """Open-system damage factor from the NACE SP0198 Fig 1 open-system curve.

    PCHIP (monotonic piecewise cubic Hermite) interpolation through the six
    NACE-digitised points held in ``nace_open_t_points_c`` /
    ``nace_open_r_points``. Outside that range — but inside the active band
    [nace_t_low_c, nace_t_high_c] — extrapolates linearly using the slope of
    the nearest boundary segment, clipped at zero.

    The asymmetric rise-peak-fall shape arises because reaction rate rises
    with temperature while dissolved oxygen escapes as water heats up; their
    product peaks in the middle (≈ 0.42 at 80 °C in the digitised data).

    Args:
        t_skin: Steel surface temperature in °C.

    Returns:
        Damage factor in mm/y. Zero outside the active band.
    """
    cfg = load_section(CONFIG_SECTION, REQUIRED_KEYS)
    t_low = float(cfg["nace_t_low_c"])
    t_high = float(cfg["nace_t_high_c"])
    if t_skin < t_low or t_skin > t_high:
        return 0.0
    t_fit = np.asarray(cfg["nace_open_t_points_c"], dtype=float)
    r_fit = np.asarray(cfg["nace_open_r_points"], dtype=float)
    if t_skin < t_fit[0]:
        slope_lo = (r_fit[1] - r_fit[0]) / (t_fit[1] - t_fit[0])
        return max(0.0, float(r_fit[0] + slope_lo * (t_skin - t_fit[0])))
    if t_skin > t_fit[-1]:
        slope_hi = (r_fit[-1] - r_fit[-2]) / (t_fit[-1] - t_fit[-2])
        return max(0.0, float(r_fit[-1] + slope_hi * (t_skin - t_fit[-1])))
    return float(PchipInterpolator(t_fit, r_fit)(t_skin))


# ====================================== Step 3: Dew point, wetness factor ======================================


def compute_t_dew(t_ambient: float, rh_percent: float) -> float:
    """Compute the surface dew point via the Magnus formula.

    The dew point is set by the absolute water content of the air, which is
    conserved as air migrates through the insulation system, so the surface
    dew point equals the external dew point.

    Args:
        t_ambient: Ambient air temperature in °C.
        rh_percent: External relative humidity (0-100, not 0-1).

    Returns:
        T_dew in °C.

    Raises:
        ValueError: If ``rh_percent`` is outside ``(0, 100]``. Above 100 is
            physically impossible and a likely bad-data sentinel; at or
            below 0 the Magnus log term is undefined.
    """
    if not 0 < rh_percent <= 100:
        raise ValueError(
            f"rh_percent must be in (0, 100], got {rh_percent}"
        )
    cfg = load_section(CONFIG_SECTION, REQUIRED_KEYS)
    a = float(cfg["magnus_a"])
    b = float(cfg["magnus_b"])
    gamma = math.log(rh_percent / 100) + a * t_ambient / (b + t_ambient)
    return b * gamma / (a - gamma)


def compute_wetness(t_skin: float, t_dew: float) -> float:
    """Compute the wetness factor w(T_skin, T_dew).

        w = 1.0                                  if T_skin ≤ T_dew
            (T_dew + band − T_skin) / band       if T_dew < T_skin ≤ T_dew + band
            0                                    if T_skin > T_dew + band

    where ``band = wetness_transition_band_c`` from config.

    Scores whether water is likely on the steel surface from atmospheric
    condensation. At or below the dew point, the surface is condensing
    (w = 1). Well above the dew point the surface is dry (w = 0). Within the
    transition band immediately above T_dew, partial condensation is possible
    and w drops smoothly from 1 to 0.

    Args:
        t_skin: Steel surface temperature in °C (from :func:`compute_t_skin`).
        t_dew: Surface dew point in °C (from :func:`compute_t_dew`).

    Returns:
        Wetness factor in [0, 1].
    """
    cfg = load_section(CONFIG_SECTION, REQUIRED_KEYS)
    band = float(cfg["wetness_transition_band_c"])
    if t_skin <= t_dew:
        return 1.0
    if t_skin >= t_dew + band:
        return 0.0
    return (t_dew + band - t_skin) / band


# ====================================== Step 4: Hourly damage score ======================================


def compute_hour_score(f_t_skin: float, wetness: float) -> float:
    """Multiply the NACE damage factor by the wetness factor to get one hour's score.

        hour_score = f(T_skin) * w(T_skin, T_dew)

    Multiplication is the AND logic: damage accumulates only when both
    conditions hold. Hot but dry (w = 0) → 0. Wet but cold/too-hot
    (f = 0) → 0. Hot and wet → positive.

    Args:
        f_t_skin: NACE damage factor in mm/y from :func:`compute_f_closed`
            or :func:`compute_f_open` (open/closed chosen per asset).
        wetness: Wetness factor in [0, 1] from :func:`compute_wetness`.

    Returns:
        Per-hour score (units of f, scaled by the dimensionless w).
    """
    return f_t_skin * wetness


# ====================================== Step 5: Active CUI Hours ======================================


def compute_ach(hour_scores: Iterable[float]) -> float:
    """Sum per-hour scores over a 90-day window to get Active CUI Hours.

        ACH_90d = Σ hour_score(t)  over hours t in last 90 days

    The caller is responsible for slicing the hourly series to the 90-day
    window (2160 samples) — windowing depends on the caller's timestamp
    format, which this function does not take. Theoretical ceiling is 2160
    (every hour scoring 1.0 on both factors) but real assets sit well below.

    Args:
        hour_scores: Iterable of per-hour scores from
            :func:`compute_hour_score`, covering the last 90 days.

    Returns:
        Raw ACH_90d, in (mm/y)·hour units (sum of f·w over the window).
    """
    return sum(hour_scores)


# ====================================== Pipeline: tie Steps 1-5 together ======================================


def compute_ach_for_asset(
    insulation_material: str,
    insulation_thickness: float,
    component_diameter: float,
    furnished_thickness: float,
    insulation_condition: str,
    cladding_integrity: str,
    weather_df: pd.DataFrame,
    process_history_df: pd.DataFrame,
    last_inspection_date: pd.Timestamp,
    today: pd.Timestamp,
    h_internal: float | None = None,
    h_external: float | None = None,
) -> float:
    """Run Steps 1-5 end-to-end for one asset over its trailing ACH window.

        Step 1: k = compute_k(asset)                            — constant per asset
                T_skin(t) = compute_t_skin(T_process(t), T_ambient(t), k)
        Step 2: f(t) = compute_f_open|closed(T_skin(t))
        Step 3: T_dew(t) = compute_t_dew(T_ambient(t), RH(t))
                w(t)     = compute_wetness(T_skin(t), T_dew(t))
        Step 4: hour_score(t) = compute_hour_score(f(t), w(t))
        Step 5: ACH = compute_ach(hour_score series)

    The trailing ACH window is read from
    ``asset_temperature.ach_window_days`` in ``config.yaml`` (default 90).
    Both ``weather_df`` and ``process_history_df`` are sliced internally to
    ``[max(today - ach_window_days, last_inspection_date), today]``,
    resampled to a clean clock-hour grid (mean within each bucket), and
    joined on ``datetime`` before Steps 1-5 run. Symmetric with
    :func:`...historical_weather_feature.compute_wet_load`, which covers
    the *pre-ACH* half of the same overall window.

    Weather and process temperature come from physically separate data
    sources — the per-location weather cache and the plant's process
    historian — so they stay as two DataFrames; neither pretends to own
    the other's columns. The hourly resample before merging means the
    process historian can log at any cadence (1-minute, 5-minute,
    irregular) without the inner merge silently dropping every row.

    Args:
        insulation_material: Material key into ``insulation_lambda_w_per_mk``.
        insulation_thickness: Insulation jacket thickness, mm (> 0).
        component_diameter: Pipe outer diameter, mm (> 0).
        furnished_thickness: Original/furnished metal wall thickness, mm.
        insulation_condition: ``"GOOD"``/``"AVERAGE"``/``"POOR"`` — combined
            with ``cladding_integrity`` to derive the NACE open/closed flag
            via :func:`is_open_system`.
        cladding_integrity: ``"GOOD"``/``"AVERAGE"``/``"POOR"``.
        weather_df: Hourly DataFrame from the weather cache. Columns
            ``datetime``, ``temp`` (ambient °C), ``dew`` (°C),
            ``humidity`` (% in (0, 100]), ``precip`` (mm). This function
            reads only ``datetime``, ``temp``, ``humidity``; the other
            columns are part of the shared schema with
            ``compute_wet_load`` and are ignored here.
        process_history_df: Hourly DataFrame from the plant's process
            historian. Columns ``datetime`` and ``process_temperature_c``
            (°C). One row per hour, aligned with ``weather_df`` on
            ``datetime``.
        last_inspection_date: Earliest date considered. The ACH window
            cannot extend further back than the last inspection — if the
            inspection is more recent than ``today - ach_window_days``,
            the window shrinks accordingly.
        today: Reference date. Window ends at ``today``.

    Returns:
        Raw ACH for the trailing window. Returns ``0.0`` when
        ``last_inspection_date >= today`` (no window to summarise) or
        when the joined slice is empty.

    Raises:
        ValueError: Propagated from :func:`compute_k` (bad geometry or
            unknown insulation), :func:`is_open_system` (invalid condition
            string), or :func:`compute_t_dew` (RH out of range).
    """
    window = prepare_hourly_window(
        insulation_material,
        insulation_thickness,
        component_diameter,
        furnished_thickness,
        weather_df,
        process_history_df,
        last_inspection_date,
        today,
        h_internal=h_internal,
        h_external=h_external,
    )
    if window.empty:
        return 0.0

    open_system = is_open_system(insulation_condition, cladding_integrity)
    f = compute_f_open if open_system else compute_f_closed

    hour_scores: list[float] = []
    for t_skin, t_ambient, rh in zip(
        window["t_skin"], window["temp"], window["humidity"], strict=True,
    ):
        t_dew = compute_t_dew(t_ambient, rh)
        hour_scores.append(
            compute_hour_score(f(t_skin), compute_wetness(t_skin, t_dew))
        )
    return compute_ach(hour_scores)


# ====================================== Hourly-window helper ======================================


def prepare_hourly_window(
    insulation_material: str,
    insulation_thickness: float,
    component_diameter: float,
    furnished_thickness: float,
    weather_df: pd.DataFrame,
    process_history_df: pd.DataFrame,
    last_inspection_date: pd.Timestamp,
    today: pd.Timestamp,
    h_internal: float | None = None,
    h_external: float | None = None,
) -> pd.DataFrame:
    """Slice → resample → merge → add T_skin: the hourly window for Steps 2–5.

    Public (no underscore prefix) because it is also consumed by
    :func:`...cycle_features.compute_cycles_for_asset`, which builds
    the same T_skin series the ACH pipeline does. Centralising the
    windowing here means the cycle counter and the ACH summer can
    never drift apart on what "the window" means.

    Window: ``[max(today - ach_window_days, last_inspection_date), today]``.
    Both inputs are resampled to a clock-hour grid (mean within each
    bucket) before merging on ``datetime``, so the process historian
    may log at any cadence (1-min, 5-min, irregular) without the merge
    silently dropping rows.

    Returns:
        DataFrame with columns ``datetime``, ``temp``, ``humidity``,
        ``process_temperature_c``, ``t_skin``. Empty (with that column
        schema preserved) when ``last_inspection_date >= today``, when
        either input is empty in the window, or when the inner merge
        produces no overlapping timestamps.
    """
    cfg = load_section(CONFIG_SECTION, REQUIRED_KEYS)
    window_start = max(
        today - pd.Timedelta(days=int(cfg["ach_window_days"])),
        last_inspection_date,
    )
    empty = pd.DataFrame(
        columns=["datetime", "temp", "humidity", "process_temperature_c", "t_skin"]
    )
    if window_start >= today:
        return empty

    weather_window = weather_df[
        (weather_df["datetime"] >= window_start) & (weather_df["datetime"] <= today)
    ]
    process_window = process_history_df[
        (process_history_df["datetime"] >= window_start)
        & (process_history_df["datetime"] <= today)
    ]
    if weather_window.empty or process_window.empty:
        return empty

    weather_hourly = (
        weather_window[["datetime", "temp", "humidity"]]
        .set_index("datetime")
        .resample("h")
        .mean()
        .dropna()
        .reset_index()
    )
    process_hourly = (
        process_window[["datetime", "process_temperature_c"]]
        .set_index("datetime")
        .resample("h")
        .mean()
        .dropna()
        .reset_index()
    )
    window = weather_hourly.merge(process_hourly, on="datetime", how="inner")
    if window.empty:
        return empty

    k = compute_k(
        insulation_material,
        insulation_thickness,
        component_diameter,
        furnished_thickness,
        h_internal=h_internal,
        h_external=h_external,
    )
    return window.assign(
        t_skin=[
            compute_t_skin(t_process, t_ambient, k)
            for t_process, t_ambient in zip(
                window["process_temperature_c"], window["temp"], strict=True,
            )
        ]
    )
