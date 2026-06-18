"""
test_date_chain.py
==================
Checks that date fields obey ordering constraints (methodology §4 Layer 4).
"""

from __future__ import annotations

import pandas as pd
import pytest
from generation_helpers import parse_commissioning_timestamp


def _reference_ts(gen_config: dict) -> pd.Timestamp:
    run = gen_config["run"]
    return pd.Timestamp(str(run["reference_date"])).normalize()


def test_insulation_install_date_not_future(df, gen_config):
    """insulation_install_date <= reference_date for every row."""
    if df is None:
        pytest.skip("No dataset provided")
    ref = _reference_ts(gen_config)
    ins = pd.to_datetime(df["insulation_install_date"])
    assert (ins <= ref).all()


def test_insulation_install_date_within_asset_lifetime(df, gen_config):
    """insulation_install_date >= asset_commissioning_date."""
    if df is None:
        pytest.skip("No dataset provided")
    for _, row in df.iterrows():
        commissioning = parse_commissioning_timestamp(row["asset_commissioning_date"])
        ins = pd.Timestamp(row["insulation_install_date"]).normalize()
        assert ins >= commissioning.normalize(), (row.get("Asset"), ins, commissioning)


def test_coating_application_date_not_future(df, gen_config):
    """coating_application_date <= reference_date for every row."""
    if df is None:
        pytest.skip("No dataset provided")
    ref = _reference_ts(gen_config)
    coat = pd.to_datetime(df["coating_application_date"])
    assert (coat <= ref).all()


def test_coating_application_date_within_asset_lifetime(df, gen_config):
    """coating_application_date >= asset_commissioning_date."""
    if df is None:
        pytest.skip("No dataset provided")
    for _, row in df.iterrows():
        commissioning = parse_commissioning_timestamp(row["asset_commissioning_date"])
        coat = pd.Timestamp(row["coating_application_date"]).normalize()
        assert coat >= commissioning.normalize()


def test_inspection_date_not_future(df, gen_config):
    """latest_inspection_date <= reference_date for every row."""
    if df is None:
        pytest.skip("No dataset provided")
    ref = _reference_ts(gen_config)
    ins = pd.to_datetime(df["latest_inspection_date"])
    assert (ins <= ref).all()


def test_inspection_date_within_asset_lifetime(df, gen_config):
    """latest_inspection_date >= asset_commissioning_date."""
    if df is None:
        pytest.skip("No dataset provided")
    for _, row in df.iterrows():
        commissioning = parse_commissioning_timestamp(row["asset_commissioning_date"])
        inspection = pd.Timestamp(row["latest_inspection_date"]).normalize()
        assert inspection >= commissioning.normalize()
