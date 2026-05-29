"""
DAG-step generators for synthetic input rows.

Each public function fills one methodology slice of columns (see
``docs/synthetic_inputs_methodology.md`` §4). Signature::

    fn(dataframe: pd.DataFrame, config: GeneratorConfig, rng: np.random.Generator)
        -> pd.DataFrame

Each public function returns a **new** ``DataFrame``; the input frame is left
unchanged.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from generation_helpers import (
    commissioning_timestamp,
    conditional_weights_block,
    random_lookback_timestamp,
    random_timestamp_uniform_between,
    reference_timestamp,
    sample_first_matching_weighted_rule,
    sample_geometry_class_for_asset_class,
    sample_weighted_category,
    sample_weighted_category_column,
    schema_categorical_choices,
    schema_float_range_bounds,
    schema_integer_range_bounds,
    years_between_timestamps,
)
from schema_loader import GeneratorConfig


def generate_anchors(
    dataframe: pd.DataFrame,
    config: GeneratorConfig,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """
    DAG layer 1 — independent anchors: ``asset_class``, ``exposure_zone``,
    ``metallurgy_family``, ``asset_age`` (methodology §4).
    """
    result = dataframe.copy()
    generation_yaml = config.generation
    row_count = len(result)

    proportions = generation_yaml["asset_class_proportions"]
    asset_class_keys = [str(key) for key in proportions]
    configured_counts = np.array([int(proportions[k]) for k in asset_class_keys], dtype=int)
    configured_total = int(configured_counts.sum())

    if configured_total == row_count:
        shuffled_classes: list[str] = []
        for asset_class_key, count in zip(asset_class_keys, configured_counts):
            shuffled_classes.extend([asset_class_key] * int(count))
        rng.shuffle(shuffled_classes)
    else:
        # e.g. tests with a partial DataFrame: match target row count but keep class mix.
        if row_count == 0:
            shuffled_classes = []
        else:
            probabilities = configured_counts.astype(float) / float(configured_total)
            allocated = rng.multinomial(row_count, probabilities)
            shuffled_classes = []
            for asset_class_key, count in zip(asset_class_keys, allocated):
                shuffled_classes.extend([asset_class_key] * int(count))
            rng.shuffle(shuffled_classes)

    result["asset_class"] = shuffled_classes

    exposure_weights = generation_yaml["exposure_zone_weights"]
    result["exposure_zone"] = sample_weighted_category_column(
        rng, exposure_weights, row_count
    )

    metallurgy_block = conditional_weights_block(config, "metallurgy_family")
    if metallurgy_block is None:
        raise ValueError("conditional_rules.conditional_weights.metallurgy_family is required")
    metallurgy_rules = metallurgy_block.get("rules", [])

    metallurgy_series: list[str] = []
    for row_index in range(row_count):
        row_context_for_metallurgy = {
            "exposure_zone": result.at[row_index, "exposure_zone"],
        }
        metallurgy_series.append(
            sample_first_matching_weighted_rule(
                metallurgy_rules, row_context_for_metallurgy, rng
            )
        )
    result["metallurgy_family"] = metallurgy_series

    age_low, age_high = schema_integer_range_bounds(config.schema, "asset_age")
    result["asset_age"] = rng.integers(age_low, age_high + 1, size=row_count)

    return result


def generate_geometry(
    dataframe: pd.DataFrame,
    config: GeneratorConfig,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """
    DAG layer 2 — ``geometry_class``, ``geometry_complexity``, ``orientation``,
    ``shelter_flag``, ``tracing_system`` (methodology §4). ``tracing_system`` is
    preliminary until :func:`generate_operating` supplies ``operating_temperature``.
    """
    result = dataframe.copy()
    row_count = len(result)
    asset_class_config = config.asset_class
    shelter_choices = schema_categorical_choices(config.schema, "shelter_flag")

    tracing_block = conditional_weights_block(config, "tracing_system")
    if tracing_block is None:
        raise ValueError("conditional_rules.conditional_weights.tracing_system is required")
    tracing_rules = tracing_block.get("rules", [])

    geometry_classes: list[str] = []
    geometry_complexities: list[str] = []
    orientations: list[str] = []
    shelter_flags: list[str] = []
    tracing_systems: list[str] = []

    for row_index in range(row_count):
        asset_class_key = str(result.at[row_index, "asset_class"])
        class_config = asset_class_config.get(asset_class_key)
        if not isinstance(class_config, dict):
            raise ValueError(f"Unknown asset_class {asset_class_key!r} in asset_class_config.yaml")

        geometry_classes.append(sample_geometry_class_for_asset_class(class_config, rng))
        geometry_complexities.append(
            sample_weighted_category(rng, class_config["geometry_complexity_weights"])
        )
        orientations.append(sample_weighted_category(rng, class_config["orientation_weights"]))
        shelter_flags.append(str(rng.choice(shelter_choices)))

        # No operating temperature yet: only predicates satisfiable without it match.
        row_context_for_tracing: dict[str, Any] = {}
        tracing_systems.append(
            sample_first_matching_weighted_rule(tracing_rules, row_context_for_tracing, rng)
        )

    result["geometry_class"] = geometry_classes
    result["geometry_complexity"] = geometry_complexities
    result["orientation"] = orientations
    result["shelter_flag"] = shelter_flags
    result["tracing_system"] = tracing_systems

    return result


def generate_wall_insulation(
    dataframe: pd.DataFrame,
    config: GeneratorConfig,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """
    DAG layer 3 — ``component_diameter``, ``furnished_thickness``,
    ``insulation_material``, ``insulation_thickness`` (methodology §4).
    """
    result = dataframe.copy()
    row_count = len(result)
    asset_class_config = config.asset_class

    insulation_material_block = conditional_weights_block(config, "insulation_material")
    if insulation_material_block is None:
        raise ValueError("conditional_rules.conditional_weights.insulation_material is required")
    insulation_material_rules = insulation_material_block.get("rules", [])

    schema_insulation_thickness_low, schema_insulation_thickness_high = (
        schema_float_range_bounds(config.schema, "insulation_thickness")
    )

    component_diameters: list[float] = []
    furnished_thicknesses: list[float] = []
    insulation_materials: list[str] = []
    insulation_thicknesses: list[float] = []

    for row_index in range(row_count):
        asset_class_key = str(result.at[row_index, "asset_class"])
        class_config = asset_class_config.get(asset_class_key)
        if not isinstance(class_config, dict):
            raise ValueError(f"Unknown asset_class {asset_class_key!r} in asset_class_config.yaml")

        diameter_limits = class_config["component_diameter"]
        wall_limits = class_config["furnished_thickness"]
        insulation_thickness_limits = class_config["insulation_thickness"]

        diameter_low, diameter_high = float(diameter_limits["min"]), float(diameter_limits["max"])
        wall_low, wall_high = float(wall_limits["min"]), float(wall_limits["max"])
        insul_mm_low, insul_mm_high = float(insulation_thickness_limits["min"]), float(
            insulation_thickness_limits["max"]
        )

        component_diameters.append(round(float(rng.uniform(diameter_low, diameter_high)), 1))
        furnished_thicknesses.append(round(float(rng.uniform(wall_low, wall_high)), 2))

        row_context_for_insulation = {
            "exposure_zone": result.at[row_index, "exposure_zone"],
        }
        insulation_materials.append(
            sample_first_matching_weighted_rule(
                insulation_material_rules, row_context_for_insulation, rng
            )
        )

        raw_insulation_thickness = float(rng.uniform(insul_mm_low, insul_mm_high))
        clipped = max(
            schema_insulation_thickness_low,
            min(schema_insulation_thickness_high, raw_insulation_thickness),
        )
        insulation_thicknesses.append(float(round(clipped)))

    result["component_diameter"] = component_diameters
    result["furnished_thickness"] = furnished_thicknesses
    result["insulation_material"] = insulation_materials
    result["insulation_thickness"] = insulation_thicknesses

    return result


def generate_dates(
    dataframe: pd.DataFrame,
    config: GeneratorConfig,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """
    DAG layer 4 — insulation / coating / inspection dates and ``coating_system``
    (methodology §4). Applies Tier‑1 epoxy downgrade when coating age > 10 years.
    """
    result = dataframe.copy()
    generation_yaml = config.generation
    reference_ts = reference_timestamp(generation_yaml)
    date_generation = generation_yaml["date_generation"]
    inspection_years_min = float(date_generation["inspection_age_min_years"])
    inspection_years_max = float(date_generation["inspection_age_max_years"])

    coating_block = conditional_weights_block(config, "coating_system")
    if coating_block is None:
        raise ValueError("conditional_rules.conditional_weights.coating_system is required")
    coating_rules = coating_block.get("rules", [])

    row_count = len(result)
    insulation_dates: list[str] = []
    coating_dates: list[str] = []
    inspection_dates: list[str] = []
    coating_systems: list[str] = []

    for row_index in range(row_count):
        asset_age_years = int(result.at[row_index, "asset_age"])
        commissioning_ts = commissioning_timestamp(reference_ts, asset_age_years)

        insulation_ts = random_timestamp_uniform_between(
            rng, commissioning_ts, reference_ts
        )
        insulation_dates.append(insulation_ts.date().isoformat())

        coating_ts = random_timestamp_uniform_between(rng, commissioning_ts, reference_ts)
        coating_dates.append(coating_ts.date().isoformat())

        inspection_earliest = max(
            commissioning_ts.normalize(),
            insulation_ts.normalize(),
        )
        inspection_ts = random_lookback_timestamp(
            rng,
            reference_ts,
            inspection_years_min,
            inspection_years_max,
            inspection_earliest,
        )
        inspection_dates.append(inspection_ts.date().isoformat())

        row_context_for_coating = {
            "asset_age": asset_age_years,
            "exposure_zone": result.at[row_index, "exposure_zone"],
        }
        coating_system = sample_first_matching_weighted_rule(
            coating_rules, row_context_for_coating, rng
        )

        coating_age_years = years_between_timestamps(coating_ts, reference_ts)
        if coating_age_years > 10.0 and coating_system in (
            "EPOXY_HT_MULTI",
            "EPOXY_HT_SINGLE",
        ):
            coating_system = "EPOXY_AGED"

        coating_systems.append(coating_system)

    result["insulation_install_date"] = insulation_dates
    result["coating_application_date"] = coating_dates
    result["coating_system"] = coating_systems
    result["inspection_record_dates"] = inspection_dates

    return result


def generate_operating(
    dataframe: pd.DataFrame,
    config: GeneratorConfig,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """
    DAG layer 5 — operating temperature triplet, cycling, on‑line fraction, and
    final ``tracing_system`` using ``operating_temperature`` in rule context.
    """
    result = dataframe.copy()
    generation_yaml = config.generation
    metallurgy_ranges = generation_yaml["operating_temperature_ranges"]["by_metallurgy"]
    cycling_weights = generation_yaml["cycling_grade_weights"]
    cycling_ranges = generation_yaml["cycling_grade_ranges"]

    tracing_block = conditional_weights_block(config, "tracing_system")
    if tracing_block is None:
        raise ValueError("conditional_rules.conditional_weights.tracing_system is required")
    tracing_rules = tracing_block.get("rules", [])

    schema_op_low, schema_op_high = schema_float_range_bounds(
        config.schema, "operating_temperature"
    )

    row_count = len(result)
    operating_temps: list[float] = []
    min_temps: list[float] = []
    max_temps: list[float] = []
    avg_cycles: list[int] = []
    op_vs_shutdown: list[float] = []
    tracing_final: list[str] = []

    for row_index in range(row_count):
        metallurgy = str(result.at[row_index, "metallurgy_family"])
        if metallurgy not in metallurgy_ranges:
            raise KeyError(
                "No operating_temperature_ranges.by_metallurgy entry for "
                f"{metallurgy!r}"
            )
        raw_lo, raw_hi = metallurgy_ranges[metallurgy]
        draw_lo = max(schema_op_low, float(raw_lo))
        draw_hi = min(schema_op_high, float(raw_hi))
        if draw_lo > draw_hi:
            draw_lo, draw_hi = draw_hi, draw_lo

        operating_temp = round(float(rng.uniform(draw_lo, draw_hi)), 1)

        span_below = float(rng.uniform(5.0, 40.0))
        span_above = float(rng.uniform(5.0, 40.0))
        min_temp = round(max(schema_op_low, operating_temp - span_below), 1)
        max_temp = round(min(schema_op_high, operating_temp + span_above), 1)
        if min_temp > operating_temp:
            min_temp = operating_temp
        if max_temp < operating_temp:
            max_temp = operating_temp

        cycling_grade = sample_weighted_category(rng, cycling_weights)
        cycle_lo, cycle_hi = cycling_ranges[cycling_grade]
        avg_cycle_val = int(rng.integers(int(cycle_lo), int(cycle_hi) + 1))

        onstream_fraction = round(float(rng.uniform(0.0, 1.0)), 2)

        row_context_for_tracing = {"operating_temperature": operating_temp}
        tracing_choice = sample_first_matching_weighted_rule(
            tracing_rules, row_context_for_tracing, rng
        )

        operating_temps.append(operating_temp)
        min_temps.append(min_temp)
        max_temps.append(max_temp)
        avg_cycles.append(avg_cycle_val)
        op_vs_shutdown.append(onstream_fraction)
        tracing_final.append(tracing_choice)

    result["operating_temperature"] = operating_temps
    result["min_operating_temperature"] = min_temps
    result["max_operating_temperature"] = max_temps
    result["avg_cycles_per_quarter"] = avg_cycles
    result["operation_vs_shutdown_fraction"] = op_vs_shutdown
    result["tracing_system"] = tracing_final

    return result


def generate_insulation_flags(
    dataframe: pd.DataFrame,
    config: GeneratorConfig,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """DAG layer 6 — chloride flag, insulation condition, cladding integrity."""
    result = dataframe.copy()
    generation_yaml = config.generation
    reference_ts = reference_timestamp(generation_yaml)

    insulation_block = conditional_weights_block(config, "insulation_condition")
    if insulation_block is None:
        raise ValueError("conditional_rules.conditional_weights.insulation_condition is required")
    insulation_rules = insulation_block.get("rules", [])

    cladding_block = conditional_weights_block(config, "cladding_integrity")
    if cladding_block is None:
        raise ValueError("conditional_rules.conditional_weights.cladding_integrity is required")
    cladding_rules = cladding_block.get("rules", [])

    row_count = len(result)
    chloride_flags: list[bool] = []
    insulation_conditions: list[str] = []
    cladding_integrities: list[str] = []

    for row_index in range(row_count):
        insulation_ts = pd.Timestamp(str(result.at[row_index, "insulation_install_date"]))
        insulation_age_years = years_between_timestamps(insulation_ts, reference_ts)
        exposure_zone = str(result.at[row_index, "exposure_zone"])
        insulation_material = str(result.at[row_index, "insulation_material"])
        asset_age_years = int(result.at[row_index, "asset_age"])

        tier1_chloride = (
            exposure_zone == "MARINE"
            and insulation_material == "CALCIUM_SILICATE"
            and insulation_age_years > 5.0
        )
        chloride_flags.append(bool(tier1_chloride))

        row_ctx_insulation = {
            "insulation_age_years": insulation_age_years,
            "exposure_zone": exposure_zone,
            "asset_age": asset_age_years,
        }
        insulation_conditions.append(
            sample_first_matching_weighted_rule(
                insulation_rules, row_ctx_insulation, rng
            )
        )

        row_ctx_cladding = {"asset_age": asset_age_years}
        cladding_integrities.append(
            sample_first_matching_weighted_rule(cladding_rules, row_ctx_cladding, rng)
        )

    result["insulation_chloride_flag"] = chloride_flags
    result["insulation_condition"] = insulation_conditions
    result["cladding_integrity"] = cladding_integrities

    return result


def generate_thickness_washdown(
    dataframe: pd.DataFrame,
    config: GeneratorConfig,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """DAG layer 7 — UT thickness, washdown counts."""
    result = dataframe.copy()
    generation_yaml = config.generation
    wall_cfg = generation_yaml["wall_loss"]
    alpha = float(wall_cfg["alpha"])
    beta = float(wall_cfg["beta"])
    min_frac = float(wall_cfg["min_fraction"])
    max_frac = float(wall_cfg["max_fraction"])

    wash_lo, wash_hi = schema_integer_range_bounds(config.schema, "washdown_records")

    row_count = len(result)
    last_thicknesses: list[float] = []
    washdowns: list[int] = []

    for row_index in range(row_count):
        furnished = float(result.at[row_index, "furnished_thickness"])
        beta_draw = float(rng.beta(alpha, beta))
        wall_loss_fraction = min_frac + beta_draw * (max_frac - min_frac)
        raw_last = furnished * (1.0 - wall_loss_fraction)
        last_t = round(max(1.0, min(raw_last, furnished)), 2)
        last_thicknesses.append(last_t)
        washdowns.append(int(rng.integers(wash_lo, wash_hi + 1)))

    result["last_inspection_thickness"] = last_thicknesses
    result["washdown_records"] = washdowns

    return result
