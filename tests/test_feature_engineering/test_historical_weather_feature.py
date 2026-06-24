"""Tests for the recency-weighted wet_load metric.

Expected values depend on calibration in ``config.yaml``:
half_life_days=365, drying_weight=0.3, drying_temp_threshold_c=15,
drying_humidity_threshold_percent=60, ach_window_days=90. Update if those
change.

Fixtures build *hourly* weather frames matching the Visual Crossing
fetch schema (``datetime``, ``temp``, ``humidity``, ``precip``);
``compute_wet_load`` resamples to daily internally.
"""

import pandas as pd
from lean_virtual_sensor.feature_engineering.historical_weather_feature import (
    compute_wet_load,
)

# Dynamic dates so the tests never depend on a wall-clock date. TODAY is
# midnight today; LAST_INSPECTION sits well before the trailing 90-day ACH
# window so the pre-ACH slice is non-empty.
TODAY = pd.Timestamp.today().normalize()
WINDOW_END = TODAY - pd.Timedelta(days=90)
LAST_INSPECTION = WINDOW_END - pd.Timedelta(days=140)


def _hourly_weather(start, end, *, temp, humidity, precip_per_hour):
    """Build an hourly weather frame with constant per-hour values."""
    timestamps = pd.date_range(start, end, freq="h")
    return pd.DataFrame(
        {
            "datetime": timestamps,
            "temp": temp,
            "dew": temp - 5,
            "humidity": humidity,
            "precip": precip_per_hour,
        }
    )


# ====================================== Short-circuit paths ======================================


def test_open_system_returns_zero_without_touching_weather():
    df = _hourly_weather(LAST_INSPECTION, TODAY, temp=20.0, humidity=95, precip_per_hour=2.0)
    assert compute_wet_load(df, LAST_INSPECTION, TODAY, open_system=True) == 0.0


def test_recent_inspection_inside_ach_window_returns_zero():
    inspection_inside_ach = TODAY - pd.Timedelta(days=30)
    df = _hourly_weather(LAST_INSPECTION, TODAY, temp=20.0, humidity=95, precip_per_hour=2.0)
    assert compute_wet_load(df, inspection_inside_ach, TODAY, open_system=False) == 0.0


def test_empty_weather_frame_returns_zero():
    empty = pd.DataFrame(columns=["datetime", "temp", "dew", "humidity", "precip"])
    empty["datetime"] = pd.to_datetime(empty["datetime"])
    assert compute_wet_load(empty, LAST_INSPECTION, TODAY, open_system=False) == 0.0


def test_weather_outside_window_returns_zero():
    out_of_window = _hourly_weather(
        start=LAST_INSPECTION - pd.Timedelta(days=200),
        end=LAST_INSPECTION - pd.Timedelta(hours=1),
        temp=20.0,
        humidity=95,
        precip_per_hour=2.0,
    )
    assert compute_wet_load(out_of_window, LAST_INSPECTION, TODAY, open_system=False) == 0.0


def test_no_rain_no_vapor_no_drying_returns_zero():
    # Moderate-RH cool days: no rain, humidity 50 (below vapor threshold 60
    # so no vapor ingress), temp 10 (below 15 so NOT hot-dry, no drying).
    # Both weighted_wet and weighted_drying are zero → 0.0 fallback.
    df = _hourly_weather(LAST_INSPECTION, WINDOW_END, temp=10.0, humidity=50, precip_per_hour=0.0)
    assert compute_wet_load(df, LAST_INSPECTION, TODAY, open_system=False) == 0.0


# ====================================== Ratio behaviour ======================================


def test_pure_rain_returns_one():
    # Cool wet days: rain present, but humidity 85 / temp 10 means no
    # day is hot-dry → drying = 0 → ratio = rain / rain = 1.0.
    df = _hourly_weather(LAST_INSPECTION, WINDOW_END, temp=10.0, humidity=85, precip_per_hour=1.0)
    assert compute_wet_load(df, LAST_INSPECTION, TODAY, open_system=False) == 1.0


def test_pure_drying_returns_zero():
    # Hot dry days: no rain, RH 30 (< vapor threshold 60 so no vapor),
    # hot-dry mask True everywhere → weighted_wet = 0, weighted_drying > 0
    # → ratio = 0 / drying = 0.0.
    df = _hourly_weather(LAST_INSPECTION, WINDOW_END, temp=25.0, humidity=30, precip_per_hour=0.0)
    assert compute_wet_load(df, LAST_INSPECTION, TODAY, open_system=False) == 0.0


def test_vapor_alone_returns_one():
    # Cool humid days: no rain, RH 85 (> vapor threshold 60 → vapor ingress
    # contributes), temp 10 (< drying threshold 15 → no drying). Vapor is
    # the only term contributing to either side, so the ratio is
    # weighted_wet / weighted_wet = 1.0.
    df = _hourly_weather(LAST_INSPECTION, WINDOW_END, temp=10.0, humidity=85, precip_per_hour=0.0)
    assert compute_wet_load(df, LAST_INSPECTION, TODAY, open_system=False) == 1.0


def test_result_is_bounded_in_unit_interval():
    # A noisy mixed window should always land in [0, 1].
    df = _hourly_weather(LAST_INSPECTION, WINDOW_END, temp=20.0, humidity=50, precip_per_hour=0.5)
    score = compute_wet_load(df, LAST_INSPECTION, TODAY, open_system=False)
    assert 0.0 <= score <= 1.0


# ====================================== Sequence sensitivity ======================================


def test_recent_rain_scores_higher_than_old_rain():
    """Identical totals, opposite timing → wet_load differs because of recency weighting."""
    half_window = LAST_INSPECTION + (WINDOW_END - LAST_INSPECTION) / 2

    # Asset A: WET in the OLD half (far from window_end), DRY-HOT in the RECENT half.
    a_old_wet = _hourly_weather(
        LAST_INSPECTION,
        half_window - pd.Timedelta(hours=1),
        temp=10.0,
        humidity=85,
        precip_per_hour=1.0,
    )
    a_recent_dry = _hourly_weather(
        half_window,
        WINDOW_END,
        temp=25.0,
        humidity=30,
        precip_per_hour=0.0,
    )
    asset_a = pd.concat([a_old_wet, a_recent_dry], ignore_index=True)

    # Asset B: DRY-HOT in the OLD half, WET in the RECENT half.
    b_old_dry = _hourly_weather(
        LAST_INSPECTION,
        half_window - pd.Timedelta(hours=1),
        temp=25.0,
        humidity=30,
        precip_per_hour=0.0,
    )
    b_recent_wet = _hourly_weather(
        half_window,
        WINDOW_END,
        temp=10.0,
        humidity=85,
        precip_per_hour=1.0,
    )
    asset_b = pd.concat([b_old_dry, b_recent_wet], ignore_index=True)

    score_a = compute_wet_load(asset_a, LAST_INSPECTION, TODAY, open_system=False)
    score_b = compute_wet_load(asset_b, LAST_INSPECTION, TODAY, open_system=False)

    # Both totals are identical; only the timing flips. With recent rain
    # weighted more heavily, B (recent wet) must score strictly higher
    # than A (recent dry).
    assert score_b > score_a


def test_two_close_in_time_wet_periods_produce_similar_scores():
    """Recency weighting is smooth; tiny timing shifts shouldn't flip scores."""
    df_early = _hourly_weather(
        LAST_INSPECTION,
        LAST_INSPECTION + pd.Timedelta(days=10),
        temp=10.0,
        humidity=85,
        precip_per_hour=1.0,
    )
    df_just_later = _hourly_weather(
        LAST_INSPECTION + pd.Timedelta(days=1),
        LAST_INSPECTION + pd.Timedelta(days=11),
        temp=10.0,
        humidity=85,
        precip_per_hour=1.0,
    )
    score_early = compute_wet_load(df_early, LAST_INSPECTION, TODAY, open_system=False)
    score_later = compute_wet_load(df_just_later, LAST_INSPECTION, TODAY, open_system=False)

    # Both produce wet_load = 1.0 because neither has any drying days
    # (temp 10 < threshold 15). The test guards against accidental
    # discontinuities — same shape of input, same score.
    assert score_early == score_later == 1.0
