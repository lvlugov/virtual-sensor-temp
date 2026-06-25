"""
Shared helpers for synthetic row generation: schema lookups, YAML conditional
weights, Tier 1 ``set_value`` rules, and weighted sampling. Used by
``layer_generators`` so generation logic stays readable and testable in isolation.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, MutableMapping
from typing import Any

import numpy as np
import pandas as pd

from lean_virtual_sensor.inputs_generation.schema_loader import GeneratorConfig


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


def deterministic_rules_block(
    config: GeneratorConfig,
    field_name: str,
) -> dict[str, Any] | None:
    """Return the ``deterministic_rules.<field_name>`` block from rules YAML, if any."""
    rules_root = config.conditional_rules.get("deterministic_rules")
    if not isinstance(rules_root, dict):
        return None
    block = rules_root.get(field_name)
    return block if isinstance(block, dict) else None


def apply_deterministic_field_value(
    config: GeneratorConfig,
    field_name: str,
    row_context: Mapping[str, Any],
    *,
    default: Any = None,
) -> Any:
    """
    Evaluate Tier 1 ``deterministic_rules`` for ``field_name``.

    Walks ordered YAML ``rules``; returns ``value`` from the first rule whose
    ``condition`` matches ``row_context`` and ``action`` is ``set_value``.
    If no rule matches, returns ``default``.
    """
    block = deterministic_rules_block(config, field_name)
    if block is None:
        return default
    rules = block.get("rules")
    if not isinstance(rules, list):
        raise ValueError(
            f"deterministic_rules.{field_name} must contain a 'rules' list, "
            f"got {type(rules).__name__}"
        )
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            continue
        action = rule.get("action")
        if action != "set_value":
            raise ValueError(
                f"deterministic_rules.{field_name}.rules[{index}] action must be "
                f"'set_value' (got {action!r})"
            )
        condition = rule.get("condition")
        if not rule_condition_matches(condition, row_context):
            continue
        if "value" not in rule:
            raise ValueError(f"deterministic_rules.{field_name}.rules[{index}] missing 'value'")
        return rule["value"]
    return default


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
            f"category weights must sum to a positive finite value, got {category_weights!r}"
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
            f"category weights must sum to a positive finite value, got {category_weights!r}"
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
        age_years = _asset_age_years_from_context(row_context)
        if age_years is None:
            return False
        return age_years <= float(predicate_value)

    if predicate_key == "asset_age_gt":
        age_years = _asset_age_years_from_context(row_context)
        if age_years is None:
            return False
        return age_years > float(predicate_value)

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


def _asset_age_years_from_context(row_context: Mapping[str, Any]) -> float | None:
    """Years from commissioning to reference, for coating/cladding rule predicates."""
    if "asset_age_years" in row_context:
        return float(row_context["asset_age_years"])
    if "asset_commissioning_date" in row_context and "reference_date" in row_context:
        commissioning = pd.Timestamp(str(row_context["asset_commissioning_date"])).normalize()
        reference = pd.Timestamp(str(row_context["reference_date"])).normalize()
        return years_between_timestamps(commissioning, reference)
    return None


# --- component geometry sampling -------------------------------------------


def geometry_standards_pipe_nps(conditional_rules: Mapping[str, Any]) -> dict[str, Any]:
    """Return ``geometry_standards.pipe_nps`` from conditional rules YAML."""
    geometry_standards = conditional_rules.get("geometry_standards")
    if not isinstance(geometry_standards, dict):
        raise ValueError("conditional_rules.geometry_standards is required")
    pipe_nps = geometry_standards.get("pipe_nps")
    if not isinstance(pipe_nps, dict):
        raise ValueError("geometry_standards.pipe_nps is required")
    return pipe_nps


def sample_nps_catalog_geometry(
    rng: np.random.Generator,
    pipe_nps_block: Mapping[str, Any],
) -> tuple[float, float]:
    """Draw a weighted ``(od_mm, wall_mm)`` pair from the PIPE NPS catalog."""
    catalog = pipe_nps_block.get("nps_catalog")
    if not isinstance(catalog, list) or not catalog:
        raise ValueError("pipe_nps.nps_catalog must be a non-empty list")
    weights = np.array([float(row["weight"]) for row in catalog], dtype=float)
    total = float(weights.sum())
    if total <= 0 or not math.isfinite(total):
        raise ValueError("pipe_nps catalog weights must sum to a positive finite value")
    probabilities = weights / total
    index = int(rng.choice(len(catalog), p=probabilities))
    row = catalog[index]
    return float(row["od_mm"]), float(row["wall_mm"])


def sample_triangular_diameter(
    rng: np.random.Generator,
    diameter_min: float,
    diameter_mode: float,
    diameter_max: float,
) -> float:
    """Draw outer diameter from a triangular distribution."""
    return float(rng.triangular(diameter_min, diameter_mode, diameter_max))


def sample_coupled_wall_thickness(
    rng: np.random.Generator,
    diameter: float,
    t_over_d_min: float,
    t_over_d_max: float,
    clamp_min: float,
    clamp_max: float,
) -> float:
    """Draw wall thickness as ``(t/D) × diameter``, clamped to ``[clamp_min, clamp_max]``."""
    t_over_d = float(rng.uniform(t_over_d_min, t_over_d_max))
    wall = t_over_d * diameter
    return float(max(clamp_min, min(clamp_max, wall)))


def sample_component_geometry(
    asset_class_key: str,
    class_config: Mapping[str, Any],
    conditional_rules: Mapping[str, Any],
    rng: np.random.Generator,
) -> tuple[float, float]:
    """
    Draw ``(component_diameter, furnished_thickness)`` for one asset class.

    PIPE uses the weighted NPS catalog; other classes use triangular diameter
    with coupled or fixed wall thickness per ``geometry_sampling`` in class config.
    """
    if asset_class_key == "PIPE":
        pipe_nps = geometry_standards_pipe_nps(conditional_rules)
        od_mm, wall_mm = sample_nps_catalog_geometry(rng, pipe_nps)
        return round(od_mm, 1), round(wall_mm, 2)

    geometry_sampling = class_config.get("geometry_sampling")
    if not isinstance(geometry_sampling, dict):
        raise ValueError(f"{asset_class_key!r}: missing geometry_sampling in asset_class_config")

    diameter_limits = class_config["component_diameter"]
    wall_limits = class_config["furnished_thickness"]
    wall_min_env = float(wall_limits["min"])
    wall_max_env = float(wall_limits["max"])
    diameter = sample_triangular_diameter(
        rng,
        float(diameter_limits["min"]),
        float(diameter_limits["mode"]),
        float(diameter_limits["max"]),
    )

    method = geometry_sampling.get("method")
    wall_cfg = geometry_sampling["wall"]
    if method == "triangular_fixed_wall":
        fixed_min = max(float(wall_cfg["min"]), wall_min_env)
        fixed_max = min(float(wall_cfg["max"]), wall_max_env)
        wall = float(rng.uniform(fixed_min, fixed_max))
    elif method == "triangular_coupled_wall":
        clamp_min = max(float(wall_cfg["clamp_min"]), wall_min_env)
        clamp_max = min(float(wall_cfg["clamp_max"]), wall_max_env)
        wall = sample_coupled_wall_thickness(
            rng,
            diameter,
            float(wall_cfg["t_over_d_min"]),
            float(wall_cfg["t_over_d_max"]),
            clamp_min,
            clamp_max,
        )
    else:
        raise ValueError(f"{asset_class_key!r}: unknown geometry_sampling.method {method!r}")

    return round(diameter, 1), round(wall, 2)


# --- operating temperature static fields (layer 5) -----------------------------

_COLD_SERVICE_PROFILE_BY_CLASS: dict[str, str] = {
    "PIPE": "PIPE_COLD_SERVICE",
    "PRESSURE_VESSEL": "PRESSURE_VESSEL_COLD_SERVICE",
    "STORAGE_TANK": "STORAGE_TANK_REFRIGERATED",
}
_COLD_SERVICE_MIN_OFFSET = (5.0, 10.0)


def _profile_is_cold_service(profile: Mapping[str, Any]) -> bool:
    """Cold-service table rows have sub-ambient operating temperature ranges."""
    op_block = profile["operating_temperature"]
    return float(op_block["max"]) < 0.0


def resolve_operating_temperature_profile(
    asset_class: str,
    operating_temperature_config: Mapping[str, Any],
    rng: np.random.Generator,
) -> str:
    """
    Choose the Section 2 table row (profile key) for one asset.

    Eligible classes may use their cold-service row; wide-swing reassignment
    is applied separately via ``apply_wide_swing_temperature_assignments``.
    """
    default_profiles = operating_temperature_config["asset_class_default_profile"]
    if asset_class not in default_profiles:
        raise KeyError(f"No asset_class_default_profile entry for asset class {asset_class!r}")

    if asset_class in _COLD_SERVICE_PROFILE_BY_CLASS:
        cold_fracs = operating_temperature_config["cold_service_fraction"]
        fraction = float(cold_fracs[asset_class])
        if rng.random() < fraction:
            return _COLD_SERVICE_PROFILE_BY_CLASS[asset_class]

    return str(default_profiles[asset_class])


def sample_operating_temperature_fields(
    profile_key: str,
    operating_temperature_config: Mapping[str, Any],
    rng: np.random.Generator,
) -> dict[str, float | int]:
    """
    Draw the five static temperature fields for one sampling profile.

    Profile selection (asset_class, cold-service, wide-swing) is handled by the
    caller; this function only samples from ``profiles[profile_key]``.
    """
    profiles = operating_temperature_config.get("profiles")
    if not isinstance(profiles, dict):
        raise ValueError("operating_temperature_config must define 'profiles'")
    profile = profiles.get(profile_key)
    if not isinstance(profile, dict):
        raise ValueError(f"Unknown operating temperature profile {profile_key!r}")

    max_excursion_fraction = float(operating_temperature_config["max_excursion_fraction"])

    op_block = profile["operating_temperature"]
    operating_temp = round(
        float(
            rng.triangular(
                float(op_block["min"]),
                float(op_block["mode"]),
                float(op_block["max"]),
            )
        ),
        1,
    )

    min_temp = _sample_min_operating_temperature(profile, operating_temp, rng)
    max_temp = _sample_max_operating_temperature(
        profile, operating_temp, max_excursion_fraction, rng
    )

    cycles_block = profile["avg_cycles_per_quarter"]
    cycles = int(rng.integers(int(cycles_block["min"]), int(cycles_block["max"]) + 1))

    fraction_block = profile["operation_vs_shutdown_fraction"]
    on_stream = round(
        float(
            rng.uniform(
                float(fraction_block["min"]),
                float(fraction_block["max"]),
            )
        ),
        3,
    )

    min_temp, max_temp = _repair_temperature_triplet(operating_temp, min_temp, max_temp)

    return {
        "operating_temperature": operating_temp,
        "min_operating_temperature": min_temp,
        "max_operating_temperature": max_temp,
        "avg_cycles_per_quarter": cycles,
        "operation_vs_shutdown_fraction": on_stream,
    }


def apply_wide_swing_temperature_assignments(
    dataframe: pd.DataFrame,
    operating_temperature_config: Mapping[str, Any],
    rng: np.random.Generator,
) -> pd.DataFrame:
    """
    Reassign a random share of rows to the wide-swing Section 2 table row.

    Spec: 5% of assets, any ``asset_class``; all five static fields overwritten.
    """
    result = dataframe.copy()
    row_count = len(result)
    if row_count == 0:
        return result

    wide_fraction = float(operating_temperature_config["wide_swing_fraction"])
    wide_count = int(round(wide_fraction * row_count))
    if wide_count <= 0:
        return result

    wide_indices = rng.choice(row_count, size=wide_count, replace=False)
    field_names = (
        "operating_temperature",
        "min_operating_temperature",
        "max_operating_temperature",
        "avg_cycles_per_quarter",
        "operation_vs_shutdown_fraction",
    )
    for row_index in wide_indices:
        fields = sample_operating_temperature_fields(
            "WIDE_SWING", operating_temperature_config, rng
        )
        for field_name in field_names:
            result.at[row_index, field_name] = fields[field_name]

    return result


def _sample_min_operating_temperature(
    profile: Mapping[str, Any],
    operating_temp: float,
    rng: np.random.Generator,
) -> float:
    min_block = profile["min_operating_temperature"]
    envelope_lo = float(min_block["min"])
    envelope_hi = float(min_block["max"])

    if _profile_is_cold_service(profile):
        offset = float(rng.uniform(*_COLD_SERVICE_MIN_OFFSET))
        drawn = operating_temp - offset
        drawn = max(envelope_lo, min(drawn, envelope_hi))
    else:
        drawn = float(rng.uniform(envelope_lo, envelope_hi))

    drawn = min(drawn, operating_temp)
    return round(drawn, 1)


def _sample_max_operating_temperature(
    profile: Mapping[str, Any],
    operating_temp: float,
    max_excursion_fraction: float,
    rng: np.random.Generator,
) -> float:
    max_block = profile["max_operating_temperature"]
    envelope_lo = float(max_block["min"])
    envelope_hi = float(max_block["max"])

    if _profile_is_cold_service(profile):
        # Cold-service max is the table warm-up ceiling (10–25 °C or 0–10 °C).
        drawn = float(rng.uniform(envelope_lo, envelope_hi))
    else:
        # Hot / wide-swing: operating + ~10%, clamped to the table max envelope.
        derived = operating_temp * (1.0 + max_excursion_fraction)
        drawn = min(derived, envelope_hi)

    drawn = max(drawn, operating_temp, envelope_lo)
    drawn = min(drawn, envelope_hi)
    return round(drawn, 1)


def _repair_temperature_triplet(
    operating_temp: float,
    min_temp: float,
    max_temp: float,
) -> tuple[float, float]:
    """Ensure min <= operating <= max after rounding and clamping."""
    if min_temp > operating_temp:
        min_temp = operating_temp
    if max_temp < operating_temp:
        max_temp = operating_temp
    return round(min_temp, 1), round(max_temp, 1)


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
    """Nominal commissioning date: ``reference_date`` minus ``asset_age_years`` whole years."""
    return (reference - pd.DateOffset(years=int(asset_age_years))).normalize()


def parse_commissioning_timestamp(commissioning_date: str | pd.Timestamp) -> pd.Timestamp:
    """Parse ``asset_commissioning_date`` to a normalised timestamp."""
    return pd.Timestamp(str(commissioning_date)).normalize()


def asset_age_years_at_reference(
    reference: pd.Timestamp,
    commissioning: pd.Timestamp,
) -> float:
    """Whole-life years from commissioning to reference (for rule predicates)."""
    return years_between_timestamps(commissioning.normalize(), reference.normalize())


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
