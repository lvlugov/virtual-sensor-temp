"""
test_completeness.py
====================
No nulls in fields marked nullable=false in schema.yaml (synthetic dataset).
"""

from __future__ import annotations

import pytest


def test_no_nulls_in_non_nullable_fields(df, schema):
    """No null values in any field marked nullable=false in schema.yaml."""
    if df is None:
        pytest.skip("No dataset provided")
    variables = schema["variables"]
    for name, spec in variables.items():
        if not isinstance(spec, dict):
            continue
        if spec.get("nullable", True):
            continue
        if name not in df.columns:
            continue
        nulls = df[name].isna().sum()
        assert int(nulls) == 0, f"{name}: expected no nulls, found {int(nulls)}"
