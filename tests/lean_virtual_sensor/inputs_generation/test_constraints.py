"""
test_constraints.py
===================
Inter-variable constraints from schema.yaml and methodology §4.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from lean_virtual_sensor.inputs_generation.constraints import (
    _clamp_and_round_numerics,
    _enforce_temperature_triplet,
)
from lean_virtual_sensor.inputs_generation.generation_helpers import years_between_timestamps
from lean_virtual_sensor.inputs_generation.layer_generators import (
    generate_anchors,
    generate_dates,
    generate_geometry,
    generate_operating,
    generate_wall_insulation,
)
from lean_virtual_sensor.inputs_generation.pipeline import _assign_asset_ids, _build_empty_dataframe
from lean_virtual_sensor.inputs_generation.schema_loader import load_all_configs


def _config_dir() -> Path:
    return (
        Path(__file__).resolve().parents[3] / "lean_virtual_sensor" / "inputs_generation" / "config"
    )


def _reference_ts(gen_config: dict) -> pd.Timestamp:
    return pd.Timestamp(str(gen_config["run"]["reference_date"])).normalize()


def test_temperature_triplet_ordering(df):
    """min_op_temp <= op_temp <= max_op_temp for every row."""
    if df is None:
        pytest.skip("No dataset provided")
    assert (df["min_operating_temperature"] <= df["operating_temperature"]).all()
    assert (df["operating_temperature"] <= df["max_operating_temperature"]).all()


def test_enforce_constraints_on_operating_layer_output():
    """Temperature triplet repair and numeric clamp on layer 5 output."""
    cfg = load_all_configs(_config_dir())
    rng = np.random.default_rng(99)
    n_rows = 200
    dataframe = _build_empty_dataframe(n_rows, cfg, rng)
    dataframe = _assign_asset_ids(dataframe)
    dataframe = generate_anchors(dataframe, cfg, rng)
    dataframe = generate_geometry(dataframe, cfg, rng)
    dataframe = generate_wall_insulation(dataframe, cfg, rng)
    dataframe = generate_dates(dataframe, cfg, rng)
    dataframe = generate_operating(dataframe, cfg, rng)

    corrected, _triplet_fixes = _enforce_temperature_triplet(dataframe)
    corrected, _clamp_fixes = _clamp_and_round_numerics(corrected, cfg)

    assert (corrected["min_operating_temperature"] <= corrected["operating_temperature"]).all()
    assert (corrected["operating_temperature"] <= corrected["max_operating_temperature"]).all()
    op_lo, op_hi = cfg.schema["variables"]["operating_temperature"]["range"]
    for column in (
        "operating_temperature",
        "min_operating_temperature",
        "max_operating_temperature",
    ):
        series = pd.to_numeric(corrected[column], errors="coerce")
        assert series.between(float(op_lo), float(op_hi)).all(), column
    frac_decimals = int(cfg.schema["variables"]["operation_vs_shutdown_fraction"]["decimals"])
    frac_series = pd.to_numeric(corrected["operation_vs_shutdown_fraction"], errors="coerce")
    assert frac_series.eq(frac_series.round(frac_decimals)).all()


def test_wall_thickness_ordering(df):
    """last_inspection_thickness <= furnished_thickness for every row."""
    if df is None:
        pytest.skip("No dataset provided")
    assert (df["last_inspection_thickness"] <= df["furnished_thickness"]).all()


def test_last_inspection_thickness_minimum(df):
    """last_inspection_thickness >= 1.0 for every row."""
    if df is None:
        pytest.skip("No dataset provided")
    assert (df["last_inspection_thickness"] >= 1.0).all()


def test_chloride_auto_flag(df, gen_config):
    """R-CHLORIDE-01: MARINE + CALCIUM_SILICATE + insulation_age > 5y ⇒ flag true."""
    if df is None:
        pytest.skip("No dataset provided")
    ref = _reference_ts(gen_config)
    ins_ages = df["insulation_install_date"].map(
        lambda s: years_between_timestamps(pd.Timestamp(str(s)).normalize(), ref)
    )
    mask = (
        (df["exposure_zone"] == "MARINE")
        & (df["insulation_material"] == "CALCIUM_SILICATE")
        & (ins_ages > 5.0)
    )
    if mask.any():
        flagged = df.loc[mask, "insulation_chloride_flag"]
        assert flagged.astype(bool).all(), "Tier-1 chloride auto-flag not satisfied"


def test_coating_system_allowed_values(df, schema):
    """coating_system uses only data-dictionary allowed values (no EPOXY_AGED)."""
    if df is None:
        pytest.skip("No dataset provided")
    allowed = set(schema["variables"]["coating_system"]["allowed_values"])
    assert set(df["coating_system"].unique()).issubset(allowed)


def test_geometry_class_per_asset_class(df, asset_config):
    """most_prevalent_geometry_class is within the allowed subset for each asset_class."""
    if df is None:
        pytest.skip("No dataset provided")
    for _, row in df.iterrows():
        ac = str(row["asset_class"])
        allowed = set(asset_config[ac]["geometry_class_allowed"])
        assert row["most_prevalent_geometry_class"] in allowed, (
            ac,
            row["most_prevalent_geometry_class"],
        )


def test_component_diameter_per_asset_class(df, asset_config):
    """component_diameter is within asset_class-specific [min, max]."""
    if df is None:
        pytest.skip("No dataset provided")
    for _, row in df.iterrows():
        ac = str(row["asset_class"])
        bounds = asset_config[ac]["component_diameter"]
        diameter = float(row["component_diameter"])
        assert float(bounds["min"]) <= diameter <= float(bounds["max"])


def test_inspection_ever_done_when_inspection_date_present(df):
    """Synthetic rows with latest_inspection_date always have inspection_ever_done true."""
    if df is None:
        pytest.skip("No dataset provided")
    assert df["inspection_ever_done"].astype(bool).all()
