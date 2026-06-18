"""Tests for ``generate_dates`` and ``generate_operating`` (layers 4–5)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from generation_helpers import parse_commissioning_timestamp
from layer_generators import (
    generate_anchors,
    generate_dates,
    generate_geometry,
    generate_operating,
    generate_wall_insulation,
)
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


def _dataframe_through_layer5(cfg, *, n_rows: int = 200, seed: int = 7):
    rng = np.random.default_rng(seed)
    dataframe = _build_empty_dataframe(n_rows, cfg, rng)
    dataframe = _assign_asset_ids(dataframe)
    dataframe = generate_anchors(dataframe, cfg, rng)
    dataframe = generate_geometry(dataframe, cfg, rng)
    dataframe = generate_wall_insulation(dataframe, cfg, rng)
    dataframe = generate_dates(dataframe, cfg, rng)
    dataframe = generate_operating(dataframe, cfg, rng)
    return dataframe


def test_dates_respect_commissioning_and_reference(cfg):
    dataframe = _dataframe_through_layer5(cfg)
    reference = pd.Timestamp(cfg.generation["run"]["reference_date"]).normalize()

    for _, row in dataframe.iterrows():
        commissioning = parse_commissioning_timestamp(row["asset_commissioning_date"])
        for column in (
            "insulation_install_date",
            "coating_application_date",
            "latest_inspection_date",
        ):
            event = pd.Timestamp(str(row[column])).normalize()
            assert event <= reference
            assert event >= commissioning.normalize()


def test_operating_temperature_triplet_and_schema_bounds(cfg):
    dataframe = _dataframe_through_layer5(cfg)
    op_lo, op_hi = cfg.schema["variables"]["operating_temperature"]["range"]
    op_lo, op_hi = float(op_lo), float(op_hi)

    for _, row in dataframe.iterrows():
        op = float(row["operating_temperature"])
        t_min = float(row["min_operating_temperature"])
        t_max = float(row["max_operating_temperature"])
        assert op_lo <= op <= op_hi
        assert op_lo <= t_min <= op_hi
        assert op_lo <= t_max <= op_hi
        assert t_min <= op <= t_max


def _is_wide_swing_row(row: pd.Series) -> bool:
    """Wide-swing table row: hot operating ~250 °C with sub-ambient min."""
    op = float(row["operating_temperature"])
    t_min = float(row["min_operating_temperature"])
    return 245.0 <= op <= 255.0 and t_min <= -5.0


def test_cold_service_identified_by_negative_operating_temperature(cfg):
    dataframe = _dataframe_through_layer5(cfg, n_rows=1000, seed=42)
    cold_eligible = {"PIPE", "PRESSURE_VESSEL", "STORAGE_TANK"}
    cold_rows = dataframe[
        (dataframe["operating_temperature"] < 0) & (~dataframe.apply(_is_wide_swing_row, axis=1))
    ]
    assert not cold_rows.empty
    assert set(cold_rows["asset_class"]).issubset(cold_eligible)


def test_wide_swing_fraction_near_five_percent(cfg):
    dataframe = _dataframe_through_layer5(cfg, n_rows=1000, seed=42)
    wide_count = int(dataframe.apply(_is_wide_swing_row, axis=1).sum())
    assert 40 <= wide_count <= 60


def test_reactor_on_stream_fraction_below_pipe(cfg):
    dataframe = _dataframe_through_layer5(cfg, n_rows=1000, seed=42)
    reactor_median = float(
        dataframe.loc[
            dataframe["asset_class"] == "REACTOR", "operation_vs_shutdown_fraction"
        ].median()
    )
    pipe_median = float(
        dataframe.loc[dataframe["asset_class"] == "PIPE", "operation_vs_shutdown_fraction"].median()
    )
    assert reactor_median < pipe_median


def test_storage_tank_cycles_mostly_low(cfg):
    dataframe = _dataframe_through_layer5(cfg, n_rows=1000, seed=42)
    tank_cycles = dataframe.loc[
        dataframe["asset_class"] == "STORAGE_TANK", "avg_cycles_per_quarter"
    ]
    assert not tank_cycles.empty
    assert float(tank_cycles.median()) <= 2.0


def test_avg_cycles_within_schema_and_tracing_is_allowed_value(cfg):
    dataframe = _dataframe_through_layer5(cfg)
    cycle_lo, cycle_hi = cfg.schema["variables"]["avg_cycles_per_quarter"]["range"]
    tracing_allowed = set(cfg.schema["variables"]["tracing_system"]["allowed_values"])

    for _, row in dataframe.iterrows():
        cycles = int(row["avg_cycles_per_quarter"])
        assert int(cycle_lo) <= cycles <= int(cycle_hi)
        assert row["tracing_system"] in tracing_allowed
