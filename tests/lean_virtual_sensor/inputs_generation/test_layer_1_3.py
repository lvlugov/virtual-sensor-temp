"""Tests for the first three DAG generation steps (anchors → geometry → wall/insulation)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from layer_generators import generate_anchors, generate_geometry, generate_wall_insulation
from pipeline import _assign_asset_ids, _build_empty_dataframe
from schema_loader import load_all_configs


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


def _run_first_three_dag_layers(cfg, *, n_rows: int = 1000, seed: int = 42):
    rng = np.random.default_rng(seed)
    dataframe = _build_empty_dataframe(n_rows, cfg, rng)
    dataframe = _assign_asset_ids(dataframe)
    dataframe = generate_anchors(dataframe, cfg, rng)
    dataframe = generate_geometry(dataframe, cfg, rng)
    dataframe = generate_wall_insulation(dataframe, cfg, rng)
    return dataframe


def test_anchors_match_configured_class_counts(cfg):
    dataframe = _run_first_three_dag_layers(cfg)
    proportions = cfg.generation["asset_class_proportions"]
    for asset_class_key, expected_rows in proportions.items():
        actual = (dataframe["asset_class"] == asset_class_key).sum()
        assert int(actual) == int(expected_rows), (
            f"{asset_class_key}: expected {expected_rows} rows, got {actual}"
        )


def test_anchors_respect_schema_categoricals_and_asset_age(cfg):
    variables = cfg.schema["variables"]
    exposure_allowed = set(variables["exposure_zone"]["allowed_values"])
    metallurgy_allowed = set(variables["metallurgy_family"]["allowed_values"])
    dataframe = _run_first_three_dag_layers(cfg)
    assert set(dataframe["exposure_zone"].unique()).issubset(exposure_allowed)
    assert set(dataframe["metallurgy_family"].unique()).issubset(metallurgy_allowed)
    age_low, age_high = variables["asset_age"]["range"]
    assert dataframe["asset_age"].between(int(age_low), int(age_high)).all()


def test_geometry_columns_respect_asset_class_tables(cfg):
    asset_class_config = cfg.asset_class
    dataframe = _run_first_three_dag_layers(cfg)
    for _, row in dataframe.iterrows():
        asset_class_key = row["asset_class"]
        class_entry = asset_class_config[asset_class_key]
        allowed_geometry = set(class_entry["geometry_class_allowed"])
        assert row["geometry_class"] in allowed_geometry
        assert row["geometry_complexity"] in class_entry["geometry_complexity_weights"]
        assert row["orientation"] in class_entry["orientation_weights"]


def test_wall_and_insulation_columns_respect_schema_and_class_ranges(cfg):
    variables = cfg.schema["variables"]
    insulation_material_allowed = set(variables["insulation_material"]["allowed_values"])
    insulation_thickness_low, insulation_thickness_high = variables["insulation_thickness"]["range"]
    asset_class_config = cfg.asset_class
    dataframe = _run_first_three_dag_layers(cfg)
    for _, row in dataframe.iterrows():
        asset_class_key = row["asset_class"]
        class_entry = asset_class_config[asset_class_key]
        diameter_min = float(class_entry["component_diameter"]["min"])
        diameter_max = float(class_entry["component_diameter"]["max"])
        wall_min = float(class_entry["furnished_thickness"]["min"])
        wall_max = float(class_entry["furnished_thickness"]["max"])
        assert diameter_min <= row["component_diameter"] <= diameter_max
        assert wall_min <= row["furnished_thickness"] <= wall_max
        assert row["insulation_material"] in insulation_material_allowed
        assert float(insulation_thickness_low) <= row["insulation_thickness"] <= float(
            insulation_thickness_high
        )


def test_anchors_when_dataframe_row_count_differs_from_yaml_totals(cfg):
    """Scaffold may use fewer rows than ``asset_class_proportions`` (e.g. fast tests)."""
    rng = np.random.default_rng(123)
    n = 50
    dataframe = _build_empty_dataframe(n, cfg, rng)
    dataframe = _assign_asset_ids(dataframe)
    dataframe = generate_anchors(dataframe, cfg, rng)
    assert len(dataframe) == n
    assert dataframe["asset_class"].notna().all()
    allowed = set(cfg.generation["asset_class_proportions"])
    assert set(dataframe["asset_class"]).issubset(allowed)
