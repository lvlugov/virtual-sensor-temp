"""Shared acceptance checks for static temperature field populations (spec Section 2)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd


def is_wide_swing_row(row: pd.Series) -> bool:
    """Wide-swing table row: operating ~250 °C with sub-ambient min."""
    op = float(row["operating_temperature"])
    t_min = float(row["min_operating_temperature"])
    return 245.0 <= op <= 255.0 and t_min <= -5.0


def is_cold_service_row(row: pd.Series) -> bool:
    """Cold service: sub-ambient operating, not wide-swing."""
    return float(row["operating_temperature"]) < 0.0 and not is_wide_swing_row(row)


def assert_wide_swing_fraction_near_five_percent(
    dataframe: pd.DataFrame,
    *,
    slack: int = 10,
) -> None:
    wide_count = int(dataframe.apply(is_wide_swing_row, axis=1).sum())
    n_rows = len(dataframe)
    expected = int(round(0.05 * n_rows))
    assert abs(wide_count - expected) <= slack, (
        f"wide-swing count {wide_count}, expected ~{expected} (±{slack})"
    )


def assert_pipe_operating_median_nearer_peak_than_midpoint(dataframe: pd.DataFrame) -> None:
    pipe_rows = dataframe[dataframe["asset_class"] == "PIPE"]
    pipe_rows = pipe_rows[~pipe_rows.apply(is_wide_swing_row, axis=1)]
    assert not pipe_rows.empty
    median_op = float(pipe_rows["operating_temperature"].median())
    peak = 100.0
    midpoint = 170.0
    assert abs(median_op - peak) < abs(median_op - midpoint), (
        f"PIPE median {median_op} not nearer peak {peak} than midpoint {midpoint}"
    )


def assert_cold_service_fractions_within_tolerance(
    dataframe: pd.DataFrame,
    operating_temperature_config: Mapping[str, Any],
    *,
    tolerance: float = 0.04,
) -> None:
    cold_fracs = operating_temperature_config["cold_service_fraction"]
    for class_name, target in cold_fracs.items():
        class_rows = dataframe[dataframe["asset_class"] == class_name]
        if class_rows.empty:
            continue
        cold_count = int(class_rows.apply(is_cold_service_row, axis=1).sum())
        actual = cold_count / len(class_rows)
        target_f = float(target)
        assert abs(actual - target_f) <= tolerance, (
            f"{class_name}: cold-service fraction {actual:.3f}, "
            f"target {target_f:.3f} (±{tolerance})"
        )


def assert_hot_assets_have_non_negative_min(dataframe: pd.DataFrame) -> None:
    """Ordinary hot assets: operating > 0 and min ≥ 0 (excludes cold and wide-swing)."""
    mask = (
        (dataframe["operating_temperature"] > 0)
        & ~dataframe.apply(is_wide_swing_row, axis=1)
        & ~dataframe.apply(is_cold_service_row, axis=1)
    )
    if not mask.any():
        return
    mins = dataframe.loc[mask, "min_operating_temperature"]
    assert (mins >= 0).all()


def assert_reactor_on_stream_below_pipe(dataframe: pd.DataFrame) -> None:
    reactor_median = float(
        dataframe.loc[
            dataframe["asset_class"] == "REACTOR", "operation_vs_shutdown_fraction"
        ].median()
    )
    pipe_median = float(
        dataframe.loc[dataframe["asset_class"] == "PIPE", "operation_vs_shutdown_fraction"].median()
    )
    assert reactor_median < pipe_median


def assert_temperature_population_acceptance(
    dataframe: pd.DataFrame,
    operating_temperature_config: Mapping[str, Any],
) -> None:
    """Run all Section 2 population acceptance checks."""
    assert_wide_swing_fraction_near_five_percent(dataframe)
    assert_pipe_operating_median_nearer_peak_than_midpoint(dataframe)
    assert_cold_service_fractions_within_tolerance(dataframe, operating_temperature_config)
    assert_hot_assets_have_non_negative_min(dataframe)
    assert_reactor_on_stream_below_pipe(dataframe)
