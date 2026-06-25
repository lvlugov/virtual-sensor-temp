"""Thin wrapper over inputs_generation.generate_features.append_features.

When weather_dir is absent, falls back to running the feature pipeline directly
with empty time-series DataFrames (ACH, cycle_count, wet_load will be zero).
"""

from pathlib import Path

import pandas as pd

from lean_virtual_sensor.inputs_generation.generate_features import (
    _DATE_COLUMNS,
    _FEATURE_COLUMNS,
    _feature_kwargs,
    append_features,
)

_API583_TOTAL_COLUMN = "api583_total_score"


def featurise_inventory(
    raw_synthetic_inputs_csv: Path,
    timeseries_dir: Path,
    weather_dir: Path,
    output_csv: Path,
    *,
    reference_date: str,
    seed: int,
) -> Path:
    """Append derived CUI features to the raw synthetic inputs CSV.

    Delegates to append_features() when weather_dir exists (full path with real
    timeseries data). Falls back to _featurise_no_weather() otherwise, which
    runs the feature pipeline with empty time-series DataFrames; ACH, cycle_count
    and wet_load will be zero but all other features are computed correctly.

    Args:
        raw_synthetic_inputs_csv: Static synthetic dataset CSV (output of generate step).
        timeseries_dir: Directory of per-asset process-temperature CSVs.
        weather_dir: Directory of per-location hourly weather caches.
        output_csv: Destination CSV (original columns + feature + API 583 columns).
        reference_date: Run "today" as ISO string (YYYY-MM-DD).
        seed: Run seed; reproduces the asset -> weather-cache assignment.

    Returns:
        Path to the written output CSV.
    """
    if weather_dir.exists():
        append_features(
            raw_synthetic_inputs_csv,
            weather_dir,
            timeseries_dir,
            output_csv,
            reference_date=pd.Timestamp(reference_date),
            seed=seed,
        )
    else:
        _featurise_no_weather(
            raw_synthetic_inputs_csv,
            output_csv,
            reference_date=pd.Timestamp(reference_date),
        )
    return output_csv


def _featurise_no_weather(
    dataset_path: Path,
    output_path: Path,
    *,
    reference_date: pd.Timestamp,
) -> None:
    """Featurise without weather or timeseries data using empty DataFrames.

    Called when weather_dir is absent. All time-series-dependent features
    (ach_90d, cycle_count, wet_load) will be zero/NaN.
    """
    from lean_virtual_sensor.feature_engineering.api_583_risk.pipeline import (
        compute_api_583_likelihood,
    )
    from lean_virtual_sensor.feature_engineering.feature_pipeline import (
        compute_features_for_asset,
    )

    empty_weather_df = pd.DataFrame(columns=["datetime", "temp", "dew", "humidity", "precip"])
    empty_process_df = pd.DataFrame(columns=["datetime", "process_temperature_c"])

    static_df = pd.read_csv(dataset_path, parse_dates=list(_DATE_COLUMNS))
    features: list[dict] = []
    api_totals: list[int | None] = []

    for _, row in static_df.iterrows():
        try:
            result = compute_features_for_asset(
                **_feature_kwargs(row, empty_weather_df, empty_process_df, reference_date)
            )
            features.append({col: result[col] for col in _FEATURE_COLUMNS})
        except (ValueError, KeyError):
            features.append({})
            api_totals.append(None)
            continue

        try:
            likelihood = compute_api_583_likelihood(
                {**result, "sweating_asset": row["sweating_asset"]}
            )
            api_totals.append(int(likelihood["total"]))
        except (ValueError, KeyError):
            api_totals.append(None)

    feature_df = pd.DataFrame(features, columns=list(_FEATURE_COLUMNS), index=static_df.index)
    api_df = pd.DataFrame({_API583_TOTAL_COLUMN: api_totals}, index=static_df.index)
    output_df = pd.concat([static_df, feature_df, api_df], axis=1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_df.to_csv(output_path, index=False)
