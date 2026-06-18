"""Unit tests for per-profile operating temperature field sampling."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from generation_helpers import sample_operating_temperature_fields
from schema_loader import load_all_configs


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise RuntimeError("Could not locate repository root")


CONFIG_DIR = _repo_root() / "lean_virtual_sensor" / "inputs_generation" / "config"


@pytest.fixture
def cfg():
    return load_all_configs(CONFIG_DIR)


def _sample_many(
    profile_key: str,
    ot_config: dict,
    *,
    n: int = 10_000,
    seed: int = 42,
) -> list[dict[str, float | int]]:
    rng = np.random.default_rng(seed)
    return [sample_operating_temperature_fields(profile_key, ot_config, rng) for _ in range(n)]


def test_pipe_operating_temperature_clusters_near_mode(cfg) -> None:
    """Triangular draw peaks at mode; mean is (min+mode+max)/3, not the mode itself."""
    samples = _sample_many("PIPE", cfg.operating_temperature)
    ops = [float(row["operating_temperature"]) for row in samples]
    mode = 100.0
    midpoint = 170.0

    median_op = float(np.median(ops))
    assert median_op < midpoint

    near_peak = sum(1 for op in ops if mode - 30 <= op <= mode + 30)
    high_tail = sum(1 for op in ops if op >= 220)
    assert near_peak > high_tail


def test_max_operating_temperature_not_below_operating(cfg) -> None:
    for profile_key in cfg.operating_temperature["profiles"]:
        samples = _sample_many(profile_key, cfg.operating_temperature, n=500, seed=7)
        for row in samples:
            assert row["min_operating_temperature"] <= row["operating_temperature"]
            assert row["operating_temperature"] <= row["max_operating_temperature"]


def test_hot_profile_max_excursion_near_ten_percent(cfg) -> None:
    samples = _sample_many("PIPE", cfg.operating_temperature)
    ratios = [
        (row["max_operating_temperature"] - row["operating_temperature"])
        / row["operating_temperature"]
        for row in samples
        if row["operating_temperature"] > 0
    ]
    median_ratio = float(np.median(ratios))
    assert 0.07 <= median_ratio <= 0.13


def test_cold_service_min_below_operating(cfg) -> None:
    samples = _sample_many("PIPE_COLD_SERVICE", cfg.operating_temperature)
    below_threshold = [
        row
        for row in samples
        if row["min_operating_temperature"] <= row["operating_temperature"] - 5.0
    ]
    assert len(below_threshold) / len(samples) >= 0.95


def test_cold_service_max_warmup_above_operating(cfg) -> None:
    samples = _sample_many("PIPE_COLD_SERVICE", cfg.operating_temperature, n=1000)
    assert all(row["max_operating_temperature"] > row["operating_temperature"] for row in samples)
    assert all(row["max_operating_temperature"] >= 10.0 for row in samples)


def test_wide_swing_max_uses_ten_percent_rule(cfg) -> None:
    samples = _sample_many("WIDE_SWING", cfg.operating_temperature, n=1000)
    for row in samples:
        op = float(row["operating_temperature"])
        t_max = float(row["max_operating_temperature"])
        assert 245.0 <= t_max <= 255.0
        assert t_max >= op
        expected = min(op * 1.10, 255.0)
        assert abs(t_max - expected) < 0.15 or t_max == 255.0


def test_avg_cycles_per_quarter_is_integer(cfg) -> None:
    for profile_key in cfg.operating_temperature["profiles"]:
        row = sample_operating_temperature_fields(
            profile_key,
            cfg.operating_temperature,
            np.random.default_rng(0),
        )
        assert isinstance(row["avg_cycles_per_quarter"], (int, np.integer))


def test_operation_vs_shutdown_fraction_within_profile_bounds(cfg) -> None:
    profiles = cfg.operating_temperature["profiles"]
    for profile_key, profile in profiles.items():
        fraction_block = profile["operation_vs_shutdown_fraction"]
        lo = float(fraction_block["min"])
        hi = float(fraction_block["max"])
        samples = _sample_many(profile_key, cfg.operating_temperature, n=200, seed=11)
        for row in samples:
            fraction = float(row["operation_vs_shutdown_fraction"])
            assert lo <= fraction <= hi


def test_unknown_profile_raises(cfg) -> None:
    with pytest.raises(ValueError, match="Unknown operating temperature profile"):
        sample_operating_temperature_fields(
            "NOT_A_PROFILE",
            cfg.operating_temperature,
            np.random.default_rng(0),
        )
