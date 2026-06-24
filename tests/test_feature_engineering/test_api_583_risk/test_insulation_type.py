"""Tests for the API 583 insulation-type scorer.

Covers validation, the ``None`` → ``"UNKNOWN"`` default, each material's
score, and score-grouping invariants by water-handling behaviour. The
material → score mapping lives in ``api_583_risk/config.yaml``.
"""

import pytest
from lean_virtual_sensor.feature_engineering.api_583_risk.input_features.insulation_type import (
    score_insulation_type,
)

# ====================================== Validation ======================================


def test_unknown_insulation_material_raises():
    with pytest.raises(ValueError, match="Bad insulation_material"):
        score_insulation_type("AEROGEL")


def test_lowercase_material_rejected():
    with pytest.raises(ValueError):
        score_insulation_type("fiberglass")


# ====================================== Score by material ======================================


@pytest.mark.parametrize(
    "insulation_material, expected_score",
    [
        ("FOAMGLASS", 1),
        ("PEARLITE", 1),
        ("CALCIUM_SILICATE", 3),
        ("FIBERGLASS", 3),
        ("MINERAL_WOOL", 5),
        ("ASBESTOS", 5),
        ("UNKNOWN", 5),
    ],
)
def test_insulation_material_scores(insulation_material, expected_score):
    assert score_insulation_type(insulation_material) == expected_score


# ====================================== Missing-data default ======================================


def test_none_defaults_to_unknown():
    # insulation_material None → "UNKNOWN" → 5.
    assert score_insulation_type(None) == 5


# ====================================== Score-grouping invariants ======================================


def test_closed_cell_materials_score_1():
    # Foam glass and expanded perlite both have low water-wicking → 1.
    assert score_insulation_type("FOAMGLASS") == score_insulation_type("PEARLITE") == 1


def test_moderately_absorbent_materials_score_3():
    # Calcium silicate and fibreglass both score 3.
    assert score_insulation_type("CALCIUM_SILICATE") == score_insulation_type("FIBERGLASS") == 3


def test_high_risk_and_unknown_materials_score_5():
    # Standard mineral wool, asbestos (legacy), and unknown all → 5.
    assert (
        score_insulation_type("MINERAL_WOOL")
        == score_insulation_type("ASBESTOS")
        == score_insulation_type("UNKNOWN")
        == 5
    )


