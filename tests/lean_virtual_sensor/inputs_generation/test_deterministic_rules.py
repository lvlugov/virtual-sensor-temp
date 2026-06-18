"""Unit tests for Tier 1 deterministic rules (R-CHLORIDE-01) via generation_helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
from generation_helpers import apply_deterministic_field_value
from schema_loader import load_all_configs


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise RuntimeError("Could not locate repository root (pyproject.toml)")


CONFIG_DIR = _repo_root() / "lean_virtual_sensor" / "inputs_generation" / "config"


@pytest.fixture(scope="module")
def config():
    return load_all_configs(CONFIG_DIR)


def test_r_chloride_01_matches_marine_casi_old_insulation(config) -> None:
    value = apply_deterministic_field_value(
        config,
        "insulation_chloride_flag",
        {
            "exposure_zone": "MARINE",
            "insulation_material": "CALCIUM_SILICATE",
            "insulation_age_years": 6.0,
        },
        default=False,
    )
    assert value is True


def test_r_chloride_01_default_false_when_conditions_not_met(config) -> None:
    value = apply_deterministic_field_value(
        config,
        "insulation_chloride_flag",
        {
            "exposure_zone": "TEMPERATE",
            "insulation_material": "CALCIUM_SILICATE",
            "insulation_age_years": 10.0,
        },
        default=False,
    )
    assert value is False


def test_r_chloride_01_fails_closed_on_young_insulation(config) -> None:
    value = apply_deterministic_field_value(
        config,
        "insulation_chloride_flag",
        {
            "exposure_zone": "MARINE",
            "insulation_material": "CALCIUM_SILICATE",
            "insulation_age_years": 5.0,
        },
        default=False,
    )
    assert value is False


def test_unknown_field_returns_default(config) -> None:
    assert (
        apply_deterministic_field_value(
            config,
            "nonexistent_field",
            {},
            default=False,
        )
        is False
    )
