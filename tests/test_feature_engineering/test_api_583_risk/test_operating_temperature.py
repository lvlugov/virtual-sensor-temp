"""Tests for the API 583 operating-temperature scorer.

Covers validation, the carbon-steel cyclic-service override (Table A.1
gating), and bucket boundaries for both Table A.1 (carbon/low-alloy
steel) and Table A.8 (austenitic/duplex stainless).
"""

import pytest

from lean_virtual_sensor.feature_engineering.api_583_risk.input_features.operating_temperature import (
    score_operating_temperature,
)


def _score(metallurgy, operating_temperature, *, t_min=None, t_max=None, cycles=0):
    """Compact wrapper — defaults the envelope to ``operating_temperature``
    and ``avg_cycles_per_quarter`` to 0 so callers can opt in to cyclic
    inputs only when they're relevant to the test."""
    return score_operating_temperature(
        metallurgy_family=metallurgy,
        operating_temperature=operating_temperature,
        min_operating_temperature=operating_temperature if t_min is None else t_min,
        max_operating_temperature=operating_temperature if t_max is None else t_max,
        avg_cycles_per_quarter=cycles,
    )


# ====================================== Validation ======================================


def test_unknown_metallurgy_raises():
    with pytest.raises(ValueError, match="Unknown metallurgy_family"):
        _score("TITANIUM", 100)


def test_operating_temperature_below_min_envelope_raises():
    with pytest.raises(ValueError, match="min_operating_temperature > operating_temperature"):
        score_operating_temperature("CARBON_STEEL", 80, 100, 200, 0)


def test_operating_temperature_above_max_envelope_raises():
    with pytest.raises(ValueError, match="max_operating_temperature < operating_temperature"):
        score_operating_temperature("CARBON_STEEL", 250, 0, 200, 0)


# ====================================== Carbon / low-alloy steel buckets ======================================


@pytest.mark.parametrize(
    "operating_temperature, expected_score",
    [
        (-5, 0),    # below envelope
        (-4, 1),    # low boundary (closed)
        (0, 1),
        (37, 1),
        (38, 3),    # transition low → moderate
        (76, 3),
        (77, 5),    # transition moderate → peak
        (90, 5),
        (110, 5),   # peak boundary (closed)
        (111, 3),   # transition peak → moderate
        (132, 3),
        (133, 1),   # transition moderate → low
        (177, 1),   # high envelope (closed)
        (178, 0),   # above envelope
    ],
)
def test_carbon_steel_bucket_thresholds(operating_temperature, expected_score):
    assert _score("CARBON_STEEL", operating_temperature) == expected_score


def test_low_alloy_steel_uses_same_table_as_carbon_steel():
    assert _score("LOW_ALLOY_STEEL", 90) == _score("CARBON_STEEL", 90) == 5


# ====================================== Carbon / low-alloy steel cyclic override ======================================


def test_cyclic_service_overrides_bucket_score():
    # T_op = 0 would land in the LOW bucket (1), but the cyclic
    # conditions all hold (max > 177, min < 110, cycles > 0) → score 5.
    assert score_operating_temperature("CARBON_STEEL", 0, 0, 200, 4) == 5


def test_cyclic_requires_active_cycling():
    # Cycles = 0 disables the override; falls back to bucket (T_op = 0 → 1).
    assert score_operating_temperature("CARBON_STEEL", 0, 0, 200, 0) == 1


def test_cyclic_requires_max_above_177_strict():
    # max == 177 fails the strict `> 177` clause; falls back to bucket.
    # T_op = 0 → low bucket (1).
    assert score_operating_temperature("CARBON_STEEL", 0, 0, 177, 4) == 1


def test_cyclic_requires_min_below_110_strict():
    # min == 110 fails the strict `< 110` clause; falls back to bucket.
    # T_op = 115 → moderate bucket (3).
    assert score_operating_temperature("CARBON_STEEL", 115, 110, 200, 4) == 3


# ====================================== Stainless steel buckets ======================================


@pytest.mark.parametrize(
    "operating_temperature, expected_score",
    [
        (48, 0),    # below envelope
        (49, 1),    # low boundary (closed)
        (59, 1),
        (60, 5),    # transition low → peak
        (121, 5),   # peak boundary (closed)
        (122, 3),   # transition peak → elevated
        (204, 3),   # elevated boundary (closed)
        (205, 0),   # above envelope
    ],
)
def test_austenitic_stainless_bucket_thresholds(operating_temperature, expected_score):
    assert _score("AUSTENITIC_SS", operating_temperature) == expected_score


def test_duplex_stainless_uses_same_table_as_austenitic():
    assert _score("DUPLEX_SS", 90) == _score("AUSTENITIC_SS", 90) == 5


def test_stainless_steel_has_no_cyclic_override():
    # All carbon-steel cyclic conditions hold, but Table A.8 has no
    # cyclic clause — score by bucket only. T_op = 0 is below the SS
    # envelope (49 °C) → score 0, NOT the carbon-steel override (5).
    assert score_operating_temperature("AUSTENITIC_SS", 0, 0, 200, 4) == 0
