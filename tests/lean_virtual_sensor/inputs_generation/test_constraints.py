"""
test_constraints.py
===================
Inter-variable constraints from schema.yaml and methodology §4.
"""

from __future__ import annotations

import pandas as pd
import pytest

from generation_helpers import years_between_timestamps


def _reference_ts(gen_config: dict) -> pd.Timestamp:
    return pd.Timestamp(str(gen_config["run"]["reference_date"])).normalize()


def test_temperature_triplet_ordering(df):
    """min_op_temp <= op_temp <= max_op_temp for every row."""
    if df is None:
        pytest.skip("No dataset provided")
    assert (df["min_operating_temperature"] <= df["operating_temperature"]).all()
    assert (df["operating_temperature"] <= df["max_operating_temperature"]).all()


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


def test_coating_auto_downgrade(df, gen_config):
    """R-COAT-DEFER-01: no row has coating_age > 10y and undegraded organic epoxy (layer 4)."""
    if df is None:
        pytest.skip("No dataset provided")
    ref = _reference_ts(gen_config)
    coat_ages = df["coating_application_date"].map(
        lambda s: years_between_timestamps(pd.Timestamp(str(s)).normalize(), ref)
    )
    violates = (coat_ages > 10.0) & df["coating_system"].isin(["EPOXY_HT_MULTI", "EPOXY_HT_SINGLE"])
    assert not violates.any(), "Tier-1 coating downgrade not applied"


def test_geometry_class_per_asset_class(df, asset_config):
    """geometry_class is within the allowed subset for each asset_class."""
    if df is None:
        pytest.skip("No dataset provided")
    for _, row in df.iterrows():
        ac = str(row["asset_class"])
        allowed = set(asset_config[ac]["geometry_class_allowed"])
        assert row["geometry_class"] in allowed, (ac, row["geometry_class"])


def test_component_diameter_per_asset_class(df, asset_config):
    """component_diameter is within asset_class-specific [min, max]."""
    if df is None:
        pytest.skip("No dataset provided")
    for _, row in df.iterrows():
        ac = str(row["asset_class"])
        bounds = asset_config[ac]["component_diameter"]
        diameter = float(row["component_diameter"])
        assert float(bounds["min"]) <= diameter <= float(bounds["max"])
