"""
test_distributions.py
=====================
Aggregate sanity checks on the synthetic dataset (methodology / Part 2).
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from schema_loader import load_all_configs
from temperature_population_checks import assert_temperature_population_acceptance


ASSET_CLASS_TOLERANCE = 0.05


def _config_dir() -> Path:
    return (
        Path(__file__).resolve().parents[3]
        / "lean_virtual_sensor"
        / "inputs_generation"
        / "config"
    )


def test_asset_class_counts_within_tolerance(df, gen_config):
    """Asset class counts within ±5% of targets in generation_config."""
    if df is None or gen_config is None:
        pytest.skip("Requires synthetic dataset with generation_config")
    proportions = gen_config["asset_class_proportions"]
    n_rows = len(df)
    for asset_class_key, target in proportions.items():
        target_n = int(target)
        actual = int((df["asset_class"] == asset_class_key).sum())
        slack = max(1, math.ceil(ASSET_CLASS_TOLERANCE * target_n))
        assert abs(actual - target_n) <= slack, (
            f"{asset_class_key}: target {target_n}, actual {actual}, slack {slack}"
        )
    assert n_rows == int(gen_config["run"]["n_rows"])


def test_no_empty_asset_class(df, gen_config):
    """Every asset class with a configured positive count has at least one row."""
    if df is None or gen_config is None:
        pytest.skip("Requires synthetic dataset with generation_config")
    proportions = gen_config["asset_class_proportions"]
    for asset_class_key, target in proportions.items():
        if int(target) <= 0:
            continue
        actual = int((df["asset_class"] == asset_class_key).sum())
        assert actual >= 1, f"{asset_class_key}: expected ≥1 row, got {actual}"


def test_no_degenerate_categorical_distributions(df, schema):
    """No categorical (≥3 levels) has a single value on >99% of rows."""
    if df is None:
        pytest.skip("No dataset provided")
    n = len(df)
    variables = schema["variables"]
    for name, spec in variables.items():
        if not isinstance(spec, dict) or spec.get("type") != "categorical":
            continue
        allowed = spec.get("allowed_values") or []
        if len(allowed) < 3 or name not in df.columns:
            continue
        counts = df[name].value_counts(normalize=False)
        if counts.empty:
            continue
        assert counts.max() <= int(0.99 * n) + 1, f"{name}: degenerate distribution (max count {counts.max()})"


def test_numeric_columns_have_variance(df, schema):
    """Numeric columns with schema range have non-zero variance."""
    if df is None:
        pytest.skip("No dataset provided")
    variables = schema["variables"]
    for name, spec in variables.items():
        if not isinstance(spec, dict) or name not in df.columns:
            continue
        if spec.get("type") not in ("int", "float") or "range" not in spec:
            continue
        series = pd.to_numeric(df[name], errors="coerce")
        assert series.std(ddof=0) > 0 or series.nunique() > 1, f"{name}: zero variance"


def test_wall_loss_distribution_is_right_skewed(df):
    """Derived wall_loss_fraction (1 − last/furnished) is right-skewed (mean > median)."""
    if df is None:
        pytest.skip("No dataset provided")
    last = pd.to_numeric(df["last_inspection_thickness"], errors="coerce")
    furnished = pd.to_numeric(df["furnished_thickness"], errors="coerce")
    frac = 1.0 - (last / furnished)
    assert frac.mean() > frac.median(), "expected right-skewed wall loss fraction"


def test_temperature_population_acceptance(df, gen_config):
    """Static temperature fields match Section 2 population targets."""
    if df is None or gen_config is None:
        pytest.skip("Requires synthetic dataset with generation_config")
    cfg = load_all_configs(_config_dir())
    assert_temperature_population_acceptance(df, cfg.operating_temperature)
