"""
Shared helpers for synthetic row generation: schema lookups, YAML conditional
weights, and weighted sampling. Used by ``layer_generators`` (and later
``constraints``) so generation logic stays readable and testable in isolation.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, MutableMapping
from typing import Any

import numpy as np
import pandas as pd

from schema_loader import GeneratorConfig


def conditional_weights_block(
    config: GeneratorConfig,
    field_name: str,
) -> dict[str, Any] | None:
    """Return the ``conditional_weights.<field_name>`` block from rules YAML, if any."""
    weights_root = config.conditional_rules.get("conditional_weights")
    if not isinstance(weights_root, dict):
        return None
    block = weights_root.get(field_name)
    return block if isinstance(block, dict) else None


def schema_variable(schema: dict[str, Any], variable_name: str) -> dict[str, Any]:
    """Return the schema entry for one variable (must exist)."""
    variables = schema.get("variables")
    if not isinstance(variables, dict):
        raise TypeError("schema must contain a 'variables' mapping")
    if variable_name not in variables:
        raise KeyError(f"schema.variables has no entry {variable_name!r}")
    entry = variables[variable_name]
    if not isinstance(entry, dict):
        raise TypeError(f"schema.variables.{variable_name} must be a mapping")
    return entry


def schema_categorical_choices(schema: dict[str, Any], variable_name: str) -> list[str]:
    """Allowed string values for a categorical schema variable."""
    entry = schema_variable(schema, variable_name)
    allowed = entry.get("allowed_values")
    if not isinstance(allowed, list) or not allowed:
        raise ValueError(f"schema.variables.{variable_name} needs non-empty allowed_values")
    return [str(value) for value in allowed]


def schema_integer_range_bounds(schema: dict[str, Any], variable_name: str) -> tuple[int, int]:
    """Inclusive [low, high] integer bounds from schema ``range``."""
    entry = schema_variable(schema, variable_name)
    bounds = entry.get("range")
    if not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
        raise ValueError(f"schema.variables.{variable_name} needs range [low, high]")
    return int(bounds[0]), int(bounds[1])


def schema_float_range_bounds(schema: dict[str, Any], variable_name: str) -> tuple[float, float]:
    """Inclusive [low, high] float bounds from schema ``range``."""
    entry = schema_variable(schema, variable_name)
    bounds = entry.get("range")
    if not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
        raise ValueError(f"schema.variables.{variable_name} needs range [low, high]")
    return float(bounds[0]), float(bounds[1])


def _weight_table_labels_and_probs(
    category_weights: Mapping[Any, Any],
) -> tuple[list[str], np.ndarray]:
    """Normalise YAML weight keys (``true``/``false`` may load as bool) for sampling."""
    labels: list[str] = []
    probs: list[float] = []
    for key, weight in category_weights.items():
        if isinstance(key, bool):
            labels.append("true" if key else "false")
        else:
            labels.append(str(key))
        probs.append(float(weight))
    return labels, np.array(probs, dtype=float)


def sample_weighted_category(
    rng: np.random.Generator,
    category_weights: Mapping[str, Any],
) -> str:
    """Draw a single categorical outcome from a positive weight table (normalized)."""
    labels, probabilities = _weight_table_labels_and_probs(category_weights)
    total = float(probabilities.sum())
    if total <= 0 or not math.isfinite(total):
        raise ValueError(
            "category weights must sum to a positive finite value, "
            f"got {category_weights!r}"
        )
    probabilities /= total
    return str(rng.choice(labels, p=probabilities))


def sample_weighted_category_column(
    rng: np.random.Generator,
    category_weights: Mapping[str, Any],
    row_count: int,
) -> pd.Series:
    """Vectorized ``sample_weighted_category`` for one column (IID rows)."""
    labels, probabilities = _weight_table_labels_and_probs(category_weights)
    total = float(probabilities.sum())
    if total <= 0 or not math.isfinite(total):
        raise ValueError(
            "category weights must sum to a positive finite value, "
            f"got {category_weights!r}"
        )
    probabilities /= total
    draws = rng.choice(labels, size=row_count, p=probabilities)
    return pd.Series(draws, index=range(row_count))


def sample_geometry_class_for_asset_class(
    asset_class_entry: MutableMapping[str, Any],
    rng: np.random.Generator,
) -> str:
    """
    Draw ``geometry_class`` restricted to ``geometry_class_allowed`` and the
    corresponding subset of ``geometry_class_weights``.
    """
    allowed = asset_class_entry.get("geometry_class_allowed")
    weights = asset_class_entry.get("geometry_class_weights")
    if not isinstance(allowed, list) or not allowed:
        raise ValueError("asset_class entry missing geometry_class_allowed")
    if not isinstance(weights, dict) or not weights:
        raise ValueError("asset_class entry missing geometry_class_weights")

    restricted_weights: dict[str, float] = {}
    for geometry_label in allowed:
        key = str(geometry_label)
        if key in weights:
            restricted_weights[key] = float(weights[key])
    if not restricted_weights:
        raise ValueError(
            "geometry_class_weights keys must overlap geometry_class_allowed for this asset class"
        )
    return sample_weighted_category(rng, restricted_weights)


def sample_first_matching_weighted_rule(
    rules: list[Any],
    row_context: Mapping[str, Any],
    rng: np.random.Generator,
) -> str:
    """
    Walk ordered YAML ``rules``; return a weighted draw from the first rule whose
    ``condition`` matches ``row_context``. Rules are first-match wins (same as YAML).
    """
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        condition = rule.get("condition")
        if not rule_condition_matches(condition, row_context):
            continue
        weights = rule.get("weights")
        if not isinstance(weights, dict):
            raise ValueError(f"conditional rule has no weights dict: {rule!r}")
        return sample_weighted_category(rng, weights)
    raise ValueError(f"No conditional rule matched row_context keys={set(row_context)!r}")


def rule_condition_matches(
    condition: Any,
    row_context: Mapping[str, Any],
) -> bool:
    """
    Evaluate a YAML ``condition`` mapping against already-generated row fields.

    Unknown condition keys return ``False`` (fail closed) until explicitly supported.
    """
    if condition is None:
        return True
    if isinstance(condition, dict) and not condition:
        return True
    if not isinstance(condition, dict):
        return False

    for predicate_key, predicate_value in condition.items():
        if not _evaluate_predicate(predicate_key, predicate_value, row_context):
            return False
    return True


def _evaluate_predicate(
    predicate_key: str,
    predicate_value: Any,
    row_context: Mapping[str, Any],
) -> bool:
    if predicate_key == "exposure_zone":
        return row_context.get("exposure_zone") == predicate_value

    if predicate_key == "insulation_material":
        return row_context.get("insulation_material") == predicate_value

    if predicate_key == "asset_age_lte":
        if "asset_age" not in row_context:
            return False
        return int(row_context["asset_age"]) <= int(predicate_value)

    if predicate_key == "asset_age_gt":
        if "asset_age" not in row_context:
            return False
        return int(row_context["asset_age"]) > int(predicate_value)

    if predicate_key == "operating_temperature_lt":
        if "operating_temperature" not in row_context:
            return False
        return float(row_context["operating_temperature"]) < float(predicate_value)

    if predicate_key == "operating_temperature_gte":
        if "operating_temperature" not in row_context:
            return False
        return float(row_context["operating_temperature"]) >= float(predicate_value)

    if predicate_key == "insulation_age_years_gt":
        if "insulation_age_years" not in row_context:
            return False
        return float(row_context["insulation_age_years"]) > float(predicate_value)

    if predicate_key == "insulation_age_years_lte":
        if "insulation_age_years" not in row_context:
            return False
        return float(row_context["insulation_age_years"]) <= float(predicate_value)

    if predicate_key == "coating_age_years_gt":
        if "coating_age_years" not in row_context:
            return False
        return float(row_context["coating_age_years"]) > float(predicate_value)

    if predicate_key == "coating_system_in":
        if "coating_system" not in row_context:
            return False
        if isinstance(predicate_value, (list, tuple)):
            allowed = list(predicate_value)
        else:
            allowed = [predicate_value]
        return row_context.get("coating_system") in allowed

    return False


# --- calendar / reference timeline -------------------------------------------


def reference_timestamp(generation_yaml: dict[str, Any]) -> pd.Timestamp:
    """Anchor ``reference_date`` from ``generation_config`` ``run`` block."""
    run = generation_yaml.get("run")
    if not isinstance(run, dict) or "reference_date" not in run:
        raise ValueError("generation config must contain run.reference_date")
    return pd.Timestamp(str(run["reference_date"])).normalize()


def commissioning_timestamp(
    reference: pd.Timestamp,
    asset_age_years: int,
) -> pd.Timestamp:
    """Nominal commissioning date: ``reference_date`` minus ``asset_age`` whole years."""
    return (reference - pd.DateOffset(years=int(asset_age_years))).normalize()


def years_between_timestamps(
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> float:
    """Approximate years from ``start`` to ``end`` (non-negative)."""
    left, right = (start.normalize(), end.normalize())
    if right < left:
        left, right = right, left
    return max(0.0, (right - left).days / 365.25)


def random_timestamp_uniform_between(
    rng: np.random.Generator,
    earliest: pd.Timestamp,
    latest: pd.Timestamp,
) -> pd.Timestamp:
    """Uniform draw on whole calendar days, inclusive of both endpoints."""
    left = min(earliest.normalize(), latest.normalize())
    right = max(earliest.normalize(), latest.normalize())
    span_days = int((right - left).days)
    offset_days = int(rng.integers(0, span_days + 1))
    return (left + pd.Timedelta(days=offset_days)).normalize()


def random_lookback_timestamp(
    rng: np.random.Generator,
    reference: pd.Timestamp,
    years_min: float,
    years_max: float,
    earliest_allowed: pd.Timestamp,
) -> pd.Timestamp:
    """
    Subtract a random span of years from ``reference``, then clamp to
    ``[earliest_allowed, reference]`` (for inspection lookback).
    """
    span_years = float(rng.uniform(years_min, years_max))
    candidate = reference - pd.Timedelta(days=int(span_years * 365.25))
    earliest_n = earliest_allowed.normalize()
    ref_n = reference.normalize()
    window_low, window_high = (earliest_n, ref_n) if earliest_n <= ref_n else (ref_n, earliest_n)
    candidate = candidate.normalize()
    if candidate < window_low:
        candidate = window_low
    if candidate > window_high:
        candidate = window_high
    return candidate
