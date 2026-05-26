"""API 583 CUI risk — pipeline that runs all seven parameter scorers.

Takes a single asset's metadata as a mapping and produces either:

- the seven per-parameter scores (:func:`compute_api_583_scores`), or
- the full likelihood category (:func:`compute_api_583_likelihood`),
  which sums the scores and maps the total to a letter rating per
  API 583 Annex A Table A.7 (carbon/low-alloy steel) or Table A.9
  (austenitic/duplex stainless steel).

Required keys (those the underlying scorers cannot default) are read
with ``[]`` and raise ``KeyError`` if absent; optional keys are read
with ``.get()`` and propagate ``None`` to the scorer's own default
handling.

Likelihood-band thresholds and the carbon-steel family list live in
``api_583_risk/config.yaml``.
"""

from __future__ import annotations

from typing import Any

from lean_virtual_sensor.feature_engineering.api_583_risk._config import (
    load_api_583_section,
)
from lean_virtual_sensor.feature_engineering.api_583_risk.input_features.coating_age import (
    score_coating_age,
)
from lean_virtual_sensor.feature_engineering.api_583_risk.input_features.external_environment import (
    score_external_environment,
)
from lean_virtual_sensor.feature_engineering.api_583_risk.input_features.heat_tracing import (
    score_heat_tracing,
)
from lean_virtual_sensor.feature_engineering.api_583_risk.input_features.insulation_type import (
    score_insulation_type,
)
from lean_virtual_sensor.feature_engineering.api_583_risk.input_features.jacketing_insulation import (
    score_jacketing_insulation_condition,
)
from lean_virtual_sensor.feature_engineering.api_583_risk.input_features.line_size import (
    score_line_size,
)
from lean_virtual_sensor.feature_engineering.api_583_risk.input_features.operating_temperature import (
    score_operating_temperature,
)

CONFIG_SUBSECTION = "pipeline"
REQUIRED_KEYS = (
    "carbon_steel_families",
    "cs_band_a_max",
    "cs_band_b_max",
    "cs_band_c_max",
    "cs_band_d_max",
    "ss_band_a_max",
    "ss_band_b_max",
    "ss_band_c_max",
    "ss_gap_max",
    "ss_band_d_max",
)


# ====================================== Per-parameter pipeline ======================================


def compute_api_583_scores(asset: dict[str, Any]) -> dict[str, int]:
    """Run all seven API 583 parameter scorers for a single asset.

    Args:
        asset: Mapping of asset-metadata field name → value. All
            seventeen keys are required (no optional inputs): the
            five operating-temperature fields (``metallurgy_family``,
            ``operating_temperature``, ``min_operating_temperature``,
            ``max_operating_temperature``, ``avg_cycles_per_quarter``),
            ``coating_system``, ``coating_age_years``,
            ``system_age_years``, ``cladding_integrity``,
            ``insulation_condition``, ``tracing_system``,
            ``exposure_zone``, ``shelter_flag``, ``sweating_asset``,
            ``insulation_material``, ``asset_class``, and
            ``component_diameter``. Missing any key raises
            ``KeyError``; extra keys are ignored.

    Returns:
        Dict with one entry per API 583 parameter:
        ``operating_temperature``, ``coating_age``,
        ``jacketing_insulation``, ``heat_tracing``,
        ``external_environment``, ``insulation_type``, ``line_size``.
        Values are integer scores.

    Raises:
        KeyError: If any required key is missing from ``asset``.
        ValueError: If any scorer rejects its input (see each scorer's
            docstring).
    """
    return {
        "operating_temperature": score_operating_temperature(
            metallurgy_family=asset["metallurgy_family"],
            operating_temperature=asset["operating_temperature"],
            min_operating_temperature=asset["min_operating_temperature"],
            max_operating_temperature=asset["max_operating_temperature"],
            avg_cycles_per_quarter=asset["avg_cycles_per_quarter"],
        ),
        "coating_age": score_coating_age(
            coating_system=asset["coating_system"],
            coating_age_years=asset["coating_age_years"],
            system_age_years=asset["system_age_years"],
        ),
        "jacketing_insulation": score_jacketing_insulation_condition(
            cladding_integrity=asset["cladding_integrity"],
            insulation_condition=asset["insulation_condition"],
            system_age_years=asset["system_age_years"],
        ),
        "heat_tracing": score_heat_tracing(
            tracing_system=asset["tracing_system"],
        ),
        "external_environment": score_external_environment(
            exposure_zone=asset["exposure_zone"],
            shelter_flag=asset["shelter_flag"],
            sweating_asset=asset["sweating_asset"],
        ),
        "insulation_type": score_insulation_type(
            insulation_material=asset["insulation_material"],
        ),
        "line_size": score_line_size(
            asset_class=asset["asset_class"],
            component_diameter=asset["component_diameter"],
        ),
    }


# ====================================== Likelihood-table helpers ======================================


def _map_carbon_steel_total(total: int) -> tuple[str, str]:
    """Table A.7 — carbon/low-alloy steel total → ``(likelihood, flag)``."""
    cfg = load_api_583_section(CONFIG_SUBSECTION, REQUIRED_KEYS)
    if total <= cfg["cs_band_a_max"]:
        return ("A", "ok")
    if total <= cfg["cs_band_b_max"]:
        return ("B", "ok")
    if total <= cfg["cs_band_c_max"]:
        return ("C", "ok")
    if total <= cfg["cs_band_d_max"]:
        return ("D", "ok")
    return ("E", "ok")


def _map_stainless_steel_total(total: int) -> tuple[str | None, str]:
    """Table A.9 — stainless steel total → ``(likelihood, flag)``.

    The 18–20 band is undefined in the standard and returns
    ``(None, "ss_gap_18_to_20")``.
    """
    cfg = load_api_583_section(CONFIG_SUBSECTION, REQUIRED_KEYS)
    if total <= cfg["ss_band_a_max"]:
        return ("A", "ok")
    if total <= cfg["ss_band_b_max"]:
        return ("B", "ok")
    if total <= cfg["ss_band_c_max"]:
        return ("C", "ok")
    if total <= cfg["ss_gap_max"]:
        return (None, "ss_gap_18_to_20")
    if total <= cfg["ss_band_d_max"]:
        return ("D", "ok")
    return ("E", "ok")


# ====================================== Likelihood entry point ======================================


def compute_api_583_likelihood(asset: dict[str, Any]) -> dict[str, Any]:
    """Compute the API 583 CUI likelihood category for one asset.

    Sums the seven parameter scores and maps the total against either
    Table A.7 (carbon/low-alloy steel) or Table A.9 (stainless steel).

    Args:
        asset: Same shape as :func:`compute_api_583_scores`.

    Returns:
        Dict with keys ``scores`` (the per-parameter dict),
        ``total`` (``int``), ``table_used`` (``"A.7"`` or ``"A.9"``),
        ``likelihood`` (one of ``"A"``-``"E"`` or ``None`` for the
        stainless 18-20 gap), and ``flag`` (``"ok"`` or
        ``"ss_gap_18_to_20"``).

    Raises:
        KeyError, ValueError: Propagated from :func:`compute_api_583_scores`.
    """
    scores = compute_api_583_scores(asset)

    total = sum(scores.values())

    cfg = load_api_583_section(CONFIG_SUBSECTION, REQUIRED_KEYS)
    carbon_steel_families = set(cfg["carbon_steel_families"])
    if asset["metallurgy_family"] in carbon_steel_families:
        table_used = "A.7"
        likelihood, flag = _map_carbon_steel_total(total)
    else:  # AUSTENITIC_SS, DUPLEX_SS
        table_used = "A.9"
        likelihood, flag = _map_stainless_steel_total(total)

    return {
        "scores": scores,
        "total": total,
        "table_used": table_used,
        "likelihood": likelihood,
        "flag": flag,
    }
