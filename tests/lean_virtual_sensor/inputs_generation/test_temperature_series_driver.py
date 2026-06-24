"""Tests for the temperature-series driver (per-asset core + population runner)."""

from __future__ import annotations

import copy
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml
from lean_virtual_sensor.inputs_generation.temperature_series_driver import generate_asset_series


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise RuntimeError("Could not locate repository root (pyproject.toml)")


CONFIG = yaml.safe_load(
    (
        _repo_root() / "lean_virtual_sensor/inputs_generation/config/generation_config.yaml"
    ).read_text()
)["temperature_series"]
WINDOW = CONFIG["window_days"] * 24


def _ambient(n=WINDOW):
    idx = pd.date_range("2026-02-12", periods=n, freq="h")
    return pd.DataFrame({"datetime": idx, "temp": 20 + 8 * np.sin(2 * np.pi * np.arange(n) / 24)})


# A PIPE's fields, passed explicitly (not bundled).
PIPE_KW = dict(
    operating_temperature=90.0,
    min_operating_temperature=10.0,
    max_operating_temperature=115.0,
    avg_cycles_per_quarter=12,
    operation_vs_shutdown_fraction=0.93,
    outer_diameter_mm=114.0,
    wall_thickness_mm=6.0,
    insulation_thickness_mm=50.0,
    insulation_material="MINERAL_WOOL",
    metallurgy_family="CARBON_STEEL",
)


# =================================== core: generate_asset_series ==================================


def test_core_returns_expected_shape_and_columns() -> None:
    df = generate_asset_series(
        **PIPE_KW, ambient=_ambient(), config=CONFIG, rng=np.random.default_rng(0)
    )
    assert list(df.columns) == ["datetime", "process_temperature_c"]
    assert len(df) == WINDOW


def test_core_carries_ambient_timestamps_through() -> None:
    amb = _ambient()
    df = generate_asset_series(**PIPE_KW, ambient=amb, config=CONFIG, rng=np.random.default_rng(0))
    assert np.array_equal(df["datetime"].to_numpy(), amb["datetime"].to_numpy())


def test_core_output_is_bounded() -> None:
    df = generate_asset_series(
        **PIPE_KW, ambient=_ambient(), config=CONFIG, rng=np.random.default_rng(0)
    )
    t = df["process_temperature_c"]
    assert t.min() >= PIPE_KW["min_operating_temperature"] - 1e-6
    assert t.max() <= PIPE_KW["max_operating_temperature"] + 1e-6


def test_core_uses_last_window_when_ambient_is_longer() -> None:
    amb = _ambient(WINDOW + 500)
    df = generate_asset_series(**PIPE_KW, ambient=amb, config=CONFIG, rng=np.random.default_rng(0))
    assert len(df) == WINDOW
    assert df["datetime"].iloc[0] == amb["datetime"].iloc[-WINDOW]


def test_core_is_deterministic_under_same_seed() -> None:
    a = generate_asset_series(
        **PIPE_KW, ambient=_ambient(), config=CONFIG, rng=np.random.default_rng(5)
    )
    b = generate_asset_series(
        **PIPE_KW, ambient=_ambient(), config=CONFIG, rng=np.random.default_rng(5)
    )
    assert np.array_equal(a["process_temperature_c"], b["process_temperature_c"])


def test_core_asymmetric_recovery_is_faster_never_slower() -> None:
    """recovery_tau_factor < 1 speeds up the recovery legs (return to op) and
    leaves the cooldown legs unchanged, so the series is never *below* the
    symmetric one and is strictly above it on at least some recovery hours."""
    cfg_sym = copy.deepcopy(CONFIG)
    cfg_sym["recovery_tau_factor"] = 1.0  # symmetric baseline
    fast = generate_asset_series(
        **PIPE_KW, ambient=_ambient(), config=CONFIG, rng=np.random.default_rng(0)
    )
    sym = generate_asset_series(
        **PIPE_KW, ambient=_ambient(), config=cfg_sym, rng=np.random.default_rng(0)
    )
    fast_t = fast["process_temperature_c"].to_numpy()
    sym_t = sym["process_temperature_c"].to_numpy()
    assert np.all(fast_t >= sym_t - 1e-9)  # never recovers slower
    assert np.any(fast_t > sym_t + 1e-6)  # and faster on the recovery legs


@pytest.mark.parametrize(
    "override, match",
    [
        (dict(insulation_material="ASBESTOS"), "insulation_material"),
        (dict(metallurgy_family="NICKEL_ALLOY"), "out of scope"),
    ],
)
def test_core_raises_on_unknown_lookups(override, match) -> None:
    kw = {**PIPE_KW, **override}
    with pytest.raises(ValueError, match=match):
        generate_asset_series(**kw, ambient=_ambient(), config=CONFIG, rng=np.random.default_rng(0))


def test_core_raises_on_short_ambient() -> None:
    with pytest.raises(ValueError):
        generate_asset_series(
            **PIPE_KW, ambient=_ambient(WINDOW - 1), config=CONFIG, rng=np.random.default_rng(0)
        )


def test_core_raises_on_missing_ambient_column() -> None:
    bad = _ambient().rename(columns={"temp": "temperature"})
    with pytest.raises(ValueError):
        generate_asset_series(**PIPE_KW, ambient=bad, config=CONFIG, rng=np.random.default_rng(0))
