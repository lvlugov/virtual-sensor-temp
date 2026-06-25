"""Tests for component diameter and wall thickness sampling (SME geometry scheme)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from lean_virtual_sensor.inputs_generation.generation_helpers import (
    sample_component_geometry,
    sample_coupled_wall_thickness,
    sample_nps_catalog_geometry,
    sample_triangular_diameter,
)
from lean_virtual_sensor.inputs_generation.layer_generators import (
    generate_anchors,
    generate_geometry,
    generate_wall_insulation,
)
from lean_virtual_sensor.inputs_generation.pipeline import _assign_asset_ids, _build_empty_dataframe
from lean_virtual_sensor.inputs_generation.schema_loader import load_all_configs


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


def _pipe_catalog_pairs(cfg) -> set[tuple[float, float]]:
    catalog = cfg.conditional_rules["geometry_standards"]["pipe_nps"]["nps_catalog"]
    return {(round(float(row["od_mm"]), 1), round(float(row["wall_mm"]), 2)) for row in catalog}


def test_pipe_geometry_from_nps_catalog(cfg):
    dataframe = _run_first_three_dag_layers(cfg)
    catalog_pairs = _pipe_catalog_pairs(cfg)
    pipe_rows = dataframe[dataframe["asset_class"] == "PIPE"]
    assert not pipe_rows.empty
    for _, row in pipe_rows.iterrows():
        pair = (float(row["component_diameter"]), float(row["furnished_thickness"]))
        assert pair in catalog_pairs


def test_pipe_diameter_skewed_small(cfg):
    dataframe = _run_first_three_dag_layers(cfg, seed=42)
    pipe_od = dataframe.loc[dataframe["asset_class"] == "PIPE", "component_diameter"]
    assert float(pipe_od.median()) < 150.0


def test_non_pipe_wall_coupled_to_diameter(cfg):
    dataframe = _run_first_three_dag_layers(cfg, seed=42)
    non_pipe_classes = [key for key in cfg.asset_class if key != "PIPE"]
    for asset_class_key in non_pipe_classes:
        class_cfg = cfg.asset_class[asset_class_key]
        geometry_sampling = class_cfg["geometry_sampling"]
        class_rows = dataframe[dataframe["asset_class"] == asset_class_key]
        assert not class_rows.empty

        if geometry_sampling["method"] == "triangular_fixed_wall":
            wall_min = max(
                float(geometry_sampling["wall"]["min"]),
                float(class_cfg["furnished_thickness"]["min"]),
            )
            wall_max = min(
                float(geometry_sampling["wall"]["max"]),
                float(class_cfg["furnished_thickness"]["max"]),
            )
            for _, row in class_rows.iterrows():
                assert wall_min <= row["furnished_thickness"] <= wall_max
            continue

        wall_cfg = geometry_sampling["wall"]
        t_min = float(wall_cfg["t_over_d_min"])
        t_max = float(wall_cfg["t_over_d_max"])
        clamp_min = max(
            float(wall_cfg["clamp_min"]), float(class_cfg["furnished_thickness"]["min"])
        )
        clamp_max = min(
            float(wall_cfg["clamp_max"]), float(class_cfg["furnished_thickness"]["max"])
        )
        for _, row in class_rows.iterrows():
            diameter = float(row["component_diameter"])
            wall = float(row["furnished_thickness"])
            assert clamp_min <= wall <= clamp_max
            expected_min = max(clamp_min, t_min * diameter)
            expected_max = min(clamp_max, t_max * diameter)
            if expected_min > expected_max:
                # Small diameters: dictionary/class clamp_min can exceed t/D max band.
                assert abs(wall - clamp_min) <= 0.02
            else:
                assert expected_min - 0.02 <= wall <= expected_max + 0.02


def test_geometry_within_dictionary_bounds(cfg):
    asset_class_config = cfg.asset_class
    dataframe = _run_first_three_dag_layers(cfg, seed=123)
    for _, row in dataframe.iterrows():
        asset_class_key = row["asset_class"]
        class_entry = asset_class_config[asset_class_key]
        diameter_min = float(class_entry["component_diameter"]["min"])
        diameter_max = float(class_entry["component_diameter"]["max"])
        wall_min = float(class_entry["furnished_thickness"]["min"])
        wall_max = float(class_entry["furnished_thickness"]["max"])
        assert diameter_min <= row["component_diameter"] <= diameter_max
        assert wall_min <= row["furnished_thickness"] <= wall_max


def test_sample_nps_catalog_geometry_unit(cfg):
    rng = np.random.default_rng(0)
    pipe_nps = cfg.conditional_rules["geometry_standards"]["pipe_nps"]
    catalog_pairs = _pipe_catalog_pairs(cfg)
    for _ in range(200):
        od_mm, wall_mm = sample_nps_catalog_geometry(rng, pipe_nps)
        assert (round(od_mm, 1), round(wall_mm, 2)) in catalog_pairs


def test_sample_triangular_diameter_respects_bounds():
    rng = np.random.default_rng(1)
    samples = [sample_triangular_diameter(rng, 100.0, 300.0, 500.0) for _ in range(500)]
    assert min(samples) >= 100.0
    assert max(samples) <= 500.0


def test_sample_coupled_wall_thickness_respects_clamp():
    rng = np.random.default_rng(2)
    for _ in range(100):
        wall = sample_coupled_wall_thickness(rng, 2000.0, 0.008, 0.014, 6.0, 120.0)
        assert 6.0 <= wall <= 120.0


def test_sample_component_geometry_pipe_vs_non_pipe(cfg):
    rng = np.random.default_rng(3)
    pipe_cfg = cfg.asset_class["PIPE"]
    od_mm, wall_mm = sample_component_geometry("PIPE", pipe_cfg, cfg.conditional_rules, rng)
    assert (round(od_mm, 1), round(wall_mm, 2)) in _pipe_catalog_pairs(cfg)

    pv_cfg = cfg.asset_class["PRESSURE_VESSEL"]
    diameter, wall = sample_component_geometry(
        "PRESSURE_VESSEL", pv_cfg, cfg.conditional_rules, rng
    )
    assert 500.0 <= diameter <= 4000.0
    assert 6.0 <= wall <= 120.0
