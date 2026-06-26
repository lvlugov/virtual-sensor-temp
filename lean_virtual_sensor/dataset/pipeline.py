"""Produces one dataset per config: generate → timeseries → featurise → llm_score."""

from __future__ import annotations

import json
import logging
from datetime import datetime
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


def _write_provenance(
    config: DatasetConfig, output_csv: Path, timestamp: datetime
) -> None:
    """Write JSON and Markdown provenance files alongside the dataset CSV.

    Args:
        config: Dataset configuration.
        output_csv: Path to the final dataset CSV.
        timestamp: Timestamp when the dataset was produced (ISO format).
    """
    df = pd.read_csv(output_csv)
    num_rows = len(df)

    provenance_data = {
        "name": config.name,
        "generation_config_path": str(config.generation_config_path),
        "weather_dir": str(config.weather_dir),
        "llm_config": config.llm_config,
        "raw_synthetic_inputs_name": config.raw_synthetic_inputs_name,
        "timeseries_name": config.timeseries_name,
        "featurised_name": config.featurised_name,
        "timestamp": timestamp.isoformat(),
        "num_rows": num_rows,
    }

    json_path = output_csv.parent / f"{output_csv.stem}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(provenance_data, f, indent=2)
    logger.info("Wrote provenance JSON → %s", json_path)

    md_lines = [
        f"# {config.name}",
        "",
        "## Configuration",
        f"- **name**: {config.name}",
        f"- **generation_config_path**: {config.generation_config_path}",
        f"- **weather_dir**: {config.weather_dir}",
        f"- **llm_config**: {config.llm_config}",
        f"- **raw_synthetic_inputs_name**: {config.raw_synthetic_inputs_name}",
        f"- **timeseries_name**: {config.timeseries_name}",
        f"- **featurised_name**: {config.featurised_name}",
        "",
        "## Metadata",
        f"- **timestamp**: {timestamp.isoformat()}",
        f"- **num_rows**: {num_rows}",
    ]

    md_path = output_csv.parent / f"{output_csv.stem}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
    logger.info("Wrote provenance Markdown → %s", md_path)


def _load_run_config(generation_config_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load ``run`` and ``temperature_series`` blocks from generation_config.yaml.

    Args:
        generation_config_path: Path to generation_config.yaml.

    Returns:
        Tuple of (run_block, series_block) dicts.
    """
    cfg = yaml.safe_load(generation_config_path.read_text(encoding="utf-8"))
    return cfg.get("run", {}), cfg.get("temperature_series", {})


def run_dataset_pipeline(
    config: DatasetConfig, *, data_dir: Path = Path("data"), force: bool = False
) -> Path:
    """Run all 4 steps; skip steps whose output already exists.

    Steps:
      1. generate        -> data/raw_synthetic_inputs/{raw_synthetic_inputs_name}.csv
      2. gen_timeseries  -> data/timeseries/{timeseries_name}/  (skipped if weather_dir absent)
      3. featurise       -> data/featurised/{featurised_name}.csv
      4. llm_score       -> data/datasets/{name}.csv

    Args:
        config: Dataset configuration.
        data_dir: Root data directory.
        force: If True, re-run all steps even if outputs already exist.

    Returns:
        Path to final dataset CSV.
    """
    logger.info("Running pipeline for dataset: %s", config.name)

    raw_inputs_name = config.raw_synthetic_inputs_name or config.name
    timeseries_name = config.timeseries_name or config.name
    featurised_name = config.featurised_name or config.name

    raw_csv = data_dir / "raw_synthetic_inputs" / f"{raw_inputs_name}.csv"
    timeseries_dir = data_dir / "timeseries" / timeseries_name
    featurised_csv = data_dir / "featurised" / f"{featurised_name}.csv"
    final_csv = data_dir / "datasets" / f"{config.name}.csv"

    # Step 1: generate raw synthetic inputs
    if raw_csv.exists() and not force:
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
    elif timeseries_dir.exists() and not force:
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
    if featurised_csv.exists() and not force:
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
    if final_csv.exists() and not force:
        logger.info("Step 4 (llm_score): output exists, skipping → %s", final_csv)
    else:
        logger.info("Step 4 (llm_score): running → %s", final_csv)
        score_dataset(featurised_csv, final_csv, llm_config=config.llm_config)

    _write_provenance(config, final_csv, datetime.now())

    return final_csv


def run_all_configs(
    configs: dict[str, DatasetConfig] | None = None,
    *,
    data_dir: Path = Path("data"),
    force: bool = False,
) -> list[Path]:
    """Run pipeline for every config (default: ALL_CONFIGS).

    Args:
        configs: Dict of name -> DatasetConfig. Defaults to ALL_CONFIGS.
        data_dir: Root data directory.
        force: If True, re-run all steps even if outputs already exist.

    Returns:
        List of paths to final dataset CSVs.
    """
    resolved_configs = configs if configs is not None else ALL_CONFIGS
    return [
        run_dataset_pipeline(cfg, data_dir=data_dir, force=force)
        for cfg in resolved_configs.values()
    ]
