"""
temperature_series.py
======================
Synthetic per-asset process-temperature series (``T_process(t)``).

This is the separate time-series module the schema refers to: it consumes the
static dataset (one row per asset) plus a supplied hourly ambient series, and
produces one hourly temperature value per asset over the 90-day window
(90 × 24 = 2,160 hours). The ambient series is an INPUT — never modelled here.

Section references are to docs/synthetic_inputs_methodology.md.

Step 1 (this commit) — the thermal time constant ``tau`` (Section 5): the one
number per asset that sets how fast it slides toward its cooldown target during
a shutdown. Constants (per-metallurgy metal rho/c, per-material insulation
conductivity) live in ``generation_config.yaml`` under ``temperature_series``.
"""

from __future__ import annotations

import math

import numpy as np


def compute_tau(
    outer_diameter_mm: float,
    wall_thickness_mm: float,
    insulation_thickness_mm: float,
    insulation_conductivity_w_per_mk: float,
    *,
    metal_density_kg_per_m3: float,
    metal_specific_heat_j_per_kg_k: float,
) -> float:
    """Thermal time constant ``tau`` in hours (Section 5).

        tau_h = C * R / 3600
        C  = rho * c * A_metal,  A_metal = (pi/4)(Do^2 - Di^2),  Di = Do - 2*wall
        R  = ln(Dins / Do) / (2 * pi * k_ins),  Dins = Do + 2*insulation_thickness

    ``C`` is the metal's heat capacity per metre and ``R`` the insulation's
    resistance per metre; length cancels, so tau depends only on diameter, wall
    thickness, and insulation. It feeds the per-hour slide
    ``new = target + (prev - target) * exp(-1/tau)``: after ~tau hours roughly
    two-thirds of the gap is covered, after ~3*tau essentially all of it.

    Geometry is in millimetres (the static dataset's ``component_diameter`` and
    ``furnished_thickness`` are mm) and converted to metres internally. The
    insulation conductivity (by material) and metal rho/c (by metallurgy) come
    from the caller (read from the ``temperature_series`` config block).

    Args:
        outer_diameter_mm: Metal outer diameter Do, mm. Must be > 0.
        wall_thickness_mm: Metal wall thickness, mm. Must satisfy
            0 < wall < outer_diameter / 2 (must leave a bore).
        insulation_thickness_mm: Insulation jacket thickness, mm. Must be > 0.
        insulation_conductivity_w_per_mk: k_ins for the asset's insulation
            material, W/(m·K). Must be > 0.
        metal_density_kg_per_m3: rho for the asset's metallurgy.
        metal_specific_heat_j_per_kg_k: c for the asset's metallurgy.

    Returns:
        tau in hours (> 0).

    Raises:
        ValueError: If any dimension or conductivity is non-positive, or if
            ``wall_thickness_mm >= outer_diameter_mm / 2`` (leaves no bore).
    """
    if outer_diameter_mm <= 0:
        raise ValueError(f"outer_diameter_mm must be > 0, got {outer_diameter_mm}")
    if wall_thickness_mm <= 0:
        raise ValueError(f"wall_thickness_mm must be > 0, got {wall_thickness_mm}")
    if wall_thickness_mm >= outer_diameter_mm / 2:
        raise ValueError(
            f"wall_thickness_mm ({wall_thickness_mm}) leaves no bore: "
            f"must be < outer_diameter_mm / 2 ({outer_diameter_mm / 2})."
        )
    if insulation_thickness_mm <= 0:
        raise ValueError(f"insulation_thickness_mm must be > 0, got {insulation_thickness_mm}")
    if insulation_conductivity_w_per_mk <= 0:
        raise ValueError(
            f"insulation_conductivity_w_per_mk must be > 0, got {insulation_conductivity_w_per_mk}"
        )

    do_m = outer_diameter_mm / 1000
    di_m = (outer_diameter_mm - 2 * wall_thickness_mm) / 1000
    dins_m = do_m + 2 * (insulation_thickness_mm / 1000)

    a_metal = (math.pi / 4) * (do_m**2 - di_m**2)
    c = metal_density_kg_per_m3 * metal_specific_heat_j_per_kg_k * a_metal
    r = math.log(dins_m / do_m) / (2 * math.pi * insulation_conductivity_w_per_mk)
    return c * r / 3600


# ==================================== Step 3: Cycle placement ====================================


def place_cycles(n_cycles: int, window_hours: int) -> np.ndarray:
    """Place ``n_cycles`` thermal-cycle events at equal intervals (methodology §3).

    With ``spacing = window_hours / n_cycles``, event ``i`` (0..n_cycles-1) starts
    at ``round((i + 0.5) * spacing)``. The ``+ 0.5`` centres the events, leaving a
    half-spacing of running time at each end so none starts at hour 0 or runs off
    the end. Spacing is uniform, not random.

    This decides only WHEN each cycle begins. A cycle is not necessarily a full
    shutdown — its duration (Step 4) and depth (full cooldown vs partial
    turndown, Step 5) are set later.

    ``window_hours`` is supplied by the caller as
    ``temperature_series.window_days * 24`` from config (kept out of this
    function so it stays pure and unit-testable, like :func:`compute_tau`).

    Args:
        n_cycles: Number of cycle events (the asset's ``avg_cycles_per_quarter``).
            Must be >= 0; 0 returns an empty array (asset never cycles).
        window_hours: Window length in hours. Must be > 0.

    Returns:
        Ascending int array of start-hour indices in ``[0, window_hours - 1]``,
        one per cycle. Empty when ``n_cycles == 0``.

    Raises:
        ValueError: If ``n_cycles < 0`` or ``window_hours <= 0``.
    """
    if n_cycles < 0:
        raise ValueError(f"n_cycles must be >= 0, got {n_cycles}")
    if window_hours <= 0:
        raise ValueError(f"window_hours must be > 0, got {window_hours}")
    if n_cycles == 0:
        return np.empty(0, dtype=int)

    spacing = window_hours / n_cycles
    starts = np.round((np.arange(n_cycles) + 0.5) * spacing).astype(int)
    return np.clip(starts, 0, window_hours - 1)


# ==================================== Step 4: Cycle durations ====================================


def size_cycles(
    n_cycles: int,
    fraction: float,
    window_hours: int,
    min_cycle_duration_hours: int,
) -> np.ndarray:
    """Give every cycle the same off-duration (methodology §4, uniform variant).

    The off-budget ``(1 - fraction) * window_hours`` is split **equally** across
    the ``n_cycles`` cycles, so each is off-operating for::

        duration = (1 - fraction) * window_hours / n_cycles = (1 - fraction) * spacing

    i.e. each cycle slot is ``(1 - fraction)`` off and ``fraction`` running. This
    is uniform per asset (all cycles equal) and, since N and fraction are class
    values, uniform per class. Because ``(1 - fraction) * spacing < spacing``, a
    cycle can never overrun the next, so no cap is needed.

    Each duration is floored at ``min_cycle_duration_hours`` for the rare
    high-fraction / high-N case where the raw value rounds below a meaningful
    shutdown.

    Duration is *how long* off, not *how deep* — depth (full cooldown vs partial
    turndown) is Step 5.

    Args:
        n_cycles: Number of cycle events (from :func:`place_cycles`). Must be >= 0;
            0 returns an empty array.
        fraction: ``operation_vs_shutdown_fraction`` in [0, 1] — share of the
            window spent running.
        window_hours: Window length in hours. Must be > 0.
        min_cycle_duration_hours: Floor on a single cycle's duration. Must be >= 1.

    Returns:
        Int array of length ``n_cycles``, every element the same duration (hours).
        Empty when ``n_cycles == 0``.

    Raises:
        ValueError: If ``n_cycles < 0``, ``fraction`` outside [0, 1],
            ``window_hours <= 0``, or ``min_cycle_duration_hours < 1``.
    """
    if n_cycles < 0:
        raise ValueError(f"n_cycles must be >= 0, got {n_cycles}")
    if not 0.0 <= fraction <= 1.0:
        raise ValueError(f"fraction must be in [0, 1], got {fraction}")
    if window_hours <= 0:
        raise ValueError(f"window_hours must be > 0, got {window_hours}")
    if min_cycle_duration_hours < 1:
        raise ValueError(f"min_cycle_duration_hours must be >= 1, got {min_cycle_duration_hours}")
    if n_cycles == 0:
        return np.empty(0, dtype=int)

    duration = max(
        int(round((1.0 - fraction) * window_hours / n_cycles)),
        min_cycle_duration_hours,
    )
    return np.full(n_cycles, duration, dtype=int)


# ==================================== Step 5: Cooldown target ====================================


def cooldown_reference(
    operating_temperature: float,
    min_operating_temperature: float,
) -> str:
    """Pick what a shutdown cools *toward* (§5): ``"ambient"`` or ``"min"``.

    Every shutdown aims at a real cold target — there is no partial / hold-warm
    behaviour. How far it actually gets is set entirely by duration vs τ in
    :func:`apply_thermal_lag`: a shutdown switched back on before ~3·τ never
    reaches the bottom, it just turns around from wherever it got to. So "full"
    vs "partial" dips emerge across the population from each asset's τ, not from
    any per-cycle choice here.

    * **Wide-swing** (``operating > 0`` and ``min < 0`` — the assumed 5% Dow
      Terneuzen rows): aims at ``min`` (driven sub-ambient).
    * **Everyone else** (ordinary hot and cold-service): aims at ``ambient``.
      Cold-service (``operating < 0``) slides *up* toward ambient automatically;
      the reactor's large τ keeps its dips partial automatically — no special cases.

    Args:
        operating_temperature: Asset operating temperature (°C).
        min_operating_temperature: Asset min temperature (°C).

    Returns:
        ``"min"`` for wide-swing assets, otherwise ``"ambient"``.
    """
    if operating_temperature > 0 and min_operating_temperature < 0:
        return "min"
    return "ambient"


# ============================== Step 6: Assemble per-hour target ==============================


def build_target_series(
    operating_temperature: float,
    min_operating_temperature: float,
    starts: np.ndarray,
    durations: np.ndarray,
    ref_kind: str,
    ambient: np.ndarray,
) -> np.ndarray:
    """Fold baseline + cycles + ambient into the per-hour target array (§3 steps 1–5).

    Starts flat at ``operating_temperature`` (the running baseline), then over
    each cycle's window ``[start, start + duration)`` sets the target to the
    cooldown reference: the ambient series (``ref_kind == "ambient"`` — ordinary
    hot and cold-service) or the scalar ``min`` (``ref_kind == "min"`` —
    wide-swing). Every shutdown aims fully at that reference; how far the
    temperature actually gets is decided by :func:`apply_thermal_lag` (Step 7)
    from duration vs τ. The result is **blocky** (vertical edges) on purpose.

    Deterministic. The window length is taken from ``ambient``.

    Args:
        operating_temperature: Running baseline / start of every excursion (°C).
        min_operating_temperature: The ``min`` target for wide-swing (°C).
        starts: Cycle start hours (from :func:`place_cycles`).
        durations: Cycle durations in hours (from :func:`size_cycles`).
        ref_kind: ``"ambient"`` or ``"min"`` (from :func:`cooldown_reference`).
        ambient: Hourly ambient series (°C), one value per hour of the window.
            Must be non-empty; its length defines the output length.

    Returns:
        Hourly target array (°C), same length as ``ambient``.

    Raises:
        ValueError: If ``ref_kind`` is invalid, ``ambient`` is empty, or
            ``starts`` and ``durations`` are not the same length.
    """
    if ref_kind not in ("ambient", "min"):
        raise ValueError(f"ref_kind must be 'ambient' or 'min', got {ref_kind!r}")
    if ambient.size == 0:
        raise ValueError("ambient must be non-empty")
    if len(starts) != len(durations):
        raise ValueError(
            f"starts and durations must be the same length, got {len(starts)}, {len(durations)}"
        )

    window_hours = ambient.size
    target = np.full(window_hours, float(operating_temperature))
    for start, duration in zip(starts, durations):
        s = int(start)
        e = min(s + int(duration), window_hours)
        target[s:e] = ambient[s:e] if ref_kind == "ambient" else float(min_operating_temperature)
    return target


# ================================== Step 8: Running-period noise ==================================


def add_running_noise(
    temp: np.ndarray,
    target: np.ndarray,
    operating_temperature: float,
    rng: np.random.Generator,
    amplitude_c: float,
) -> np.ndarray:
    """Add a small uniform wiggle to the running hours (§3 step 6).

    Adds ``Uniform(-amplitude_c, +amplitude_c)`` to the hours **at operating
    temperature** (``target == operating_temperature``), leaving the slides,
    dips, holds, and corrosion-zone crossings untouched so the gradual physics
    and the −4/175 °C hour-count stay clean.

    Args:
        temp: Hourly series from :func:`apply_thermal_lag`.
        target: The target array used to build ``temp`` (identifies running
            hours). Same length as ``temp``.
        operating_temperature: The running baseline value (°C).
        rng: Seeded generator.
        amplitude_c: Half-width of the uniform wiggle (°C). Must be >= 0; 0 is
            a no-op.

    Returns:
        A new series with running-hour noise added (input not mutated).

    Raises:
        ValueError: If ``amplitude_c < 0`` or ``temp`` and ``target`` differ in length.
    """
    if amplitude_c < 0:
        raise ValueError(f"amplitude_c must be >= 0, got {amplitude_c}")
    if temp.size != target.size:
        raise ValueError(f"temp and target must be the same length, got {temp.size}, {target.size}")
    out = temp.astype(float, copy=True)
    if amplitude_c == 0:
        return out
    running = target == operating_temperature
    out[running] += rng.uniform(-amplitude_c, amplitude_c, int(running.sum()))
    return out


# ====================================== Step 9: Clamp ======================================


def clamp_series(
    temp: np.ndarray,
    min_operating_temperature: float,
    max_operating_temperature: float,
    global_min_c: float,
    global_max_c: float,
) -> np.ndarray:
    """Clamp every hour to the asset bounds, then the global range (§3 step 7).

    First clips to ``[min_operating_temperature, max_operating_temperature]``,
    then to ``[global_min_c, global_max_c]``. This is also where the cold-service
    warm-up is capped at ``max`` (it slides toward ambient but cannot exceed the
    asset's max). Non-mutating.

    Args:
        temp: Hourly series (after noise).
        min_operating_temperature: Asset lower bound (°C).
        max_operating_temperature: Asset upper bound (°C). Must be >= min.
        global_min_c: Global physical floor (°C).
        global_max_c: Global physical ceiling (°C). Must be >= ``global_min_c``.

    Returns:
        A new clamped series (input not mutated).

    Raises:
        ValueError: If ``min > max`` or ``global_min_c > global_max_c``.
    """
    if min_operating_temperature > max_operating_temperature:
        raise ValueError(
            f"min ({min_operating_temperature}) must be <= max ({max_operating_temperature})"
        )
    if global_min_c > global_max_c:
        raise ValueError(f"global_min_c ({global_min_c}) must be <= global_max_c ({global_max_c})")
    out = np.clip(temp, min_operating_temperature, max_operating_temperature)
    return np.clip(out, global_min_c, global_max_c)


# ============================== Step 7: Exponential slide engine ==============================


def apply_thermal_lag(target: np.ndarray, tau: float) -> np.ndarray:
    """Relax an hourly series toward a per-hour target with time constant tau.

        temp[0] = target[0]
        temp[t] = target[t] + (temp[t-1] - target[t]) * exp(-1/tau)

    This is the core engine: the metal lags toward whatever target it is handed
    instead of jumping. Each hour it closes a fixed fraction ``1 - exp(-1/tau)``
    of the remaining gap, so after ~tau hours ~63% of a step is covered and
    after ~3*tau essentially all of it. Every physical slide shape emerges from
    this one rule, set by the target pattern and tau: full cooldowns, partial
    turndowns, holds, cold-service warm-ups, and the shallow incomplete dips of
    an asset that cycles faster than it cools.

    Pure relaxation — it knows nothing about shutdowns, ambient, or profiles.
    The target array (Steps 3-6), running noise (Step 8) and clamping (Step 9)
    are applied elsewhere.

    ``tau`` may be a **scalar** (uniform) or a **per-hour 1-D array** (same length
    as ``target``). The per-hour form lets the slide speed vary within the
    series — e.g. a shorter τ on the recovery legs so the return to operating
    temperature (active re-heating) is faster than the passive cooldown.

    Args:
        target: Hourly target temperatures (°C), one per hour of the window.
            Must be non-empty.
        tau: Thermal time constant in hours — a positive scalar, or a positive
            1-D array of length ``len(target)`` (per-hour).

    Returns:
        Hourly temperature series (°C), same length as ``target``, seeded at
        ``target[0]``.

    Raises:
        ValueError: If ``target`` is empty, ``tau`` is not strictly positive, or
            a per-hour ``tau`` array does not match ``target`` in length.
    """
    if target.size == 0:
        raise ValueError("target must be non-empty")
    tau_arr = np.asarray(tau, dtype=float)
    if tau_arr.ndim not in (0, 1):
        raise ValueError("tau must be a scalar or a 1-D array")
    if tau_arr.ndim == 1 and tau_arr.shape != target.shape:
        raise ValueError(
            f"per-hour tau must match target length, got {tau_arr.shape} vs {target.shape}"
        )
    if np.any(tau_arr <= 0):
        raise ValueError("tau must be > 0")

    alpha = np.broadcast_to(np.exp(-1.0 / tau_arr), target.shape)
    temp = np.empty(target.shape, dtype=float)
    temp[0] = target[0]
    for t in range(1, target.size):
        temp[t] = target[t] + (temp[t - 1] - target[t]) * alpha[t]
    return temp
