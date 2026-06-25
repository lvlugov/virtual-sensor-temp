#!/usr/bin/env python3
"""Population runner: append derived CUI features to the static dataset.

This is the caller for :func:`feature_pipeline.compute_features_for_asset` and
the API 583 CUI-likelihood pipeline. It owns everything around the per-asset
feature builder: it loads the static synthetic dataset, pairs each asset with
its hourly weather cache and its process-temperature time series, runs the
feature pipeline, then runs the API 583 scorers on the result, and writes a new
CSV that is the original static dataset with the derived feature columns and the
API 583 columns appended.

API 583 runs *after* the feature pipeline because two of its seventeen inputs —
``coating_age_years`` and ``system_age_years`` — are derived features, not raw
inventory fields. The appended API 583 columns are the seven per-parameter
scores (prefixed ``api583_score_``), ``api583_total``, ``api583_table_used``,
``api583_likelihood`` and ``api583_flag``.

Run order (see ``docs/temperature_series_decisions_methodology.md``)::

    1. python lean_virtual_sensor/inputs_generation/generate.py
         -> writes the static dataset:  outputs/synthetic_v{ver}_seed{seed}.csv
    2. python lean_virtual_sensor/inputs_generation/generate_timeseries.py
         -> writes outputs/timeseries/<ASSET>_<start>_<end>.csv
    3. python lean_virtual_sensor/inputs_generation/generate_features.py
         -> writes outputs/synthetic_v{ver}_seed{seed}_features.csv   (this script)

Two time-varying inputs per asset
---------------------------------
``compute_features_for_asset`` consumes two hourly frames alongside the static
row:

* ``weather_df`` — the asset's per-location weather cache (``datetime``,
  ``temp``, ``dew``, ``humidity``, ``precip``). The full cache (trimmed to
  ``reference_date``) is passed, not just the trailing 90 days, because the
  wet-load feature reaches back to the last inspection date (up to ~10 years).
* ``process_history_df`` — the per-asset process-temperature series produced by
  ``generate_timeseries.py`` (``datetime``, ``process_temperature_c``).

Ambient assignment
-------------------
The static dataset carries no location, so each asset is assigned a cached
weather location by the **same seeded, row-positional draw** that
``generate_timeseries.py`` uses (``run.random_seed``). Reproducing that draw is
what guarantees the weather cache used to score an asset is the one that
generated its process-temperature series. The assignment therefore depends on
the weather-cache directory being unchanged since the time series were written.

Skipped assets
--------------
An asset is left with empty (NaN) feature columns — never dropped — when its
time-series CSV is missing, or when the feature pipeline rejects it (e.g. a
geometry the heat balance cannot solve). Skips are counted and logged.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

logger = logging.getLogger(__name__)

# Weather-cache directory entries that are not per-location caches.
_WEATHER_SKIP_EXACT = {"INDEX.csv"}
_WEATHER_SKIP_PREFIX = "sample_"

# The six derived columns appended to the static dataset, in output order.
_FEATURE_COLUMNS = (
    "coating_age_years",
    "system_age_years",
    "open_system",
    "ach_90d",
    "cycle_count",
    "wet_load",
)

# The single API 583 column appended after the feature columns: the summed
# CUI-likelihood total across the seven parameter scorers.
_API583_TOTAL_COLUMN = "api583_total_score"

# Static-dataset date columns parsed to Timestamps on load.
_DATE_COLUMNS = (
    "asset_commissioning_date",
    "insulation_install_date",
    "coating_application_date",
    "latest_inspection_date",
)


def _inputs_generation_dir() -> Path:
    return Path(__file__).resolve().parent


def _load_run_config(generation_config_path: Path) -> dict[str, Any]:
    """Read the ``run`` block from generation_config.yaml (reference_date, seed)."""
    cfg = yaml.safe_load(generation_config_path.read_text(encoding="utf-8"))
    if not isinstance(cfg, dict) or "run" not in cfg:
        raise ValueError(f"{generation_config_path} must contain a 'run' block.")
    return cfg["run"]


def _discover_weather_caches(weather_dir: Path) -> list[Path]:
    """List per-location weather-cache CSVs, sorted for a stable assignment order.

    Excludes the ``INDEX.csv`` manifest and any ``sample_*.csv`` files. Must mirror
    the discovery in ``generate_timeseries.py`` exactly so the seeded asset ->
    location assignment reproduces.
    """
    caches = [
        p
        for p in sorted(weather_dir.glob("*.csv"))
        if p.name not in _WEATHER_SKIP_EXACT
        and not p.name.startswith(_WEATHER_SKIP_PREFIX)
    ]
    if not caches:
        raise FileNotFoundError(
            f"No per-location weather caches found in {weather_dir}."
        )
    return caches


def _load_weather_cache(cache_path: Path, reference_date: pd.Timestamp) -> pd.DataFrame:
    """Load a full location cache (all five columns), trimmed to <= reference_date.

    Unlike the 90-day ambient window the time-series generator uses, the feature
    pipeline needs the cache as far back as each asset's last inspection date, so
    the whole history is kept. Missing temperatures are interpolated then
    edge-filled so the thermal chain never sees NaN.
    """
    cache = pd.read_csv(
        cache_path,
        usecols=["datetime", "temp", "dew", "humidity", "precip"],
        parse_dates=["datetime"],
    )
    cache = cache[cache["datetime"] <= reference_date].copy()
    cache["temp"] = cache["temp"].interpolate().ffill().bfill()
    return cache.reset_index(drop=True)


def _find_series_path(timeseries_dir: Path, asset_id: str) -> Path | None:
    """Locate ``<ASSET>_<start>_<end>.csv`` for an asset, or None if absent.

    The trailing underscore in the glob makes the match exact (``SYNTH-0001_``
    cannot match ``SYNTH-00010_``).
    """
    matches = sorted(timeseries_dir.glob(f"{asset_id}_*.csv"))
    return matches[0] if matches else None


def _load_process_history(series_path: Path) -> pd.DataFrame:
    """Load a per-asset process-temperature series (``datetime``, ``process_temperature_c``)."""
    return pd.read_csv(
        series_path,
        usecols=["datetime", "process_temperature_c"],
        parse_dates=["datetime"],
    )


def _feature_kwargs(
    row: pd.Series,
    weather_df: pd.DataFrame,
    process_history_df: pd.DataFrame,
    today: pd.Timestamp,
) -> dict[str, Any]:
    """Map a static-dataset row + its two hourly frames to feature-pipeline kwargs.

    Two static columns are renamed to the pipeline's parameter names
    (``most_prevalent_geometry_class`` -> ``geometry_class``,
    ``latest_inspection_date`` -> ``last_inspection_date``). ``asset_age`` has no
    column of its own; it is derived as whole years since commissioning. It is a
    pass-through input to the pipeline (it drives no derivation), so its exact
    value does not affect the six appended feature columns.
    """
    asset_age = (today - row["asset_commissioning_date"]).days // 365
    return {
        "asset_id": str(row["Asset"]),
        "asset_class": row["asset_class"],
        "exposure_zone": row["exposure_zone"],
        "metallurgy_family": row["metallurgy_family"],
        "asset_age": float(asset_age),
        "geometry_class": row["most_prevalent_geometry_class"],
        "geometry_complexity": row["geometry_complexity"],
        "orientation": row["orientation"],
        "shelter_flag": row["shelter_flag"],
        "tracing_system": row["tracing_system"],
        "component_diameter": float(row["component_diameter"]),
        "furnished_thickness": float(row["furnished_thickness"]),
        "insulation_material": str(row["insulation_material"]),
        "insulation_thickness": float(row["insulation_thickness"]),
        "insulation_install_date": row["insulation_install_date"],
        "coating_application_date": row["coating_application_date"],
        "coating_system": row["coating_system"],
        "last_inspection_date": row["latest_inspection_date"],
        "operating_temperature": float(row["operating_temperature"]),
        "min_operating_temperature": float(row["min_operating_temperature"]),
        "max_operating_temperature": float(row["max_operating_temperature"]),
        "avg_cycles_per_quarter": float(row["avg_cycles_per_quarter"]),
        "operation_vs_shutdown_fraction": float(row["operation_vs_shutdown_fraction"]),
        "insulation_chloride_flag": row["insulation_chloride_flag"],
        "insulation_condition": row["insulation_condition"],
        "cladding_integrity": row["cladding_integrity"],
        "last_inspection_thickness": float(row["last_inspection_thickness"]),
        "washdown_records": row["washdown_records"],
        "weather_df": weather_df,
        "process_history_df": process_history_df,
        "today": today,
    }


def append_features(
    dataset_path: Path,
    weather_dir: Path,
    timeseries_dir: Path,
    output_path: Path,
    *,
    reference_date: pd.Timestamp,
    seed: int,
) -> int:
    """Append the derived feature columns + API 583 total to the dataset and write it.

    For each asset the six feature-pipeline columns are computed first, then the
    API 583 CUI-likelihood total (which consumes two of those features) is scored
    and appended as ``api583_total_score``. A row whose features are skipped, or
    whose API 583 scoring raises, gets an empty (NaN) value in the affected
    columns rather than being dropped.

    Args:
        dataset_path: Static synthetic dataset CSV (output of ``generate.py``).
        weather_dir: Directory of per-location hourly weather caches.
        timeseries_dir: Directory of per-asset process-temperature CSVs
            (output of ``generate_timeseries.py``).
        output_path: Destination CSV (original columns + feature + API 583 columns).
        reference_date: Run "today"; drives every time-based derivation.
        seed: Run seed; reproduces the asset -> weather-cache assignment.

    Returns:
        Number of assets scored (rows with feature values written).
    """
    from lean_virtual_sensor.feature_engineering.api_583_risk.pipeline import (
        compute_api_583_likelihood,
    )
    from lean_virtual_sensor.feature_engineering.feature_pipeline import (
        compute_features_for_asset,
    )

    df = pd.read_csv(dataset_path, parse_dates=list(_DATE_COLUMNS))
    caches = _discover_weather_caches(weather_dir)
    logger.info(
        "Loaded %d assets from %s; %d weather caches in %s.",
        len(df), dataset_path.name, len(caches), weather_dir,
    )

    # Same seeded, row-positional draw as generate_timeseries.py, so each asset
    # is scored against the weather cache that generated its process series.
    assign_rng = np.random.default_rng(seed)
    cache_indices = assign_rng.integers(0, len(caches), size=len(df))

    # Read each location cache at most once.
    weather_cache: dict[Path, pd.DataFrame] = {}
    features: list[dict[str, float]] = []
    api_totals: list[int | None] = []
    n_scored = 0
    skipped: dict[str, int] = {}

    for i, (_, row) in enumerate(df.iterrows()):
        asset_id = str(row["Asset"])
        series_path = _find_series_path(timeseries_dir, asset_id)
        if series_path is None:
            skipped["no time-series file"] = skipped.get("no time-series file", 0) + 1
            features.append({})
            api_totals.append(None)
            continue

        cache_path = caches[int(cache_indices[i])]
        try:
            if cache_path not in weather_cache:
                weather_cache[cache_path] = _load_weather_cache(cache_path, reference_date)
            weather_df = weather_cache[cache_path]
            process_history_df = _load_process_history(series_path)

            result = compute_features_for_asset(
                **_feature_kwargs(row, weather_df, process_history_df, reference_date)
            )
        except (ValueError, KeyError) as exc:
            reason = str(exc).split(",")[0][:60]
            skipped[reason] = skipped.get(reason, 0) + 1
            logger.debug("Skipped %s (%s): %s", asset_id, cache_path.name, exc)
            features.append({})
            api_totals.append(None)
            continue

        features.append({col: result[col] for col in _FEATURE_COLUMNS})
        n_scored += 1

        # API 583 reuses the derived ages in ``result``; ``sweating_asset`` is the
        # only required input not echoed by the feature pipeline.
        try:
            likelihood = compute_api_583_likelihood(
                {**result, "sweating_asset": row["sweating_asset"]}
            )
            api_totals.append(int(likelihood["total"]))
        except (ValueError, KeyError) as exc:
            reason = f"api583: {str(exc).split(',')[0][:50]}"
            skipped[reason] = skipped.get(reason, 0) + 1
            logger.debug("API 583 skipped %s: %s", asset_id, exc)
            api_totals.append(None)

    feature_df = pd.DataFrame(features, columns=list(_FEATURE_COLUMNS), index=df.index)
    api_df = pd.DataFrame({_API583_TOTAL_COLUMN: api_totals}, index=df.index)
    out = pd.concat([df, feature_df, api_df], axis=1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, index=False)

    if skipped:
        total_skipped = sum(skipped.values())
        logger.info("Skipped %d asset(s): %s", total_skipped, skipped)
    logger.info("Scored %d/%d assets; wrote %s.", n_scored, len(df), output_path)
    return n_scored


def main(argv: list[str] | None = None) -> int:
    base = _inputs_generation_dir()
    config_dir = base / "config"
    default_dataset = config_dir / "outputs" / "synthetic_v1.0_seed42.csv"

    parser = argparse.ArgumentParser(
        description="Append derived CUI features to the static synthetic dataset.",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=default_dataset,
        metavar="PATH",
        help="Static synthetic dataset CSV (output of generate.py).",
    )
    parser.add_argument(
        "--weather-dir",
        type=Path,
        default=base.parent / "output",
        metavar="PATH",
        help="Directory of per-location hourly weather caches.",
    )
    parser.add_argument(
        "--timeseries-dir",
        type=Path,
        default=config_dir / "outputs" / "timeseries",
        metavar="PATH",
        help="Directory of per-asset process-temperature CSVs (generate_timeseries.py).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        metavar="PATH",
        help="Output CSV. Defaults to <dataset stem>_features.csv beside the dataset.",
    )
    parser.add_argument(
        "--generation-config",
        type=Path,
        default=config_dir / "generation_config.yaml",
        metavar="PATH",
        help="generation_config.yaml (for reference_date and seed).",
    )
    parser.add_argument(
        "--reference-date",
        type=str,
        default=None,
        metavar="YYYY-MM-DD",
        help="Override run.reference_date from generation_config.yaml.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Override run.random_seed from generation_config.yaml.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable DEBUG logging.")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if not args.dataset.is_file():
        logger.error("Static dataset not found: %s. Run generate.py first.", args.dataset)
        return 1
    if not args.generation_config.is_file():
        logger.error("Generation config not found: %s", args.generation_config)
        return 1
    if not args.timeseries_dir.is_dir():
        logger.error(
            "Time-series directory not found: %s. Run generate_timeseries.py first.",
            args.timeseries_dir,
        )
        return 1

    run_cfg = _load_run_config(args.generation_config)
    reference_date = pd.Timestamp(args.reference_date or run_cfg["reference_date"])
    seed = args.seed if args.seed is not None else int(run_cfg["random_seed"])
    output_path = args.output or args.dataset.with_name(f"{args.dataset.stem}_features.csv")

    n_scored = append_features(
        args.dataset,
        args.weather_dir,
        args.timeseries_dir,
        output_path,
        reference_date=reference_date,
        seed=seed,
    )
    return 0 if n_scored > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
