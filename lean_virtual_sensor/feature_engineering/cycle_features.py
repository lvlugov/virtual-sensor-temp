"""Cooldown cycle counting for the CUI lean virtual sensor.

A "cycle" is a significant cooldown in the metal-skin temperature
(``T_skin``). Cooldowns are detected as troughs whose **prominence**
(drop relative to the surrounding baseline) exceeds a threshold —
this rejects sensor noise (~3 °C hourly jitter) while catching real
process cooldowns (50 °C+).

Two public entry points:

* :func:`compute_cycle_count` — pure aggregator over a ``T_skin``
  series. Same role for cycles that :func:`...asset_temperature.compute_ach`
  plays for hour scores: takes the per-hour numbers, returns one number.

* :func:`compute_cycles_for_asset` — per-asset orchestrator. Builds
  the same hourly ``T_skin`` series :func:`...asset_temperature.compute_ach_for_asset`
  uses (via the shared :func:`...asset_temperature.prepare_hourly_window`
  helper) and runs the cycle counter against it.

Calibration constants (prominence threshold, NaN-gap interpolation
limit) live in the ``asset_temperature`` block of ``config.yaml`` next
to ``ach_window_days`` — the same window drives both ACH and cycles.
"""

from __future__ import annotations

import pandas as pd
from scipy.signal import find_peaks

from lean_virtual_sensor.config import load_section
from lean_virtual_sensor.feature_engineering.asset_temperature import (
    prepare_hourly_window,
)

CONFIG_SECTION = "asset_temperature"
REQUIRED_KEYS = (
    "ach_window_days",
    "cycle_min_swing_c",
    "cycle_max_gap_hours",
)


def compute_cycle_count(
    t_skin_series: pd.Series,
    min_swing_c: float,
    max_gap_hours: int,
) -> int:
    """Count hourly T_skin cooldown cycles by prominence.

    A "cycle" is a trough whose prominence (drop relative to the
    surrounding baseline) is at least ``min_swing_c`` °C. The threshold
    rejects sensor noise (~3 °C hourly jitter) while still catching
    real process cooldowns (50 °C+).

    Args:
        t_skin_series: Hourly T_skin values, typically the ``t_skin``
            column of the DataFrame returned by
            :func:`...asset_temperature.prepare_hourly_window`. NaNs
            are tolerated — gaps up to ``max_gap_hours`` consecutive
            samples are linearly interpolated; longer NaN runs are
            dropped so no phantom trough spans them.
        min_swing_c: Minimum trough prominence in °C to count as a cycle.
        max_gap_hours: Maximum interpolatable gap, in hours.

    Returns:
        Integer cooldown count. Returns ``0`` for an empty, all-NaN,
        or sub-three-point cleaned series (peak detection needs at
        least three points to define a prominence).
    """
    if t_skin_series.empty or t_skin_series.notna().sum() == 0:
        return 0
    cleaned = (
        t_skin_series.astype(float)
        .interpolate(limit=max_gap_hours, limit_area="inside")
        .dropna()
    )
    if len(cleaned) < 3:
        return 0
    troughs, _ = find_peaks(-cleaned.to_numpy(), prominence=min_swing_c)
    return int(len(troughs))


def compute_cycles_for_asset(
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
) -> int:
    """Count T_skin cooldown cycles over the trailing ACH window.

    Builds the same hourly T_skin series that
    :func:`...asset_temperature.compute_ach_for_asset` uses (via the
    shared :func:`...asset_temperature.prepare_hourly_window` helper),
    then runs :func:`compute_cycle_count` against it. Window length
    and the cycle thresholds (prominence floor, max interpolatable
    gap) all come from the ``asset_temperature`` config block.

    Args:
        insulation_material: Material key into ``insulation_lambda_w_per_mk``.
        insulation_thickness: Insulation jacket thickness, mm (> 0).
        component_diameter: Pipe outer diameter, mm (> 0).
        furnished_thickness: Original/furnished metal wall thickness, mm.
        weather_df: Hourly weather DataFrame. See
            :func:`...asset_temperature.compute_ach_for_asset` for the
            column contract.
        process_history_df: Hourly process-historian DataFrame.
        last_inspection_date: Earliest date the window may extend back
            to (mirrors :func:`...asset_temperature.compute_ach_for_asset`).
        today: Reference date; window ends here.
        h_internal: Internal film coefficient override, W/m²·K (``None`` →
            config default).
        h_external: External film coefficient override, W/m²·K (``None`` →
            config default).

    Returns:
        Integer cooldown count for the window. Returns ``0`` for an
        empty window.
    """
    cfg = load_section(CONFIG_SECTION, REQUIRED_KEYS)
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
        return 0
    t_skin_series = window.set_index("datetime")["t_skin"]
    return compute_cycle_count(
        t_skin_series,
        min_swing_c=float(cfg["cycle_min_swing_c"]),
        max_gap_hours=int(cfg["cycle_max_gap_hours"]),
    )
