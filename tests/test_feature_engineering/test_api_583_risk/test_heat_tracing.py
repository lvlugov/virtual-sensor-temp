"""Tests for the API 583 heat-tracing scorer.

Covers validation (unknown / case-sensitive enum), the ``None`` →
``"NONE"`` default, and the full score table across all six allowed
tracing-system values.
"""

import pytest

from lean_virtual_sensor.feature_engineering.api_583_risk.input_features.heat_tracing import (
    score_heat_tracing,
)


# ====================================== Validation ======================================


def test_unknown_tracing_system_raises():
    with pytest.raises(ValueError, match="Bad tracing_system"):
        score_heat_tracing("ELECTRIC")


def test_lowercase_tracing_system_rejected():
    # Tracing codes are upper-case enums; lower-case must not be silently
    # normalised.
    with pytest.raises(ValueError):
        score_heat_tracing("none")


# ====================================== Score table ======================================


@pytest.mark.parametrize(
    "tracing_system, expected_score",
    [
        ("NONE", 0),
        ("HIGH_INTEGRITY_STEAM_TRACED", 1),
        ("MEDIUM_INTEGRITY_STEAM_TRACED", 3),
        ("POOR_INTEGRITY_STEAM_TRACED", 5),
        ("ELECTRIC_TRACED", 1),
        ("HOT_OIL_TRACED", 1),
    ],
)
def test_score_table(tracing_system, expected_score):
    assert score_heat_tracing(tracing_system) == expected_score


# ====================================== Missing-data default ======================================


def test_tracing_system_none_treated_as_no_tracing():
    # tracing_system None → "NONE" → score 0.
    assert score_heat_tracing(None) == 0


# ====================================== Behavioural invariants ======================================


def test_integrity_tiers_are_strictly_increasing():
    # The whole point of the integrity split is that a deteriorating steam
    # loop scores monotonically higher; lock that property in.
    high = score_heat_tracing("HIGH_INTEGRITY_STEAM_TRACED")
    medium = score_heat_tracing("MEDIUM_INTEGRITY_STEAM_TRACED")
    poor = score_heat_tracing("POOR_INTEGRITY_STEAM_TRACED")
    assert high < medium < poor


def test_non_leak_mode_tracing_scores_equal_to_high_integrity_steam():
    # Electric and hot-oil tracing don't present the leak-mode CUI
    # mechanism, so they sit at the same score as best-case steam.
    assert (
        score_heat_tracing("ELECTRIC_TRACED")
        == score_heat_tracing("HOT_OIL_TRACED")
        == score_heat_tracing("HIGH_INTEGRITY_STEAM_TRACED")
    )
