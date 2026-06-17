"""Population-level acceptance tests for static temperature fields (spec Section 2)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from constraints import enforce_all_constraints
from layer_generators import (
    generate_anchors,
    generate_dates,
    generate_geometry,
    generate_insulation_flags,
    generate_operating,
    generate_thickness_washdown,
    generate_wall_insulation,
)
from pipeline import _assign_asset_ids, _build_empty_dataframe
from schema_loader import load_all_configs
from temperature_population_checks import assert_temperature_population_acceptance


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise RuntimeError("Could not locate repository root")


CONFIG_DIR = _repo_root() / "lean_virtual_sensor" / "inputs_generation" / "config"


@pytest.fixture
def cfg():
    return load_all_configs(CONFIG_DIR)


def _full_pipeline_dataframe(cfg, *, seed: int = 42):
    """Generate through all layers and constraint enforcement (production path)."""
    n_rows = int(cfg.generation["run"]["n_rows"])
    rng = np.random.default_rng(seed)
    dataframe = _build_empty_dataframe(n_rows, cfg, rng)
    dataframe = _assign_asset_ids(dataframe)
    dataframe = generate_anchors(dataframe, cfg, rng)
    dataframe = generate_geometry(dataframe, cfg, rng)
    dataframe = generate_wall_insulation(dataframe, cfg, rng)
    dataframe = generate_dates(dataframe, cfg, rng)
    dataframe = generate_operating(dataframe, cfg, rng)
    dataframe = generate_insulation_flags(dataframe, cfg, rng)
    dataframe = generate_thickness_washdown(dataframe, cfg, rng)
    dataframe, _corrections = enforce_all_constraints(dataframe, cfg)
    return dataframe


@pytest.fixture
def population_df(cfg):
    return _full_pipeline_dataframe(cfg, seed=42)


def test_temperature_population_acceptance_on_full_pipeline(population_df, cfg):
    assert_temperature_population_acceptance(
        population_df, cfg.operating_temperature
    )


def test_constraints_do_not_break_temperature_triplet(population_df):
    assert (
        population_df["min_operating_temperature"]
        <= population_df["operating_temperature"]
    ).all()
    assert (
        population_df["operating_temperature"]
        <= population_df["max_operating_temperature"]
    ).all()
