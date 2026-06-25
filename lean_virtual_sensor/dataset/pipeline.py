"""Orchestrates the four-step dataset pipeline: generate → timeseries → featurise → llm_score."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from lean_virtual_sensor.dataset.configs import ALL_CONFIGS, DatasetConfig
from lean_virtual_sensor.dataset.featurise import featurise_inventory
from lean_virtual_sensor.dataset.llm_scoring import score_dataset
from lean_virtual_sensor.inputs_generation.generate_timeseries import generate_population_series
from lean_virtual_sensor.inputs_generation.pipeline import run_pipeline

logger = logging.getLogger(__name__)


def _load_run_config(generation_config_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load ``run`` and ``temperature_series`` blocks from generation_config.yaml.

    Args:
        generation_config_path: Path to generation_config.yaml.

    Returns:
        Tuple of (run_block, series_block) dicts.
    """
    cfg = yaml.safe_load(generation_config_path.read_text(encoding="utf-8"))
    return cfg.get("run", {}), cfg.get("temperature_series", {})


def run_dataset_pipeline(config: DatasetConfig, *, data_dir: Path = Path("data")) -> Path:
    """Run all 4 steps; skip steps whose output already exists.

    Steps:
      1. generate        -> data/raw_synthetic_inputs/{raw_synthetic_inputs_name}.csv
      2. gen_timeseries  -> data/timeseries/{timeseries_name}/  (skipped if weather_dir absent)
      3. featurise       -> data/featurised/{featurised_name}.csv
      4. llm_score       -> data/datasets/{name}.csv

    Args:
        config: Dataset configuration.
        data_dir: Root data directory.

    Returns:
        Path to final dataset CSV.
    """
    raw_inputs_name = config.raw_synthetic_inputs_name or config.name
    timeseries_name = config.timeseries_name or config.name
    featurised_name = config.featurised_name or config.name

    raw_csv = data_dir / "raw_synthetic_inputs" / f"{raw_inputs_name}.csv"
    timeseries_dir = data_dir / "timeseries" / timeseries_name
    featurised_csv = data_dir / "featurised" / f"{featurised_name}.csv"
    final_csv = data_dir / "datasets" / f"{config.name}.csv"

    # Step 1: generate raw synthetic inputs
    if raw_csv.exists():
        logger.info("Step 1 (generate): output exists, skipping → %s", raw_csv)
    else:
        logger.info("Step 1 (generate): running → %s", raw_csv)
        raw_csv.parent.mkdir(parents=True, exist_ok=True)
        success = run_pipeline(config.generation_config_path, output_path_override=raw_csv)
        if not success:
            raise RuntimeError(f"Generation pipeline failed for config: {config.name}")

    run_block, series_block = _load_run_config(config.generation_config_path)
    reference_date_str = str(run_block["reference_date"])
    seed = int(run_block["random_seed"])

    # Step 2: generate per-asset timeseries (skip entirely if weather cache is absent)
    if not config.weather_dir.exists():
        logger.warning(
            "Step 2 (gen_timeseries): weather_dir absent (%s), skipping", config.weather_dir
        )
    elif timeseries_dir.exists():
        logger.info("Step 2 (gen_timeseries): output exists, skipping → %s", timeseries_dir)
    else:
        logger.info("Step 2 (gen_timeseries): running → %s", timeseries_dir)
        generate_population_series(
            raw_csv,
            config.weather_dir,
            timeseries_dir,
            reference_date=pd.Timestamp(reference_date_str),
            seed=seed,
            series_config=series_block,
        )

    # Step 3: featurise
    if featurised_csv.exists():
        logger.info("Step 3 (featurise): output exists, skipping → %s", featurised_csv)
    else:
        logger.info("Step 3 (featurise): running → %s", featurised_csv)
        featurise_inventory(
            raw_csv,
            timeseries_dir,
            config.weather_dir,
            featurised_csv,
            reference_date=reference_date_str,
            seed=seed,
        )

    # Step 4: LLM scoring
    if final_csv.exists():
        logger.info("Step 4 (llm_score): output exists, skipping → %s", final_csv)
    else:
        logger.info("Step 4 (llm_score): running → %s", final_csv)
        score_dataset(featurised_csv, final_csv, llm_config=config.llm_config)

    return final_csv


def run_all_configs(
    configs: dict[str, DatasetConfig] | None = None, **kwargs
) -> list[Path]:
    """Run pipeline for every config (default: ALL_CONFIGS).

    Args:
        configs: Dict of name -> DatasetConfig. Defaults to ALL_CONFIGS.
        **kwargs: Passed through to run_dataset_pipeline.

    Returns:
        List of paths to final dataset CSVs.
    """
    resolved_configs = configs if configs is not None else ALL_CONFIGS
    return [run_dataset_pipeline(cfg, **kwargs) for cfg in resolved_configs.values()]
