"""Tests for lean_virtual_sensor.feature_engineering.cycle_features.

Covers the pure cycle counter (empty / all-NaN / flat / sub-threshold /
single cooldown / multiple cooldowns / gap-interpolation) and the
per-asset orchestrator (empty-window edge cases plus an end-to-end run
where T_skin tracks an alternating hot/cold process and we verify the
expected cooldown count.
"""

import pandas as pd
import pytest

from lean_virtual_sensor.feature_engineering.cycle_features import (
    compute_cycle_count,
    compute_cycles_for_asset,
)

# Asset geometry/material as individual fields — compute_cycles_for_asset takes
# separate scalar args (no dataclass/dict). It needs only the four thermal
# fields (the condition strings drive the open/closed flag, which cycles ignore).
INSULATION_MATERIAL = "MINERAL_WOOL"
INSULATION_THICKNESS = 50
COMPONENT_DIAMETER = 100
FURNISHED_THICKNESS = 5

# Fixed reference dates so windowing is deterministic across tests.
TODAY = pd.Timestamp("2026-05-26")
LAST_INSPECTION = pd.Timestamp("2024-01-01")


def _t_skin_series(values, end=TODAY):
    """Build an hourly T_skin Series ending at ``end``."""
    return pd.Series(
        values,
        index=pd.date_range(end=end, periods=len(values), freq="h"),
        name="t_skin",
    )


def _weather_df(temp: float, humidity: float, n_hours: int = 3) -> pd.DataFrame:
    """Small hourly weather frame whose datetimes end at TODAY."""
    return pd.DataFrame(
        {
            "datetime": pd.date_range(end=TODAY, periods=n_hours, freq="h"),
            "temp": [temp] * n_hours,
            "humidity": [humidity] * n_hours,
        }
    )


def _process_df(t_process: float, n_hours: int = 3) -> pd.DataFrame:
    """Small hourly process-historian frame matching _weather_df's datetimes."""
    return pd.DataFrame(
        {
            "datetime": pd.date_range(end=TODAY, periods=n_hours, freq="h"),
            "process_temperature_c": [t_process] * n_hours,
        }
    )


# ====================================== Pure cycle counter ======================================


def test_compute_cycle_count_empty_series_is_zero():
    empty = pd.Series([], dtype=float)
    assert compute_cycle_count(empty, min_swing_c=20.0, max_gap_hours=6) == 0


def test_compute_cycle_count_all_nan_is_zero():
    series = _t_skin_series([float("nan")] * 10)
    assert compute_cycle_count(series, min_swing_c=20.0, max_gap_hours=6) == 0


def test_compute_cycle_count_flat_series_is_zero():
    # No troughs in a constant series.
    series = _t_skin_series([80.0] * 24)
    assert compute_cycle_count(series, min_swing_c=20.0, max_gap_hours=6) == 0


def test_compute_cycle_count_under_three_points_is_zero():
    # find_peaks needs at least three points to define a prominence.
    series = _t_skin_series([80.0, 30.0])
    assert compute_cycle_count(series, min_swing_c=20.0, max_gap_hours=6) == 0


def test_compute_cycle_count_below_threshold_ignored():
    # 5°C dip is well below the 20°C threshold; treated as noise.
    series = _t_skin_series([80, 80, 80, 75, 80, 80, 80])
    assert compute_cycle_count(series, min_swing_c=20.0, max_gap_hours=6) == 0


def test_compute_cycle_count_single_cooldown_counts_as_one():
    # 50°C trough — well above threshold.
    series = _t_skin_series([80, 80, 80, 30, 80, 80, 80])
    assert compute_cycle_count(series, min_swing_c=20.0, max_gap_hours=6) == 1


def test_compute_cycle_count_multiple_cooldowns_all_counted():
    # Three pronounced troughs.
    series = _t_skin_series(
        [80, 80, 30, 80, 80, 30, 80, 80, 30, 80, 80]
    )
    assert compute_cycle_count(series, min_swing_c=20.0, max_gap_hours=6) == 3


def test_compute_cycle_count_interpolates_short_gaps():
    # 2-hour NaN gap (≤ max_gap_hours=6) gets interpolated; the cycle survives.
    series = _t_skin_series(
        [80, 80, float("nan"), float("nan"), 30, 80, 80]
    )
    assert compute_cycle_count(series, min_swing_c=20.0, max_gap_hours=6) == 1


# ====================================== Per-asset orchestrator ======================================


def test_compute_cycles_for_asset_inspection_in_or_after_today_is_zero():
    cycles = compute_cycles_for_asset(
        INSULATION_MATERIAL,
        INSULATION_THICKNESS,
        COMPONENT_DIAMETER,
        FURNISHED_THICKNESS,
        _weather_df(temp=15, humidity=95),
        _process_df(t_process=20),
        TODAY,  # inspection == today → empty window
        TODAY,
    )
    assert cycles == 0


def test_compute_cycles_for_asset_empty_frames_is_zero():
    empty_weather = pd.DataFrame(columns=["datetime", "temp", "humidity"])
    empty_process = pd.DataFrame(columns=["datetime", "process_temperature_c"])
    assert (
        compute_cycles_for_asset(
            INSULATION_MATERIAL,
            INSULATION_THICKNESS,
            COMPONENT_DIAMETER,
            FURNISHED_THICKNESS,
            empty_weather,
            empty_process,
            LAST_INSPECTION,
            TODAY,
        )
        == 0
    )


def test_compute_cycles_for_asset_finds_cooldowns_in_process_swings():
    # Build a 24-hour window where process temperature alternates between
    # hot (100 °C) and cold (20 °C) every few hours. With a stable ambient
    # and the test asset's geometry, T_skin will track process — three
    # cold spells in the window should register as three cooldown cycles.
    n_hours = 24
    process_pattern = (
        [100] * 4 + [20] * 2
        + [100] * 4 + [20] * 2
        + [100] * 4 + [20] * 2
        + [100] * 6
    )
    weather = _weather_df(temp=15, humidity=60, n_hours=n_hours)
    process = pd.DataFrame(
        {
            "datetime": pd.date_range(end=TODAY, periods=n_hours, freq="h"),
            "process_temperature_c": process_pattern,
        }
    )
    cycles = compute_cycles_for_asset(
        INSULATION_MATERIAL,
        INSULATION_THICKNESS,
        COMPONENT_DIAMETER,
        FURNISHED_THICKNESS,
        weather,
        process,
        LAST_INSPECTION,
        TODAY,
    )
    assert cycles == 3
