"""Per-asset feature row builder.

Wires the per-asset feature primitives together into a single dict that
the model consumes as one row of its training / scoring DataFrame.

Per model run, for each asset:

  1. Derive scalar ages from inventory dates    →  age_features.compute_age_years
  2. Derive the most recent inspection date     →  max(inspection_record_dates)
  3. Derive the open/closed system flag         →  system_flag_feature.is_open_system
  4. Compute Active CUI Hours (last 90 days)    →  asset_temperature.compute_ach_for_asset
  5. Count T_skin cooldown cycles (same window) →  asset_temperature.compute_cycles_for_asset
  6. Compute historical wet load (pre-90-day)   →  historical_weather_feature.compute_wet_load
  7. Combine raw inventory + derived features into one flat dict

The orchestrator stays a pure transformation on its inputs: it does not
fetch weather, does not write to disk, and does not score (the API 583
scorers are downstream consumers of the dict this function returns).

Note on imports: ``compute_wet_load`` is provided by the
``historical_weather_feature`` module, which lives in a sibling branch
that merges with this one — the import is here in anticipation of that
merge.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from lean_virtual_sensor.feature_engineering.age_features import compute_age_years
from lean_virtual_sensor.feature_engineering.asset_temperature import (
    compute_ach_for_asset,
)
from lean_virtual_sensor.feature_engineering.cycle_features import (
    compute_cycles_for_asset,
)
from lean_virtual_sensor.feature_engineering.historical_weather_feature import (
    compute_wet_load,
)
from lean_virtual_sensor.feature_engineering.system_flag_feature import is_open_system


def compute_features_for_asset(
    asset_inventory: dict[str, Any],
    weather_df: pd.DataFrame,
    process_history_df: pd.DataFrame,
    today: pd.Timestamp,
) -> dict[str, Any]:
    """Assemble one row of the feature DataFrame from raw inputs.

    Args:
        asset_inventory: Static asset attributes (operator, site, geometry,
            metallurgy, condition strings, dates, etc.) — one row of the
            fleet inventory. Required keys:
            ``coating_application_date``, ``insulation_install_date``,
            ``inspection_record_dates``, ``insulation_condition``,
            ``cladding_integrity``, ``insulation_material``,
            ``insulation_thickness``, ``component_diameter``,
            ``furnished_thickness``. All other keys pass through to the
            output unchanged.
        weather_df: Hourly weather cache for this asset's location.
            Columns ``datetime``, ``temp``, ``dew``, ``humidity``, ``precip``.
        process_history_df: Hourly process-historian data for the asset.
            Columns ``datetime``, ``process_temperature_c``.
        today: Reference date for the model run. Drives every time-based
            derivation (ages, ACH window, wet-load window).

    Returns:
        Flat dict combining the raw inventory passthrough with seven
        derived features: ``coating_age_years``, ``system_age_years``,
        ``last_inspection_date``, ``open_system``, ``ach_90d``,
        ``cycle_count``, ``wet_load``.

    Raises:
        KeyError: If ``asset_inventory`` is missing a required field.
        ValueError: If ``inspection_record_dates`` is empty, or
            propagated from a downstream primitive (bad geometry,
            future-dated coating, RH out of range, etc.).
    """
    coating_age_years = compute_age_years(
        asset_inventory["coating_application_date"], today,
    )
    system_age_years = compute_age_years(
        asset_inventory["insulation_install_date"], today,
    )

    inspection_dates = asset_inventory["inspection_record_dates"]
    if not inspection_dates:
        raise ValueError("inspection_record_dates is empty")
    last_inspection_date = max(inspection_dates)

    open_system = is_open_system(
        asset_inventory["insulation_condition"],
        asset_inventory["cladding_integrity"],
    )

    ach_90d = compute_ach_for_asset(
        asset_inventory["insulation_material"],
        asset_inventory["insulation_thickness"],
        asset_inventory["component_diameter"],
        asset_inventory["furnished_thickness"],
        asset_inventory["insulation_condition"],
        asset_inventory["cladding_integrity"],
        weather_df,
        process_history_df,
        last_inspection_date,
        today,
    )
    cycle_count = compute_cycles_for_asset(
        asset_inventory["insulation_material"],
        asset_inventory["insulation_thickness"],
        asset_inventory["component_diameter"],
        asset_inventory["furnished_thickness"],
        weather_df,
        process_history_df,
        last_inspection_date,
        today,
    )
    wet_load = compute_wet_load(
        weather_df,
        last_inspection_date,
        today,
        open_system,
    )

    return {
        **asset_inventory,
        "coating_age_years": coating_age_years,
        "system_age_years": system_age_years,
        "last_inspection_date": last_inspection_date,
        "open_system": open_system,
        "ach_90d": ach_90d,
        "cycle_count": cycle_count,
        "wet_load": wet_load,
    }
