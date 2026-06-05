"""
constraints.py
==============
Post-generation **structural** constraint enforcement.

After all seven layers have run, this module performs a final pass over the
DataFrame to catch and correct structural violations that slipped through
the layer generators (e.g. floating-point rounding, edge cases in date maths).

Business rules (Tier 1 deterministic derivations such as R-CHLORIDE-01 and
R-COAT-DEFER-01) are applied in ``layer_generators`` / YAML — not here.
Contract tests (``test_constraints.py``) assert those rules on the CSV.

This is a DEFENSIVE pass — the layer generators are expected to produce
compliant data. If this module has to make many corrections, that indicates
a bug in a layer generator, not normal operation.

All corrections are logged. If a correction cannot be made (e.g. a logical
contradiction), the row is flagged and reported. Generation halts if flagged
rows exceed MAX_FLAGGED_ROWS.

Structural constraints enforced (mirrors test_constraints.py / test_date_chain):

    NUMERIC ORDERING
    ----------------
    min_operating_temperature  <= operating_temperature
    operating_temperature      <= max_operating_temperature
    last_inspection_thickness  <= furnished_thickness
    last_inspection_thickness  >= 1.0

    DATE ORDERING
    -------------
    insulation_install_date    <= reference_date
    insulation_install_date    >= commissioning_date  (reference_date - asset_age)
    coating_application_date   <= reference_date
    coating_application_date   >= commissioning_date
    inspection_record_dates    <= reference_date
    insulation_install_date    <= inspection_record_dates

    ASSET AGE
    ---------
    asset_age >= insulation_age_years  (derived from insulation_install_date)
    asset_age >= coating_age_years     (derived from coating_application_date)

    RANGE CLAMPS (last resort — log if triggered)
    -----------------------------------------------
    All numeric fields clamped to [min, max] from schema.yaml
    All float fields rounded to schema-specified decimal places
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from generation_helpers import (
    commissioning_timestamp,
    reference_timestamp,
    years_between_timestamps,
)
from schema_loader import GeneratorConfig

logger = logging.getLogger(__name__)

MAX_FLAGGED_ROWS = 0  # Halt if any row cannot be corrected


def enforce_all_constraints(
    df: pd.DataFrame,
    config: GeneratorConfig,
) -> tuple[pd.DataFrame, list[dict]]:
    """Run all constraint checks and corrections on the full DataFrame.

    Args:
        df: Generated DataFrame (all layers complete).
        config: Loaded generator config.

    Returns:
        Tuple of (corrected DataFrame, list of correction log entries).

    Raises:
        ValueError: If any row cannot be corrected (logical contradiction).
    """
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
    """Ensure min <= op_temp <= max. Returns (df, n_corrections)."""
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
    """Ensure last_inspection_thickness <= furnished_thickness >= 1.0."""
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


def _enforce_date_chain(
    df: pd.DataFrame, reference_date: pd.Timestamp
) -> tuple[pd.DataFrame, int]:
    """Ensure all dates within valid range relative to asset_age."""
    n = 0
    result = df.copy()
    ref_n = reference_date.normalize()

    for i in result.index:
        asset_age = int(result.at[i, "asset_age"])
        commissioning = commissioning_timestamp(ref_n, asset_age)

        for col in ("insulation_install_date", "coating_application_date", "inspection_record_dates"):
            ts = pd.Timestamp(str(result.at[i, col])).normalize()
            if ts > ref_n:
                n += 1
                result.at[i, col] = ref_n.date().isoformat()
                ts = ref_n
            if ts < commissioning.normalize():
                n += 1
                result.at[i, col] = commissioning.date().isoformat()

        ins_ts = pd.Timestamp(str(result.at[i, "insulation_install_date"])).normalize()
        insp_ts = pd.Timestamp(str(result.at[i, "inspection_record_dates"])).normalize()
        if insp_ts < ins_ts:
            n += 1
            result.at[i, "inspection_record_dates"] = ins_ts.date().isoformat()

    return result, n


def _clamp_and_round_numerics(
    df: pd.DataFrame, config: GeneratorConfig
) -> tuple[pd.DataFrame, int]:
    """Clamp all numeric fields to schema range and round to schema decimals."""
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
    """Rows that still violate hard constraints after correction attempts."""
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

        asset_age = int(df.at[i, "asset_age"])
        commissioning = commissioning_timestamp(ref_n, asset_age)
        ins_ts = pd.Timestamp(str(df.at[i, "insulation_install_date"]))
        coat_ts = pd.Timestamp(str(df.at[i, "coating_application_date"]))
        if ins_ts < commissioning or ins_ts > ref_n:
            reasons.append("insulation_date_window")
        if coat_ts < commissioning or coat_ts > ref_n:
            reasons.append("coating_date_window")

        insp_ts = pd.Timestamp(str(df.at[i, "inspection_record_dates"]))
        if insp_ts.normalize() < ins_ts.normalize():
            reasons.append("inspection_before_insulation")

        ins_age = years_between_timestamps(ins_ts, ref_n)
        coat_age = years_between_timestamps(coat_ts, ref_n)
        if ins_age > float(asset_age) + 1.0:
            reasons.append("insulation_age_vs_asset_age")
        if coat_age > float(asset_age) + 1.0:
            reasons.append("coating_age_vs_asset_age")

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
