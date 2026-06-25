"""Tests for the API 583 risk pipeline.

Covers the per-parameter pipeline (happy path, required-key
enforcement, optional-key tolerance, per-scorer pass-through) and the
full likelihood pipeline (Table A.7 / A.9 boundary mappings, the
stainless 18-20 gap, and the end-to-end return shape).
"""

import pytest
from lean_virtual_sensor.feature_engineering.api_583_risk.pipeline import (
    _map_carbon_steel_total,
    _map_stainless_steel_total,
    compute_api_583_likelihood,
    compute_api_583_scores,
)

# =============================== Per-parameter pipeline: happy path ===============================


def test_full_asset_returns_all_seven_scores():
    asset = {
        "metallurgy_family": "CARBON_STEEL",
        "operating_temperature": 90.0,
        "min_operating_temperature": 80.0,
        "max_operating_temperature": 100.0,
        "avg_cycles_per_quarter": 0,
        "coating_system": "TSA",
        "coating_age_years": 5.0,
        "system_age_years": 10.0,
        "cladding_integrity": "AVERAGE",
        "insulation_condition": "AVERAGE",
        "tracing_system": "ELECTRIC_TRACED",
        "exposure_zone": "TEMPERATE",
        "shelter_flag": "NORMAL",
        "sweating_asset": True,
        "insulation_material": "FOAMGLASS",
        "asset_class": "PIPE",
        "component_diameter": 100.0,
    }
    assert compute_api_583_scores(asset) == {
        "operating_temperature": 5,  # CARBON_STEEL @ 90 °C → CUI-peak bucket
        "coating_age": 0,  # Quality + 5 yr (< 8 yr)
        "jacketing_insulation": 3,  # AVERAGE / AVERAGE → worse = AVERAGE
        "heat_tracing": 1,  # electric tracing operating
        "external_environment": 3,  # TEMPERATE + non-zero ACH
        "insulation_type": 1,  # foam glass
        "line_size": 3,  # 2 in. < OD ≤ 6 in. NPS
    }


# ======================== Per-parameter pipeline: required-key enforcement ========================


def _minimal_required_asset():
    """Smallest dict that satisfies the pipeline — all 17 keys are required."""
    return {
        "metallurgy_family": "CARBON_STEEL",
        "operating_temperature": 90.0,
        "min_operating_temperature": 80.0,
        "max_operating_temperature": 100.0,
        "avg_cycles_per_quarter": 0,
        "coating_system": "TSA",
        "coating_age_years": 5.0,
        "system_age_years": 10.0,
        "cladding_integrity": "AVERAGE",
        "insulation_condition": "AVERAGE",
        "tracing_system": "NONE",
        "exposure_zone": "TEMPERATE",
        "shelter_flag": "NORMAL",
        "sweating_asset": True,
        "insulation_material": "FOAMGLASS",
        "asset_class": "PRESSURE_VESSEL",
        "component_diameter": None,
    }


@pytest.mark.parametrize(
    "missing_key",
    [
        "metallurgy_family",
        "operating_temperature",
        "min_operating_temperature",
        "max_operating_temperature",
        "avg_cycles_per_quarter",
        "coating_system",
        "coating_age_years",
        "system_age_years",
        "cladding_integrity",
        "insulation_condition",
        "tracing_system",
        "exposure_zone",
        "shelter_flag",
        "sweating_asset",
        "insulation_material",
        "asset_class",
        "component_diameter",
    ],
)
def test_missing_required_key_raises_key_error(missing_key):
    asset = _minimal_required_asset()
    del asset[missing_key]
    with pytest.raises(KeyError, match=missing_key):
        compute_api_583_scores(asset)


# ======================== Per-parameter pipeline: minimal-asset happy path ========================


def test_minimal_required_asset_runs():
    scores = compute_api_583_scores(_minimal_required_asset())
    assert set(scores) == {
        "operating_temperature",
        "coating_age",
        "jacketing_insulation",
        "heat_tracing",
        "external_environment",
        "insulation_type",
        "line_size",
    }
    assert all(isinstance(score, int) for score in scores.values())


def test_pipeline_ignores_extra_keys():
    asset = _minimal_required_asset()
    asset["site_id"] = "PLANT_42"
    asset["installed_by"] = "ACME Corp"
    scores = compute_api_583_scores(asset)
    assert len(scores) == 7


# ======================== Per-parameter pipeline: behavioural pass-through ========================


def test_equipment_asset_class_does_not_need_diameter():
    asset = _minimal_required_asset()
    asset["asset_class"] = "HEAT_EXCHANGER"
    assert compute_api_583_scores(asset)["line_size"] == 0


def test_pipe_without_diameter_raises():
    asset = _minimal_required_asset()
    asset["asset_class"] = "PIPE"
    with pytest.raises(ValueError, match="component_diameter is required"):
        compute_api_583_scores(asset)


def test_system_age_years_feeds_both_coating_and_jacketing_scorers():
    asset = _minimal_required_asset()
    asset["coating_system"] = "EPOXY_HT_SINGLE"
    asset["coating_age_years"] = 10.0
    asset["system_age_years"] = 35.0
    scores = compute_api_583_scores(asset)
    assert scores["coating_age"] == 5
    assert scores["jacketing_insulation"] == 3


# ======================== Likelihood mapping: Table A.7 (carbon/low-alloy) ========================


@pytest.mark.parametrize(
    "total, expected",
    [
        # Band A — total < 7
        (0, ("A", "ok")),
        (6, ("A", "ok")),
        # Band B — 7 ≤ total < 14
        (7, ("B", "ok")),
        (13, ("B", "ok")),
        # Band C — 14 ≤ total ≤ 20
        (14, ("C", "ok")),
        (20, ("C", "ok")),
        # Band D — 21 ≤ total ≤ 27
        (21, ("D", "ok")),
        (27, ("D", "ok")),
        # Band E — total > 27
        (28, ("E", "ok")),
        (35, ("E", "ok")),
    ],
)
def test_map_carbon_steel_total_boundaries(total, expected):
    assert _map_carbon_steel_total(total) == expected


# =================== Likelihood mapping: Table A.9 (stainless, with 18-20 gap) ===================


@pytest.mark.parametrize(
    "total, expected",
    [
        # Band A — total < 7
        (0, ("A", "ok")),
        (6, ("A", "ok")),
        # Band B — 7 ≤ total < 14
        (7, ("B", "ok")),
        (13, ("B", "ok")),
        # Band C — 14 ≤ total ≤ 17 (narrower than carbon steel)
        (14, ("C", "ok")),
        (17, ("C", "ok")),
        # Gap — 18 ≤ total ≤ 20 (undefined in the standard)
        (18, (None, "ss_gap_18_to_20")),
        (19, (None, "ss_gap_18_to_20")),
        (20, (None, "ss_gap_18_to_20")),
        # Band D — 21 ≤ total ≤ 27
        (21, ("D", "ok")),
        (27, ("D", "ok")),
        # Band E — total > 27
        (28, ("E", "ok")),
        (35, ("E", "ok")),
    ],
)
def test_map_stainless_steel_total_boundaries(total, expected):
    assert _map_stainless_steel_total(total) == expected


# ==================================== Likelihood end-to-end ====================================


def _representative_asset():
    """Same fully populated asset used in the per-parameter happy path."""
    return {
        "metallurgy_family": "CARBON_STEEL",
        "operating_temperature": 90.0,
        "min_operating_temperature": 80.0,
        "max_operating_temperature": 100.0,
        "avg_cycles_per_quarter": 0,
        "coating_system": "TSA",
        "coating_age_years": 5.0,
        "system_age_years": 10.0,
        "cladding_integrity": "AVERAGE",
        "insulation_condition": "AVERAGE",
        "tracing_system": "ELECTRIC_TRACED",
        "exposure_zone": "TEMPERATE",
        "shelter_flag": "NORMAL",
        "sweating_asset": True,
        "insulation_material": "FOAMGLASS",
        "asset_class": "PIPE",
        "component_diameter": 100.0,
    }


def test_likelihood_return_shape():
    # Five keys, scores is the per-parameter dict.
    result = compute_api_583_likelihood(_representative_asset())
    assert set(result) == {"scores", "total", "table_used", "likelihood", "flag"}
    assert set(result["scores"]) == {
        "operating_temperature",
        "coating_age",
        "jacketing_insulation",
        "heat_tracing",
        "external_environment",
        "insulation_type",
        "line_size",
    }


def test_total_equals_sum_of_parameter_scores():
    result = compute_api_583_likelihood(_representative_asset())
    assert result["total"] == sum(result["scores"].values())


def test_carbon_steel_representative_asset_lands_in_band_c():
    # Scores: 5 + 0 + 3 + 1 + 3 + 1 + 3 = 16 → Table A.7 band C.
    result = compute_api_583_likelihood(_representative_asset())
    assert result["total"] == 16
    assert result["table_used"] == "A.7"
    assert result["likelihood"] == "C"
    assert result["flag"] == "ok"


def test_stainless_steel_representative_asset_lands_in_band_c():
    # Same scores under AUSTENITIC_SS (90 °C still in the ECSCC-peak
    # range) → total 16 → Table A.9 band C.
    asset = _representative_asset()
    asset["metallurgy_family"] = "AUSTENITIC_SS"
    result = compute_api_583_likelihood(asset)
    assert result["total"] == 16
    assert result["table_used"] == "A.9"
    assert result["likelihood"] == "C"
    assert result["flag"] == "ok"


def test_stainless_steel_in_gap_returns_undefined_likelihood():
    # Same asset but swap foam glass (1) for mineral wool (5) → total
    # 16 - 1 + 5 = 20 → falls in the stainless gap.
    asset = _representative_asset()
    asset["metallurgy_family"] = "AUSTENITIC_SS"
    asset["insulation_material"] = "MINERAL_WOOL"
    result = compute_api_583_likelihood(asset)
    assert result["total"] == 20
    assert result["table_used"] == "A.9"
    assert result["likelihood"] is None
    assert result["flag"] == "ss_gap_18_to_20"


def test_duplex_stainless_uses_table_a_9():
    # DUPLEX_SS routes to Table A.9 the same as AUSTENITIC_SS.
    asset = _representative_asset()
    asset["metallurgy_family"] = "DUPLEX_SS"
    result = compute_api_583_likelihood(asset)
    assert result["table_used"] == "A.9"


def test_low_alloy_steel_uses_table_a_7():
    # LOW_ALLOY_STEEL routes to Table A.7 the same as CARBON_STEEL.
    asset = _representative_asset()
    asset["metallurgy_family"] = "LOW_ALLOY_STEEL"
    result = compute_api_583_likelihood(asset)
    assert result["table_used"] == "A.7"
