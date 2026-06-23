"""Tests for the API 583 line/nozzle-size scorer.

Covers validation, the equipment-class short-circuit to 0, the pipe
diameter bucket boundaries at the ASME B36.10 2-in. and 6-in. NPS
thresholds, and the asset-class equivalence within the equipment group.
"""

import pytest

from lean_virtual_sensor.feature_engineering.api_583_risk.input_features.line_size import (
    score_line_size,
)


# ====================================== Validation ======================================


def test_missing_asset_class_raises():
    with pytest.raises(ValueError, match="asset_class is required"):
        score_line_size(None, component_diameter=100.0)


def test_unknown_asset_class_raises():
    with pytest.raises(ValueError, match="Bad asset_class"):
        score_line_size("UNKNOWN_CLASS", component_diameter=100.0)


def test_lowercase_asset_class_rejected():
    with pytest.raises(ValueError):
        score_line_size("pipe", component_diameter=100.0)


def test_zero_diameter_rejected():
    with pytest.raises(ValueError, match="component_diameter must be > 0"):
        score_line_size("PIPE", component_diameter=0.0)


def test_negative_diameter_rejected():
    with pytest.raises(ValueError, match="component_diameter must be > 0"):
        score_line_size("PIPE", component_diameter=-10.0)


def test_pipe_without_diameter_raises():
    with pytest.raises(ValueError, match="component_diameter is required"):
        score_line_size("PIPE", component_diameter=None)


# ====================================== Equipment short-circuit ======================================


@pytest.mark.parametrize(
    "asset_class",
    ["PRESSURE_VESSEL", "HEAT_EXCHANGER", "AIR_COOLER", "STORAGE_TANK", "COLUMN", "REACTOR"],
)
def test_equipment_classes_score_0(asset_class):
    # Every equipment class returns 0 regardless of diameter.
    assert score_line_size(asset_class, component_diameter=100.0) == 0


def test_equipment_class_ignores_diameter():
    # diameter None is allowed for equipment classes (it's never read).
    assert score_line_size("PRESSURE_VESSEL", component_diameter=None) == 0


def test_equipment_class_ignores_extreme_diameter():
    # Any positive diameter is fine for equipment; only the class drives the score.
    assert score_line_size("STORAGE_TANK", component_diameter=10000.0) == 0


# ====================================== Pipe diameter buckets ======================================


@pytest.mark.parametrize(
    "component_diameter, expected_score",
    [
        # > 6 in. NPS (OD > 168.3 mm) → 1
        (300.0, 1),
        (200.0, 1),
        (168.4, 1),   # just above the 6-in. boundary
        # > 2 in. to 6 in. NPS (60.3 < OD ≤ 168.3 mm) → 3
        (168.3, 3),   # closed 6-in. boundary
        (150.0, 3),
        (100.0, 3),
        (60.4, 3),    # just above the 2-in. boundary
        # ≤ 2 in. NPS (OD ≤ 60.3 mm) → 5
        (60.3, 5),    # closed 2-in. boundary
        (50.0, 5),
        (20.0, 5),
        (0.1, 5),     # arbitrarily small but positive
    ],
)
def test_pipe_diameter_buckets(component_diameter, expected_score):
    assert score_line_size("PIPE", component_diameter) == expected_score
