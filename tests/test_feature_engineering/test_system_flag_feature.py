"""Tests for lean_virtual_sensor.feature_engineering.system_flag_feature."""

import pytest
from lean_virtual_sensor.feature_engineering.system_flag_feature import is_open_system


def test_is_open_system_both_above_average_is_closed():
    assert is_open_system("ABOVE_AVERAGE", "ABOVE_AVERAGE") is False


def test_is_open_system_case_insensitive():
    assert is_open_system("above_average", "Above_Average") is False


def test_is_open_system_average_insulation_is_open():
    assert is_open_system("AVERAGE", "ABOVE_AVERAGE") is True


def test_is_open_system_below_average_cladding_is_open():
    assert is_open_system("ABOVE_AVERAGE", "BELOW_AVERAGE") is True


def test_is_open_system_rejects_unknown_insulation_condition():
    with pytest.raises(ValueError):
        is_open_system("EXCELLENT", "ABOVE_AVERAGE")


def test_is_open_system_rejects_unknown_cladding_integrity():
    with pytest.raises(ValueError):
        is_open_system("ABOVE_AVERAGE", "BROKEN")
