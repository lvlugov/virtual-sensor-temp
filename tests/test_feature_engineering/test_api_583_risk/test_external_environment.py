"""Tests for the API 583 external-environment scorer.

Covers validation, the ``None`` defaults for the categorical inputs,
the score-0 escape hatch (``sweating_asset is False``), the
DAMAGED-shelter override, and the exposure-zone cascade.
"""

import pytest

from lean_virtual_sensor.feature_engineering.api_583_risk.input_features.external_environment import (
    score_external_environment,
)


def _score(exposure=None, shelter=None, sweating_asset=None):
    """Compact wrapper — each input defaults to None (treated as missing)."""
    return score_external_environment(exposure, shelter, sweating_asset)


# ====================================== Validation ======================================


def test_unknown_exposure_zone_raises():
    with pytest.raises(ValueError, match="Bad exposure_zone"):
        _score(exposure="TROPICAL", shelter="NORMAL")


def test_unknown_shelter_flag_raises():
    with pytest.raises(ValueError, match="Bad shelter_flag"):
        _score(exposure="TEMPERATE", shelter="EXPOSED")


def test_lowercase_enum_rejected():
    with pytest.raises(ValueError):
        _score(exposure="marine", shelter="NORMAL")


# ====================================== Missing-input defaults ======================================


def test_missing_exposure_defaults_to_temperate():
    # exposure None + NORMAL shelter + sweating None → TEMPERATE cascade → 3.
    assert _score(exposure=None, shelter="NORMAL") == 3


def test_missing_shelter_defaults_to_normal():
    # ARID_DRY exposure + shelter None → no DAMAGED override → ARID_DRY → 1.
    assert _score(exposure="ARID_DRY", shelter=None) == 1


def test_both_categorical_inputs_missing_defaults_to_3():
    # exposure None → TEMPERATE; shelter None → NORMAL; sweating None → 3.
    assert _score() == 3


# ====================================== Score 0 escape hatch ======================================


def test_sweating_false_escapes_to_0():
    # No sweating mechanism → no CUI → score 0 regardless of cascade.
    assert _score(exposure="TEMPERATE", shelter="NORMAL", sweating_asset=False) == 0


def test_sweating_false_escapes_above_damaged_shelter():
    # sweating_asset False wins even when DAMAGED shelter would force score 5.
    assert _score(exposure="MARINE", shelter="DAMAGED", sweating_asset=False) == 0


def test_sweating_true_does_not_trigger_escape():
    assert _score(exposure="TEMPERATE", shelter="NORMAL", sweating_asset=True) == 3


def test_missing_sweating_does_not_trigger_escape():
    # sweating_asset None is conservative-True → cascade continues.
    assert _score(exposure="MARINE", shelter="NORMAL", sweating_asset=None) == 5


# ====================================== Damaged shelter override ======================================


@pytest.mark.parametrize("exposure", ["MARINE", "SEVERE", "TEMPERATE", "ARID_DRY"])
def test_damaged_shelter_forces_score_5_regardless_of_exposure(exposure):
    # DAMAGED shelter introduces a local water source — overrides every
    # exposure-zone classification (assuming the asset can sweat).
    assert _score(exposure=exposure, shelter="DAMAGED", sweating_asset=True) == 5


# ====================================== Exposure-zone cascade ======================================


@pytest.mark.parametrize(
    "exposure, expected_score",
    [
        ("MARINE", 5),
        ("SEVERE", 5),
        ("ARID_DRY", 1),
        ("TEMPERATE", 3),
    ],
)
def test_exposure_zone_cascade_with_normal_shelter(exposure, expected_score):
    # NORMAL shelter + sweating asset — only exposure drives the score.
    assert _score(exposure=exposure, shelter="NORMAL", sweating_asset=True) == expected_score


@pytest.mark.parametrize("shelter", ["PROTECTED", "NORMAL"])
def test_protected_and_normal_shelters_score_the_same(shelter):
    # Only DAMAGED shelter has dedicated logic; PROTECTED and NORMAL
    # behave identically (both fall through to exposure-zone cascade).
    assert _score(exposure="TEMPERATE", shelter=shelter, sweating_asset=True) == 3
