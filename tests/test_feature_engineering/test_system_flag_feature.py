"""Tests for lean_virtual_sensor.feature_engineering.system_flag_feature."""

import pytest
from lean_virtual_sensor.feature_engineering.system_flag_feature import is_open_system


def test_is_open_system_both_good_is_closed():
    assert is_open_system("GOOD", "GOOD") is False


def test_is_open_system_case_insensitive():
    assert is_open_system("good", "Good") is False


def test_is_open_system_average_insulation_is_open():
    assert is_open_system("AVERAGE", "GOOD") is True


def test_is_open_system_poor_cladding_is_open():
    assert is_open_system("GOOD", "POOR") is True


def test_is_open_system_rejects_unknown_insulation_condition():
    with pytest.raises(ValueError):
        is_open_system("EXCELLENT", "GOOD")


def test_is_open_system_rejects_unknown_cladding_integrity():
    with pytest.raises(ValueError):
        is_open_system("GOOD", "BROKEN")
