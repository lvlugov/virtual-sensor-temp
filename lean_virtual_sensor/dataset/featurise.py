"""Thin wrapper over inputs_generation.generate_features.append_features."""

from pathlib import Path

import pandas as pd

from lean_virtual_sensor.inputs_generation.generate_features import append_features


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
    append_features(
        raw_synthetic_inputs_csv,
        weather_dir,
        timeseries_dir,
        output_csv,
        reference_date=pd.Timestamp(reference_date),
        seed=seed,
    )
    return output_csv
