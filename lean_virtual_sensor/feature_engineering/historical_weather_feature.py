"""Recency-weighted historical wetting load (pre-ACH window).

Complement to Active CUI Hours: ratio of wetting (rain + vapor ingress)
to wetting + drying over ``[last_inspection_date, today − 90 d)``, with
recent days weighted more via exponential decay.

Full formula, literature anchors, and design rationale:
``docs/historical_weather_feature.md``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from lean_virtual_sensor.config import load_section

CONFIG_SECTION = "historical_weather"
REQUIRED_KEYS = (
    "ach_window_days",
    "half_life_days",
    "drying_weight",
    "drying_temp_threshold_c",
    "drying_humidity_threshold_percent",
    "vapor_weight",
    "vapor_humidity_threshold_percent",
)


# ====================================== Step helpers ======================================


def _slice_window(
    weather_df: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    """Filter hourly weather to ``[start, end)`` by ``datetime``."""
    return weather_df[(weather_df["datetime"] >= start) & (weather_df["datetime"] < end)]


def _resample_to_daily(window: pd.DataFrame) -> pd.DataFrame:
    """Hourly → daily: sum precip, mean humidity, mean temp."""
    return (
        window.set_index("datetime")
        .resample("D")
        .agg({"precip": "sum", "humidity": "mean", "temp": "mean"})
    )


def _recency_weights(
    daily: pd.DataFrame,
    window_end: pd.Timestamp,
    half_life_days: float,
) -> pd.Series:
    """Exponential decay weight per day: ``0.5 ** (age_days / half_life)``."""
    age_days = (window_end - daily.index).days
    return pd.Series(0.5 ** (age_days / half_life_days), index=daily.index)


def _weighted_wet(
    daily: pd.DataFrame,
    weight: pd.Series,
    vapor_weight: float,
    vapor_humidity_threshold: float,
) -> float:
    """Weighted Σ of (rain + vapor ingress).

    Vapor contributes only when daily humidity exceeds the threshold.
    """
    vapor_per_day = vapor_weight * np.maximum(daily["humidity"] - vapor_humidity_threshold, 0)
    return float(((daily["precip"] + vapor_per_day) * weight).sum())


def _weighted_drying(
    daily: pd.DataFrame,
    weight: pd.Series,
    drying_weight: float,
    temp_threshold: float,
    humidity_threshold: float,
) -> float:
    """Weighted Σ of drying potential on hot-dry days only.

    A day counts as hot-dry when ``temp > temp_threshold`` AND
    ``humidity < humidity_threshold``.
    """
    hot_dry = (daily["temp"] > temp_threshold) & (daily["humidity"] < humidity_threshold)
    drying_per_day = drying_weight * daily["temp"] * (1 - daily["humidity"] / 100)
    return float((drying_per_day * weight * hot_dry).sum())


# ====================================== Public entry point ======================================


def compute_wet_load(
    weather_df: pd.DataFrame,
    last_inspection_date: pd.Timestamp,
    today: pd.Timestamp,
    open_system: bool,
) -> float:
    """Recency-weighted ratio of wetting to (wetting + drying).

    Args:
        weather_df: Hourly weather frame with columns ``datetime``,
            ``temp``, ``humidity``, ``precip``.
        last_inspection_date: Pre-ACH window start (inclusive).
        today: Reference date; window ends at ``today − ach_window_days``.
        open_system: From :func:`...system_flag_feature.is_open_system`.
            ``True`` short-circuits to ``0.0``.

    Returns:
        ``wet_load`` in ``[0, 1]``. Returns ``0.0`` for open systems,
        for inspections inside the ACH window, for empty slices, and
        when both wetting and drying totals are zero.
    """
    if open_system:
        return 0.0

    cfg = load_section(CONFIG_SECTION, REQUIRED_KEYS)
    window_end = today - pd.Timedelta(days=int(cfg["ach_window_days"]))
    if last_inspection_date >= window_end:
        return 0.0

    window = _slice_window(weather_df, last_inspection_date, window_end)
    if window.empty:
        return 0.0

    daily = _resample_to_daily(window)
    weight = _recency_weights(daily, window_end, float(cfg["half_life_days"]))

    weighted_wet = _weighted_wet(
        daily,
        weight,
        vapor_weight=float(cfg["vapor_weight"]),
        vapor_humidity_threshold=float(cfg["vapor_humidity_threshold_percent"]),
    )
    weighted_drying = _weighted_drying(
        daily,
        weight,
        drying_weight=float(cfg["drying_weight"]),
        temp_threshold=float(cfg["drying_temp_threshold_c"]),
        humidity_threshold=float(cfg["drying_humidity_threshold_percent"]),
    )

    total = weighted_wet + weighted_drying
    return weighted_wet / total if total > 0 else 0.0
