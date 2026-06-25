#!/usr/bin/env python3
"""Population runner: one process-temperature time-series CSV per asset.

This is the caller that :func:`temperature_series_driver.generate_asset_series`
documents but deliberately does not provide. It owns everything around the
per-asset core: it loads the static synthetic dataset, sources each asset's
hourly ambient series from the cached weather in ``output/``, loops the whole
population, and writes one ``datetime, process_temperature_c`` CSV per asset.

Run order (see ``docs/temperature_series_decisions_methodology.md``)::

    1. python lean_virtual_sensor/inputs_generation/generate.py
         -> writes the static dataset: outputs/synthetic_v{ver}_seed{seed}.csv
    2. python lean_virtual_sensor/inputs_generation/generate_timeseries.py
         -> writes outputs/timeseries/<ASSET>_<start>_<end>.csv   (this script)

Ambient assignment
------------------
The static dataset carries no location, so each asset is assigned one of the
cached weather locations by a **seeded draw** (``run.random_seed`` from
generation_config.yaml). The draw is over the asset's row position, so the
asset -> location mapping is fully deterministic and independent of which
assets get skipped. The ``INDEX.csv`` manifest in the weather directory is
intentionally not used.

Each asset's ambient is the trailing ``window_days`` (90 d = 2,160 h) of its
location's cache, ending on or before the run ``reference_date`` so the series
lines up with the "today" the static dataset was generated against.

Out-of-scope assets
-------------------
Assets whose metallurgy is out of scope (``NICKEL_ALLOY`` / ``OTHER`` — no
metal rho/c entry) or whose geometry the tau calculation rejects are logged
and skipped; they are never written.
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


# Static-dataset column -> generate_asset_series keyword. The five thermal and
# cycle scalars share their names; the three geometry columns are renamed to the
# driver's millimetre-suffixed parameters.
_FIELD_MAP: dict[str, str] = {
    "operating_temperature": "operating_temperature",
    "min_operating_temperature": "min_operating_temperature",
    "max_operating_temperature": "max_operating_temperature",
    "avg_cycles_per_quarter": "avg_cycles_per_quarter",
    "operation_vs_shutdown_fraction": "operation_vs_shutdown_fraction",
    "component_diameter": "outer_diameter_mm",
    "furnished_thickness": "wall_thickness_mm",
    "insulation_thickness": "insulation_thickness_mm",
    "insulation_material": "insulation_material",
    "metallurgy_family": "metallurgy_family",
}


def _inputs_generation_dir() -> Path:
    return Path(__file__).resolve().parent


def _load_run_and_series_config(
    generation_config_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read the ``run`` and ``temperature_series`` blocks from generation_config.yaml."""
    cfg = yaml.safe_load(generation_config_path.read_text(encoding="utf-8"))
    if not isinstance(cfg, dict) or "run" not in cfg or "temperature_series" not in cfg:
        raise ValueError(
            f"{generation_config_path} must contain 'run' and 'temperature_series' blocks."
        )
    return cfg["run"], cfg["temperature_series"]


def _discover_weather_caches(weather_dir: Path) -> list[Path]:
    """List per-location weather-cache CSVs, sorted for a stable assignment order.

    Excludes the ``INDEX.csv`` manifest and any ``sample_*.csv`` files.
    """
    caches = [
        p
        for p in sorted(weather_dir.glob("*.csv"))
        if p.name not in _WEATHER_SKIP_EXACT
        and not p.name.startswith(_WEATHER_SKIP_PREFIX)
    ]
    if not caches:
        raise FileNotFoundError(
            f"No per-location weather caches found in {weather_dir}. "
            f"Expected files like 'sitech_europe.csv' written by "
            f"external_temperature.fetch_bulk_to_disk."
        )
    return caches


def _load_ambient_window(
    cache_path: Path,
    reference_date: pd.Timestamp,
    window_hours: int,
) -> pd.DataFrame:
    """Load a location cache and return the trailing ``window_hours`` ending <= ref date.

    Returns a ``datetime, temp`` DataFrame. Missing temperatures are
    interpolated (then edge-filled) so the thermal chain never sees NaN.

    Raises:
        ValueError: If fewer than ``window_hours`` hourly rows fall on or before
            ``reference_date``.
    """
    cache = pd.read_csv(cache_path, usecols=["datetime", "temp"], parse_dates=["datetime"])
    cache = cache[cache["datetime"] <= reference_date]
    if len(cache) < window_hours:
        raise ValueError(
            f"{cache_path.name}: only {len(cache)} hourly rows on/before "
            f"{reference_date.date()}, need >= {window_hours}."
        )
    window = cache.iloc[-window_hours:].copy()
    window["temp"] = window["temp"].interpolate().ffill().bfill()
    return window.reset_index(drop=True)


def _series_filename(asset_id: str, ambient: pd.DataFrame) -> str:
    """``<ASSET>_<start>_<end>.csv`` from the ambient window's first/last dates."""
    start = pd.Timestamp(ambient["datetime"].iloc[0]).date()
    end = pd.Timestamp(ambient["datetime"].iloc[-1]).date()
    return f"{asset_id}_{start}_{end}.csv"


def _asset_kwargs(row: pd.Series) -> dict[str, Any]:
    """Map a static-dataset row to ``generate_asset_series`` keyword arguments."""
    kwargs: dict[str, Any] = {}
    for src, dst in _FIELD_MAP.items():
        kwargs[dst] = row[src]
    kwargs["avg_cycles_per_quarter"] = int(kwargs["avg_cycles_per_quarter"])
    kwargs["operation_vs_shutdown_fraction"] = float(kwargs["operation_vs_shutdown_fraction"])
    for key in (
        "operating_temperature",
        "min_operating_temperature",
        "max_operating_temperature",
        "outer_diameter_mm",
        "wall_thickness_mm",
        "insulation_thickness_mm",
    ):
        kwargs[key] = float(kwargs[key])
    kwargs["insulation_material"] = str(kwargs["insulation_material"])
    kwargs["metallurgy_family"] = str(kwargs["metallurgy_family"])
    return kwargs


def generate_population_series(
    dataset_path: Path,
    weather_dir: Path,
    output_dir: Path,
    *,
    reference_date: pd.Timestamp,
    seed: int,
    series_config: dict[str, Any],
) -> int:
    """Generate and write one time-series CSV per in-scope asset.

    Args:
        dataset_path: Static synthetic dataset CSV (output of ``generate.py``).
        weather_dir: Directory of per-location hourly weather caches.
        output_dir: Destination for the per-asset time-series CSVs.
        reference_date: Run "today"; each ambient window ends on/before this date.
        seed: Run seed; drives both the asset->location draw and the per-asset noise.
        series_config: The ``temperature_series`` config block.

    Returns:
        Number of time-series CSVs written.
    """
    from temperature_series_driver import generate_asset_series

    df = pd.read_csv(dataset_path)
    window_hours = int(series_config["window_days"]) * 24
    caches = _discover_weather_caches(weather_dir)
    logger.info(
        "Loaded %d assets from %s; %d weather caches in %s.",
        len(df), dataset_path.name, len(caches), weather_dir,
    )

    # Seeded location assignment, indexed by row position so it is stable
    # regardless of which assets are later skipped.
    assign_rng = np.random.default_rng(seed)
    cache_indices = assign_rng.integers(0, len(caches), size=len(df))

    output_dir.mkdir(parents=True, exist_ok=True)

    # Cache ambient windows by location so a popular location is read once.
    ambient_cache: dict[Path, pd.DataFrame] = {}
    n_written = 0
    skipped: dict[str, int] = {}

    for i, (_, row) in enumerate(df.iterrows()):
        asset_id = str(row["Asset"])
        cache_path = caches[int(cache_indices[i])]
        try:
            if cache_path not in ambient_cache:
                ambient_cache[cache_path] = _load_ambient_window(
                    cache_path, reference_date, window_hours
                )
            ambient = ambient_cache[cache_path]

            # Independent, reproducible noise stream per asset.
            rng = np.random.default_rng([seed, i])
            series = generate_asset_series(
                **_asset_kwargs(row),
                ambient=ambient,
                config=series_config,
                rng=rng,
            )
        except ValueError as exc:
            reason = str(exc).split(",")[0][:60]
            skipped[reason] = skipped.get(reason, 0) + 1
            logger.debug("Skipped %s (%s): %s", asset_id, cache_path.name, exc)
            continue

        series.to_csv(output_dir / _series_filename(asset_id, ambient), index=False)
        n_written += 1

    if skipped:
        total_skipped = sum(skipped.values())
        logger.info("Skipped %d asset(s): %s", total_skipped, skipped)
    logger.info("Wrote %d time-series CSV(s) to %s.", n_written, output_dir)
    return n_written


def main(argv: list[str] | None = None) -> int:
    base = _inputs_generation_dir()
    config_dir = base / "config"

    parser = argparse.ArgumentParser(
        description="Generate per-asset process-temperature time-series CSVs.",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=config_dir / "outputs" / "synthetic_v1.0_seed42.csv",
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
        "--output-dir",
        type=Path,
        default=config_dir / "outputs" / "timeseries",
        metavar="PATH",
        help="Destination directory for the per-asset time-series CSVs.",
    )
    parser.add_argument(
        "--generation-config",
        type=Path,
        default=config_dir / "generation_config.yaml",
        metavar="PATH",
        help="generation_config.yaml (for reference_date, seed, temperature_series).",
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
        logger.error(
            "Static dataset not found: %s. Run generate.py first.", args.dataset
        )
        return 1
    if not args.generation_config.is_file():
        logger.error("Generation config not found: %s", args.generation_config)
        return 1

    run_cfg, series_cfg = _load_run_and_series_config(args.generation_config)
    reference_date = pd.Timestamp(args.reference_date or run_cfg["reference_date"])
    seed = args.seed if args.seed is not None else int(run_cfg["random_seed"])

    n_written = generate_population_series(
        args.dataset,
        args.weather_dir,
        args.output_dir,
        reference_date=reference_date,
        seed=seed,
        series_config=series_cfg,
    )
    return 0 if n_written > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
