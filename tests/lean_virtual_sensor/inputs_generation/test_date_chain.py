"""
test_date_chain.py
==================
Checks that date fields obey ordering constraints (methodology §4 Layer 4).
"""

from __future__ import annotations

import pandas as pd
import pytest

from generation_helpers import commissioning_timestamp, years_between_timestamps


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
    """insulation_install_date >= commissioning_date (reference − asset_age)."""
    if df is None:
        pytest.skip("No dataset provided")
    ref = _reference_ts(gen_config)
    for _, row in df.iterrows():
        commissioning = commissioning_timestamp(ref, int(row["asset_age"]))
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
    """coating_application_date >= commissioning_date."""
    if df is None:
        pytest.skip("No dataset provided")
    ref = _reference_ts(gen_config)
    for _, row in df.iterrows():
        commissioning = commissioning_timestamp(ref, int(row["asset_age"]))
        coat = pd.Timestamp(row["coating_application_date"]).normalize()
        assert coat >= commissioning.normalize()


def test_inspection_date_not_future(df, gen_config):
    """inspection_record_dates <= reference_date for every row."""
    if df is None:
        pytest.skip("No dataset provided")
    ref = _reference_ts(gen_config)
    ins = pd.to_datetime(df["inspection_record_dates"])
    assert (ins <= ref).all()


def test_inspection_date_not_before_insulation_install(df):
    """inspection_record_dates >= insulation_install_date for every row."""
    if df is None:
        pytest.skip("No dataset provided")
    install = pd.to_datetime(df["insulation_install_date"])
    inspection = pd.to_datetime(df["inspection_record_dates"])
    assert (inspection >= install).all()


def test_asset_age_covers_insulation_and_coating_ages(df, gen_config):
    """asset_age (years) is not less than derived insulation / coating ages."""
    if df is None:
        pytest.skip("No dataset provided")
    ref = _reference_ts(gen_config)
    for _, row in df.iterrows():
        asset_age = int(row["asset_age"])
        ins_age = years_between_timestamps(
            pd.Timestamp(row["insulation_install_date"]).normalize(), ref
        )
        coat_age = years_between_timestamps(
            pd.Timestamp(row["coating_application_date"]).normalize(), ref
        )
        assert ins_age <= float(asset_age) + 1.0, (row.get("Asset"), ins_age, asset_age)
        assert coat_age <= float(asset_age) + 1.0, (row.get("Asset"), coat_age, asset_age)
