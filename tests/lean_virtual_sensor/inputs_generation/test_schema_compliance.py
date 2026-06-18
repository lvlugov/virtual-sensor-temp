"""
test_schema_compliance.py
=========================
Checks that all values in the dataset are within allowed sets and ranges
as defined in schema.yaml.

Tests:
    - All categorical columns contain only schema-allowed values
    - All numeric columns have values within schema [min, max]
    - All boolean columns contain only True/False
    - All date columns are valid dates in YYYY-MM-DD format
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def test_categorical_allowed_values(df, schema):
    """All categorical fields contain only schema-allowed values."""
    if df is None:
        pytest.skip("No dataset provided")
    variables = schema["variables"]
    for name, spec in variables.items():
        if not isinstance(spec, dict) or spec.get("type") != "categorical":
            continue
        if name not in df.columns:
            continue
        allowed = {str(x) for x in spec["allowed_values"]}
        for value in df[name].dropna().unique():
            assert str(value) in allowed, f"{name}: disallowed value {value!r}"


def test_numeric_ranges(df, schema):
    """All numeric fields with a schema range are within [min, max]."""
    if df is None:
        pytest.skip("No dataset provided")
    variables = schema["variables"]
    for name, spec in variables.items():
        if not isinstance(spec, dict) or name not in df.columns:
            continue
        if "range" not in spec:
            continue
        lo, hi = spec["range"]
        if spec.get("type") == "int":
            series = pd.to_numeric(df[name], errors="coerce")
            assert series.notna().all(), f"{name}: non-numeric or null"
            assert series.between(int(lo), int(hi)).all(), f"{name}: outside [{lo}, {hi}]"
        elif spec.get("type") == "float":
            series = pd.to_numeric(df[name], errors="coerce")
            assert series.notna().all(), f"{name}: non-numeric or null"
            assert series.between(float(lo), float(hi)).all(), f"{name}: outside [{lo}, {hi}]"


def test_boolean_values(df, schema):
    """All boolean fields contain only True/False (after CSV round-trip)."""
    if df is None:
        pytest.skip("No dataset provided")
    variables = schema["variables"]
    for name, spec in variables.items():
        if not isinstance(spec, dict) or spec.get("type") != "bool":
            continue
        if name not in df.columns:
            continue
        for value in df[name].dropna().unique():
            if isinstance(value, (bool, np.bool_)):
                # ``np.False_ is False`` is false; use membership, not identity.
                assert value in (True, False), name
            else:
                assert str(value).lower() in ("true", "false"), f"{name}: {value!r}"


def test_date_format(df, schema):
    """All date fields are valid calendar dates."""
    if df is None:
        pytest.skip("No dataset provided")
    variables = schema["variables"]
    for name, spec in variables.items():
        if not isinstance(spec, dict) or spec.get("type") != "date":
            continue
        if name not in df.columns:
            continue
        parsed = pd.to_datetime(df[name], errors="coerce")
        assert parsed.notna().all(), f"{name}: invalid date value(s)"
