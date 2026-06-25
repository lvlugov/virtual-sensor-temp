"""Tests for the API 583 coating-age scorer.

Covers validation, legacy-code mapping, the four score tiers
(5-escalations, 0, 1, 3 rules), cascade-priority cross-cases where
multiple rules could apply, fallback behaviour, and the class-specific
bucket boundaries for Quality, General, and system age.
"""

import pytest
from lean_virtual_sensor.feature_engineering.api_583_risk.input_features.coating_age import (
    score_coating_age,
)


def _score(coating_system, coating_age=None, system_age=None):
    """Compact wrapper — defaults both ages to None so each test opts in
    to the age inputs that matter for its case."""
    return score_coating_age(coating_system, coating_age, system_age)


# ====================================== Validation ======================================


def test_unknown_coating_system_raises():
    with pytest.raises(ValueError, match="Unknown coating_system"):
        _score("TEFLON", coating_age=5, system_age=10)


def test_negative_coating_age_raises():
    with pytest.raises(ValueError, match="coating_age_years is negative"):
        _score("TSA", coating_age=-1)


def test_negative_system_age_raises():
    with pytest.raises(ValueError, match="system_age_years is negative"):
        _score("TSA", coating_age=5, system_age=-1)


# ===================================== Legacy coating mapping =====================================


def test_legacy_epoxy_aged_treated_as_unknown():
    # EPOXY_AGED is silently mapped to UNKNOWN → score 5 regardless of ages.
    assert _score("EPOXY_AGED", coating_age=2, system_age=5) == 5


# ====================================== Score 5 escalations ======================================


def test_unknown_coating_returns_5():
    assert _score("UNKNOWN", coating_age=2, system_age=5) == 5


def test_bare_substrate_returns_5():
    assert _score("BARE", coating_age=2, system_age=5) == 5


def test_system_age_at_30_escalates_to_5():
    # system_age ≥ 30 escalates regardless of class or coating age.
    assert _score("TSA", coating_age=2, system_age=30) == 5


def test_system_age_above_30_escalates_to_5():
    assert _score("EPOXY_HT_SINGLE", coating_age=5, system_age=40) == 5


def test_general_coating_above_15_escalates_to_5():
    # General coating > 15 yr escalates even when system age would otherwise
    # produce a lower score.
    assert _score("EPOXY_HT_SINGLE", coating_age=16, system_age=None) == 5


# ====================================== Score 0 rules ======================================


def test_quality_coating_under_8_scores_0():
    assert _score("TSA", coating_age=5, system_age=None) == 0


def test_system_age_under_15_overrides_quality_mid_band():
    # Quality + coating 10 would score 1, but system < 15 fires first → 0.
    assert _score("TSA", coating_age=10, system_age=5) == 0


# ====================================== Score 1 rules ======================================


def test_quality_coating_in_8_to_15_scores_1():
    assert _score("TSA", coating_age=10, system_age=None) == 1


def test_system_age_15_to_30_scores_1():
    # Quality coating ≥ 15 yr has no Quality-specific band; the system
    # bucket fills in.
    assert _score("TSA", coating_age=20, system_age=20) == 1


# ====================================== Score 3 rules ======================================


def test_general_coating_8_to_15_with_no_system_info_scores_3():
    assert _score("EPOXY_HT_SINGLE", coating_age=10, system_age=None) == 3


def test_general_coating_under_8_with_no_system_info_scores_3():
    assert _score("EPOXY_HT_SINGLE", coating_age=5, system_age=None) == 3


# ================================== Cascade priority cross-cases ==================================


def test_quality_old_coating_with_mid_system_scores_1():
    # Quality coating ≥ 15 → no Quality band; system 15-30 picks up → 1.
    assert _score("TSA", coating_age=18, system_age=20) == 1


def test_general_mid_coating_with_mid_system_scores_1():
    # General + coating 10 alone would be 3, but system 20 (15-30) fires
    # earlier in the cascade → 1.
    assert _score("EPOXY_HT_SINGLE", coating_age=10, system_age=20) == 1


def test_general_old_coating_escalates_over_low_system():
    # General + coating > 15 escalation fires before the system <15 → 0 rule.
    assert _score("EPOXY_HT_SINGLE", coating_age=20, system_age=5) == 5


def test_old_system_overrides_quality_low_coating():
    # system_age ≥ 30 escalation fires above the Quality <8 → 0 rule.
    assert _score("TSA", coating_age=5, system_age=35) == 5


# ====================================== Fallback ======================================


def test_no_age_data_defaults_to_5():
    assert _score("TSA", coating_age=None, system_age=None) == 5


def test_quality_old_coating_with_no_system_defaults_to_5():
    # Quality + coating ≥ 15 + no system info → no rule matches → 5.
    assert _score("TSA", coating_age=20, system_age=None) == 5


# =================================== Quality coating boundaries ===================================


@pytest.mark.parametrize(
    "coating_age, expected_score",
    [
        (0.0, 0),  # bottom of <8 band
        (7.99, 0),  # just under transition
        (8.0, 1),  # transition <8 → 8-15
        (14.99, 1),  # just under transition
        (15.0, 5),  # ≥15 → no Quality band, no system info → fallback 5
    ],
)
def test_quality_coating_age_boundaries(coating_age, expected_score):
    assert _score("TSA", coating_age=coating_age, system_age=None) == expected_score


# =================================== General coating boundaries ===================================


@pytest.mark.parametrize(
    "coating_age, expected_score",
    [
        (0.0, 3),
        (7.99, 3),
        (8.0, 3),
        (15.0, 3),  # closed upper boundary still inside General bucket
        (15.01, 5),  # transition into >15 escalation
    ],
)
def test_general_coating_age_boundaries(coating_age, expected_score):
    assert _score("EPOXY_HT_SINGLE", coating_age=coating_age, system_age=None) == expected_score


# ==================================== System age boundaries ====================================


@pytest.mark.parametrize(
    "system_age, expected_score",
    [
        (0.0, 0),  # bottom of <15 band
        (14.99, 0),
        (15.0, 1),  # transition <15 → 15-30
        (29.99, 1),
        (30.0, 5),  # transition 15-30 → escalation
    ],
)
def test_system_age_boundaries(system_age, expected_score):
    # Use TSA (Quality) with no coating age so the system bands are
    # isolated — no Quality coating rules fire.
    assert _score("TSA", coating_age=None, system_age=system_age) == expected_score


# ====================================== Class equivalence ======================================


def test_all_quality_codes_use_same_table():
    # coating_age = 10 → Quality 8-15 band → score 1.
    assert _score("TSA", 10.0, None) == 1
    assert _score("IOZ", 10.0, None) == 1
    assert _score("EPOXY_HT_MULTI", 10.0, None) == 1


def test_general_code_uses_general_table():
    # EPOXY_HT_SINGLE is the only General-class code; coating_age 10 → 3.
    assert _score("EPOXY_HT_SINGLE", coating_age=10) == 3
