"""
Post-generation structural constraint enforcement.

See module docstring in constraints.py for enforced rules.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
from generation_helpers import (
    parse_commissioning_timestamp,
    reference_timestamp,
)
from schema_loader import GeneratorConfig

logger = logging.getLogger(__name__)

MAX_FLAGGED_ROWS = 0


def enforce_all_constraints(
    df: pd.DataFrame,
    config: GeneratorConfig,
) -> tuple[pd.DataFrame, list[dict]]:
    """Run all constraint checks and corrections on the full DataFrame."""
    corrections: list[dict] = []
    out = df.copy()
    reference_ts = reference_timestamp(config.generation)

    out, n = _enforce_temperature_triplet(out)
    if n:
        corrections.append({"step": "temperature_triplet", "n_corrections": n})

    out, n = _enforce_wall_thickness(out)
    if n:
        corrections.append({"step": "wall_thickness", "n_corrections": n})

    out, n = _enforce_date_chain(out, reference_ts)
    if n:
        corrections.append({"step": "date_chain", "n_corrections": n})

    out, n = _clamp_and_round_numerics(out, config)
    if n:
        corrections.append({"step": "clamp_round_numerics", "n_corrections": n})

    flagged = _collect_unrecoverable_rows(out, config, reference_ts)
    if len(flagged) > MAX_FLAGGED_ROWS:
        raise ValueError(f"Constraint pass could not fix {len(flagged)} row(s): {flagged[:10]!r}")

    return out, corrections


def _enforce_temperature_triplet(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    n = 0
    result = df.copy()
    for i in result.index:
        op = float(result.at[i, "operating_temperature"])
        min_v = float(result.at[i, "min_operating_temperature"])
        max_v = float(result.at[i, "max_operating_temperature"])
        new_min = min(min_v, op)
        new_max = max(max_v, op)
        if new_min > op:
            new_min = op
        if new_max < op:
            new_max = op
        if new_min != min_v or new_max != max_v:
            n += 1
        result.at[i, "min_operating_temperature"] = round(new_min, 1)
        result.at[i, "max_operating_temperature"] = round(new_max, 1)
    return result, n


def _enforce_wall_thickness(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    n = 0
    result = df.copy()
    for i in result.index:
        furnished = float(result.at[i, "furnished_thickness"])
        last = float(result.at[i, "last_inspection_thickness"])
        new_last = min(max(1.0, last), furnished)
        if new_last != last:
            n += 1
        result.at[i, "last_inspection_thickness"] = round(new_last, 2)
    return result, n


def _enforce_date_chain(df: pd.DataFrame, reference_date: pd.Timestamp) -> tuple[pd.DataFrame, int]:
    n = 0
    result = df.copy()
    ref_n = reference_date.normalize()

    for i in result.index:
        commissioning = parse_commissioning_timestamp(result.at[i, "asset_commissioning_date"])

        for col in (
            "insulation_install_date",
            "coating_application_date",
            "latest_inspection_date",
        ):
            ts = pd.Timestamp(str(result.at[i, col])).normalize()
            if ts > ref_n:
                n += 1
                result.at[i, col] = ref_n.date().isoformat()
                ts = ref_n
            if ts < commissioning.normalize():
                n += 1
                result.at[i, col] = commissioning.date().isoformat()

        if commissioning > ref_n:
            n += 1
            result.at[i, "asset_commissioning_date"] = ref_n.date().isoformat()

    return result, n


def _clamp_and_round_numerics(
    df: pd.DataFrame, config: GeneratorConfig
) -> tuple[pd.DataFrame, int]:
    n = 0
    result = df.copy()
    variables = config.schema.get("variables")
    if not isinstance(variables, dict):
        return result, 0

    for name, spec in variables.items():
        if name not in result.columns:
            continue
        if not isinstance(spec, dict):
            continue
        vtype = spec.get("type")
        decimals = int(spec.get("decimals", 0))

        if vtype == "int" and "range" in spec:
            lo, hi = int(spec["range"][0]), int(spec["range"][1])
            series = pd.to_numeric(result[name], errors="coerce").fillna(lo).astype(int)
            clipped = series.clip(lo, hi)
            if not clipped.equals(series):
                n += int((clipped != series).sum())
            result[name] = clipped

        elif vtype == "float" and "range" in spec:
            lo, hi = float(spec["range"][0]), float(spec["range"][1])
            series = pd.to_numeric(result[name], errors="coerce").astype(float)
            clipped = series.clip(lo, hi)
            if not np.allclose(clipped, series, equal_nan=True):
                n += int((~np.isclose(clipped, series, equal_nan=True)).sum())
            rounded = clipped.round(decimals)
            if not np.allclose(rounded, clipped, equal_nan=True):
                n += int((~np.isclose(rounded, clipped, equal_nan=True)).sum())
            result[name] = rounded

        elif vtype == "float" and "range" not in spec:
            series = pd.to_numeric(result[name], errors="coerce").astype(float)
            rounded = series.round(decimals)
            if not np.allclose(rounded, series, equal_nan=True):
                n += int((~np.isclose(rounded, series, equal_nan=True)).sum())
            result[name] = rounded

    return result, n


def _collect_unrecoverable_rows(
    df: pd.DataFrame,
    config: GeneratorConfig,
    reference_date: pd.Timestamp,
) -> list[dict[str, Any]]:
    flagged: list[dict[str, Any]] = []
    ref_n = reference_date.normalize()
    variables = config.schema.get("variables", {})

    for i in df.index:
        reasons: list[str] = []

        op = float(df.at[i, "operating_temperature"])
        if float(df.at[i, "min_operating_temperature"]) > op:
            reasons.append("min_op>op")
        if float(df.at[i, "max_operating_temperature"]) < op:
            reasons.append("max_op<op")

        furnished = float(df.at[i, "furnished_thickness"])
        last = float(df.at[i, "last_inspection_thickness"])
        if last > furnished or last < 1.0:
            reasons.append("last_thickness_bounds")

        commissioning = parse_commissioning_timestamp(df.at[i, "asset_commissioning_date"])
        ins_ts = pd.Timestamp(str(df.at[i, "insulation_install_date"]))
        coat_ts = pd.Timestamp(str(df.at[i, "coating_application_date"]))
        if ins_ts < commissioning or ins_ts > ref_n:
            reasons.append("insulation_date_window")
        if coat_ts < commissioning or coat_ts > ref_n:
            reasons.append("coating_date_window")
        if commissioning > ref_n:
            reasons.append("commissioning_after_reference")

        insp_ts = pd.Timestamp(str(df.at[i, "latest_inspection_date"]))
        if insp_ts.normalize() > ref_n or insp_ts.normalize() < commissioning.normalize():
            reasons.append("inspection_date_window")

        for var_name, spec in variables.items():
            if var_name not in df.columns or not isinstance(spec, dict):
                continue
            vtype = spec.get("type")
            if vtype == "categorical" and "allowed_values" in spec:
                allowed = set(spec["allowed_values"])
                if str(df.at[i, var_name]) not in allowed:
                    reasons.append(f"categorical:{var_name}")

        if reasons:
            flagged.append({"row_index": int(i), "reasons": reasons})

    return flagged
