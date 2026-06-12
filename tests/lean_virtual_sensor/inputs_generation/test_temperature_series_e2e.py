"""End-to-end tests for the temperature-series chain.

Runs the full pipeline (compute_tau -> place_cycles -> size_cycles ->
cooldown_reference -> build_target_series -> apply_thermal_lag ->
add_running_noise -> clamp_series) exactly as the driver will, and asserts
system-level properties: determinism, bounds, and each profile's signature.

Per-function unit tests live in ``test_temperature_series.py``.
"""

from __future__ import annotations

import numpy as np
import pytest

from temperature_series import (
    add_running_noise,
    apply_thermal_lag,
    build_target_series,
    clamp_series,
    compute_tau,
    cooldown_reference,
    place_cycles,
    size_cycles,
)

# Constants as the driver would read them from the temperature_series config block.
WINDOW = 2160  # 90 days x 24 h
MIN_DUR = 2
AMP = 2.0
GLOBAL_MIN, GLOBAL_MAX = -100.0, 500.0
CS = dict(metal_density_kg_per_m3=7850.0, metal_specific_heat_j_per_kg_k=490.0)


def _synthetic_ambient(n=WINDOW):
    """A clean daily sinusoid, 12..28 C."""
    return 20 + 8 * np.sin(2 * np.pi * np.arange(n) / 24)


def _run_chain(*, op, mn, mx, n_cycles, fraction, do, wall, ins, k, seed):
    """The whole pipeline, exactly as the driver will call it for one asset."""
    rng = np.random.default_rng(seed)
    ambient = _synthetic_ambient()
    tau = compute_tau(do, wall, ins, k, **CS)
    starts = place_cycles(n_cycles, WINDOW)
    durations = size_cycles(n_cycles, fraction, WINDOW, MIN_DUR)
    ref = cooldown_reference(op, mn)
    target = build_target_series(op, mn, starts, durations, ref, ambient)
    temp = apply_thermal_lag(target, tau)
    temp = add_running_noise(temp, target, op, rng, AMP)
    return clamp_series(temp, mn, mx, GLOBAL_MIN, GLOBAL_MAX)


# Representative assets, values per the current per-class table (see
# docs/temperature_series_explained.md §5.1).
PIPE = dict(op=90, mn=10, mx=115, n_cycles=12, fraction=0.93, do=114, wall=6, ins=50, k=0.040)
REACTOR = dict(op=250, mn=10, mx=385, n_cycles=40, fraction=0.55, do=1800, wall=25, ins=80, k=0.058)
COLD = dict(op=-40, mn=-55, mx=10, n_cycles=12, fraction=0.92, do=114, wall=6, ins=50, k=0.040)
WIDE = dict(op=250, mn=-10, mx=250, n_cycles=12, fraction=0.60, do=800, wall=20, ins=80, k=0.058)


@pytest.mark.parametrize("prof", [PIPE, REACTOR, COLD, WIDE])
def test_e2e_length_and_bounds(prof) -> None:
    s = _run_chain(seed=1, **prof)
    assert s.size == WINDOW
    assert s.min() >= prof["mn"] - 1e-6 and s.max() <= prof["mx"] + 1e-6
    assert s.min() >= GLOBAL_MIN and s.max() <= GLOBAL_MAX


def test_e2e_deterministic_under_same_seed() -> None:
    assert np.array_equal(_run_chain(seed=7, **PIPE), _run_chain(seed=7, **PIPE))


def test_e2e_different_seed_changes_output() -> None:
    assert not np.array_equal(_run_chain(seed=1, **PIPE), _run_chain(seed=2, **PIPE))


def test_e2e_pipe_sits_in_corrosion_zone() -> None:
    s = _run_chain(seed=1, **PIPE)
    assert s.max() <= PIPE["op"] + 3            # lives at op (plus running noise)
    assert ((s >= -4) & (s <= 175)).mean() > 0.95  # essentially always active


def test_e2e_reactor_never_fully_cools() -> None:
    """Large tau -> partial dips; it never gets near ambient (~12-28) or its own min."""
    s = _run_chain(seed=1, **REACTOR)
    assert s.min() > 40                  # stays well clear of ambient — never fully cold
    assert s.min() > REACTOR["mn"] + 25  # nowhere near its cooldown floor


def test_e2e_cold_service_crosses_zero_and_caps_at_max() -> None:
    s = _run_chain(seed=1, **COLD)
    assert s.min() < 0 < s.max()         # runs cold, warms across 0 on shutdown
    assert s.max() <= COLD["mx"] + 1e-6  # capped at the asset max


def test_e2e_wide_swing_spans_envelope() -> None:
    s = _run_chain(seed=1, **WIDE)
    assert (s.max() - s.min()) > 150     # driven across a huge range
    assert s.max() >= WIDE["op"] - 3      # runs at the top
