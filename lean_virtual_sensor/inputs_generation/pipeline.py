"""
pipeline.py
===========
Orchestrates the full synthetic dataset generation run.

Steps:
    1. Load and cross-validate all four config files
    2. Initialise seeded random number generator
    3. Pre-allocate empty DataFrame (n_rows × n_columns)
    4. Assign asset_ids (SYNTH-0001 ... SYNTH-1000)
    5. Run DAG generation steps in order (see ``layer_generators`` module)
    6. Run post-generation constraint enforcement (constraints.py)
    7. Run full pytest test suite against the output DataFrame
    8. If all tests pass: write versioned CSV to outputs/
    9. If any test fails: log violations, raise, do not write output

The pipeline never writes output unless every test passes.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from lean_virtual_sensor.inputs_generation.constraints import enforce_all_constraints
from lean_virtual_sensor.inputs_generation.layer_generators import (
    generate_anchors,
    generate_dates,
    generate_geometry,
    generate_insulation_flags,
    generate_operating,
    generate_thickness_washdown,
    generate_wall_insulation,
)
from lean_virtual_sensor.inputs_generation.schema_loader import GeneratorConfig, load_all_configs

logger = logging.getLogger(__name__)


def run_pipeline(
    config_path: Path,
    *,
    output_path_override: Path | None = None,
    write_output: bool = True,
) -> bool:
    """Run the full generation pipeline.

    Args:
        config_path: Path to generation_config.yaml.
        output_path_override: If set, write CSV here instead of ``run.output_path``.
        write_output: If false, do not write a CSV file after generation.

    Returns:
        True if generation succeeded and output was written (when requested), False otherwise.
    """
    config_path = config_path.resolve()
    if not config_path.is_file():
        logger.error("Generation config not found: %s", config_path)
        return False

    logger.info("Using generation config: %s", config_path)
    config_dir = config_path.parent
    cfg = load_all_configs(config_dir, generation_config_path=config_path)

    run = cfg.generation["run"]
    n_rows = int(run["n_rows"])
    seed = int(run["random_seed"])
    rng = np.random.default_rng(seed)
    logger.debug("Seeded RNG with random_seed=%s", seed)

    df = _build_empty_dataframe(n_rows, cfg, rng)
    df = _assign_asset_ids(df)
    df = generate_anchors(df, cfg, rng)
    df = generate_geometry(df, cfg, rng)
    df = generate_wall_insulation(df, cfg, rng)
    df = generate_dates(df, cfg, rng)
    df = generate_operating(df, cfg, rng)
    df = generate_insulation_flags(df, cfg, rng)
    df = generate_thickness_washdown(df, cfg, rng)

    df, correction_log = enforce_all_constraints(df, cfg)
    if correction_log:
        logger.info("Constraint pass corrections: %s", correction_log)

    output_rel = Path(str(run["output_path"]))
    if output_path_override is not None:
        output_path = output_path_override.resolve()
    else:
        output_path = (
            output_rel.resolve()
            if output_rel.is_absolute()
            else (config_dir / output_rel).resolve()
        )

    halt_on_tests = bool(run.get("halt_on_test_failure", True))
    tmp_path: Path | None = None
    try:
        if halt_on_tests:
            fd, tmp_name = tempfile.mkstemp(suffix=".csv", text=True)
            os.close(fd)
            tmp_path = Path(tmp_name)
            df.to_csv(tmp_path, index=False)
            if not _run_test_suite(tmp_path):
                logger.error("Pytest gate failed; output not written to %s", output_path)
                return False
        else:
            logger.warning("halt_on_test_failure is false; skipping pytest gate")
    finally:
        if tmp_path is not None and tmp_path.is_file():
            tmp_path.unlink(missing_ok=True)

    if write_output:
        _write_output(df, output_path)
        logger.info(
            "Pipeline complete: %d rows, %d columns → %s",
            len(df),
            len(df.columns),
            output_path,
        )
    else:
        logger.info(
            "Pipeline complete: %d rows, %d columns (output not written)",
            len(df),
            len(df.columns),
        )
    return True


def _build_empty_dataframe(
    n_rows: int,
    config: GeneratorConfig,
    _rng: np.random.Generator,
) -> pd.DataFrame:
    """Pre-allocate an empty DataFrame with correct column order.

    ``_rng`` is reserved for future stochastic defaults; layers will use it.
    """
    variables = config.schema.get("variables")
    if not isinstance(variables, dict) or not variables:
        raise ValueError("schema must contain non-empty 'variables'")

    # Asset is excluded from schema variables but is the first output column.
    cols = ["Asset"] + list(variables.keys())
    return pd.DataFrame(index=range(n_rows), columns=cols)


def _assign_asset_ids(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Assign sequential synthetic asset IDs: SYNTH-0001 ... SYNTH-N."""
    result = dataframe.copy()
    row_count = len(result)
    result["Asset"] = [f"SYNTH-{i:04d}" for i in range(1, row_count + 1)]
    return result


def _repo_root() -> Path:
    """Repository root (parent of ``lean_virtual_sensor``)."""
    return Path(__file__).resolve().parent.parent.parent


def _run_test_suite(dataset_csv: Path) -> bool:
    """Run pytest on ``tests/lean_virtual_sensor/inputs_generation`` with ``--dataset``."""
    repo_root = _repo_root()
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/lean_virtual_sensor/inputs_generation",
        f"--dataset={dataset_csv}",
        "-q",
        "--tb=line",
    ]
    completed = subprocess.run(cmd, cwd=repo_root, check=False)
    return completed.returncode == 0


def _write_output(df: pd.DataFrame, output_path: Path) -> None:
    """Write the final DataFrame to the versioned output CSV."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    logger.info("Output written to %s (%d rows)", output_path, len(df))
