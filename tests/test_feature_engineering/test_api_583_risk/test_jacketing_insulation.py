"""Tests for the API 583 jacketing/insulation-condition scorer.

Covers validation, the AVERAGE-default substitution for missing ratings,
the score-0 escape hatch (new system + both ABOVE_AVERAGE), the
worse-of-two cascade across all rating combinations, and symmetry.
"""

import pytest

from lean_virtual_sensor.feature_engineering.api_583_risk.input_features.jacketing_insulation import (
    score_jacketing_insulation_condition,
)


def _score(cladding=None, insulation=None, system_age=None):
    """Compact wrapper — defaults each input to None (treated as missing)."""
    return score_jacketing_insulation_condition(cladding, insulation, system_age)


# ====================================== Validation ======================================


def test_unknown_cladding_integrity_raises():
    with pytest.raises(ValueError, match="Bad cladding_integrity"):
        _score(cladding="CORRODED", insulation="AVERAGE")


def test_unknown_insulation_condition_raises():
    with pytest.raises(ValueError, match="Bad insulation_condition"):
        _score(cladding="AVERAGE", insulation="WET")


def test_lowercase_rating_raises():
    # Ratings are upper-case enums; lower-case strings must not be
    # silently normalised.
    with pytest.raises(ValueError):
        _score(cladding="above_average", insulation="AVERAGE")


def test_negative_system_age_raises():
    with pytest.raises(ValueError, match="system_age_years is negative"):
        _score(cladding="AVERAGE", insulation="AVERAGE", system_age=-1)


# ====================================== Missing-rating defaults ======================================


def test_missing_cladding_defaults_to_average():
    # cladding None + insulation ABOVE → worse = AVERAGE → 3.
    assert _score(cladding=None, insulation="ABOVE_AVERAGE") == 3


def test_missing_insulation_defaults_to_average():
    # cladding ABOVE + insulation None → worse = AVERAGE → 3.
    assert _score(cladding="ABOVE_AVERAGE", insulation=None) == 3


def test_both_missing_defaults_to_score_3():
    # Both default to AVERAGE → worse = AVERAGE → 3.
    assert _score(cladding=None, insulation=None) == 3


def test_missing_rating_does_not_mask_below_average():
    # Missing rating defaults to AVERAGE, but BELOW_AVERAGE on the other
    # still dominates → 5.
    assert _score(cladding=None, insulation="BELOW_AVERAGE") == 5


# ====================================== Score 0 escape hatch ======================================


def test_new_system_both_above_average_scores_0():
    assert _score(cladding="ABOVE_AVERAGE", insulation="ABOVE_AVERAGE", system_age=2.5) == 0


def test_zero_age_with_both_above_average_scores_0():
    # Boundary: system_age = 0 still qualifies (< 5).
    assert _score(cladding="ABOVE_AVERAGE", insulation="ABOVE_AVERAGE", system_age=0.0) == 0


def test_age_at_5_does_not_qualify_for_score_0():
    # system_age = 5 fails the strict `< 5` clause; falls through to 1.
    assert _score(cladding="ABOVE_AVERAGE", insulation="ABOVE_AVERAGE", system_age=5.0) == 1


def test_unknown_system_age_does_not_qualify_for_score_0():
    # system_age None fails the `is not None` clause; falls through to 1.
    assert _score(cladding="ABOVE_AVERAGE", insulation="ABOVE_AVERAGE", system_age=None) == 1


def test_score_0_requires_both_ratings_above_average():
    # One AVERAGE blocks score 0 even with a brand-new system → 3.
    assert _score(cladding="ABOVE_AVERAGE", insulation="AVERAGE", system_age=1.0) == 3


def test_below_average_dominates_even_with_new_system():
    # BELOW_AVERAGE on either side overrides the score-0 escape hatch.
    assert _score(cladding="BELOW_AVERAGE", insulation="ABOVE_AVERAGE", system_age=1.0) == 5


# ====================================== Worse-of-two cascade ======================================


@pytest.mark.parametrize(
    "cladding, insulation, expected_score",
    [
        # Any BELOW_AVERAGE → 5
        ("BELOW_AVERAGE", "BELOW_AVERAGE", 5),
        ("BELOW_AVERAGE", "AVERAGE", 5),
        ("BELOW_AVERAGE", "ABOVE_AVERAGE", 5),
        ("AVERAGE", "BELOW_AVERAGE", 5),
        ("ABOVE_AVERAGE", "BELOW_AVERAGE", 5),
        # Worse = AVERAGE → 3
        ("AVERAGE", "AVERAGE", 3),
        ("AVERAGE", "ABOVE_AVERAGE", 3),
        ("ABOVE_AVERAGE", "AVERAGE", 3),
    ],
)
def test_worse_of_two_cascade(cladding, insulation, expected_score):
    # No system_age, so the score-0 escape hatch doesn't fire and the
    # cascade is purely worse-of-two.
    assert _score(cladding=cladding, insulation=insulation, system_age=None) == expected_score


def test_both_above_average_old_system_scores_1():
    assert _score(cladding="ABOVE_AVERAGE", insulation="ABOVE_AVERAGE", system_age=10.0) == 1


# ====================================== Symmetry ======================================


@pytest.mark.parametrize(
    "rating_a, rating_b",
    [
        ("BELOW_AVERAGE", "AVERAGE"),
        ("BELOW_AVERAGE", "ABOVE_AVERAGE"),
        ("AVERAGE", "ABOVE_AVERAGE"),
    ],
)
def test_score_is_symmetric_in_two_ratings(rating_a, rating_b):
    # The worse-of-two logic must not depend on which rating is the
    # cladding and which is the insulation.
    forward = _score(rating_a, rating_b, system_age=10.0)
    reversed_ = _score(rating_b, rating_a, system_age=10.0)
    assert forward == reversed_
