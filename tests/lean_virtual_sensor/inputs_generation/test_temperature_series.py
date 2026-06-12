"""Unit tests for inputs_generation.temperature_series.

Pure tests — the time-series functions take plain arguments (no generated CSV),
so nothing here depends on the ``--dataset`` fixture. Built up one function at a
time, mirroring the build order of the module.
"""

from __future__ import annotations

import math

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

GLOBAL_MIN, GLOBAL_MAX = -100.0, 500.0

# Carbon-steel constants, as the driver would pass them from config.
CS = dict(metal_density_kg_per_m3=7850.0, metal_specific_heat_j_per_kg_k=490.0)


# ====================================== Step 1: compute_tau ======================================


def test_compute_tau_reference_pipe() -> None:
    """4.5-inch pipe, 6 mm wall, 50 mm mineral wool (k=0.040) -> ~5.5 h (methodology §5)."""
    assert math.isclose(compute_tau(114, 6, 50, 0.040, **CS), 5.45, abs_tol=0.1)


def test_compute_tau_increases_with_wall_thickness() -> None:
    """More steel mass -> slower cooldown."""
    assert compute_tau(114, 12, 50, 0.040, **CS) > compute_tau(114, 6, 50, 0.040, **CS)


def test_compute_tau_increases_with_insulation() -> None:
    """More insulation resistance -> slower cooldown."""
    assert compute_tau(114, 6, 100, 0.040, **CS) > compute_tau(114, 6, 50, 0.040, **CS)


def test_compute_tau_decreases_with_conductivity() -> None:
    """Higher k (less insulating) -> faster cooldown."""
    assert compute_tau(114, 6, 50, 0.065, **CS) < compute_tau(114, 6, 50, 0.040, **CS)


def test_compute_tau_second_reference_value() -> None:
    """2 m vessel, 20 mm wall, 80 mm CaSi (k=0.058) -> ~28.1 h (hand-computed)."""
    assert math.isclose(compute_tau(2000, 20, 80, 0.058, **CS), 28.07, abs_tol=0.2)


def test_compute_tau_increases_with_metal_heat_capacity() -> None:
    """Higher rho*c (austenitic SS 8000/500) stores more heat -> larger tau than CS."""
    austenitic = compute_tau(
        114, 6, 50, 0.040,
        metal_density_kg_per_m3=8000.0, metal_specific_heat_j_per_kg_k=500.0,
    )
    assert austenitic > compute_tau(114, 6, 50, 0.040, **CS)


@pytest.mark.parametrize(
    "do, wall, ins, k, why",
    [
        (25, 13, 50, 0.040, "wall >= Do/2 (no bore)"),
        (114, 0, 50, 0.040, "wall <= 0"),
        (-1, 6, 50, 0.040, "Do <= 0"),
        (114, 6, 0, 0.040, "insulation <= 0"),
        (114, 6, 50, 0.0, "conductivity <= 0"),
    ],
)
def test_compute_tau_raises_on_bad_input(do, wall, ins, k, why) -> None:
    with pytest.raises(ValueError):
        compute_tau(do, wall, ins, k, **CS)


# ====================================== Step 3: place_cycles ======================================

WINDOW = 2160  # 90 days x 24 h


@pytest.mark.parametrize("n", [1, 4, 12, 40, 200])
def test_place_cycles_count_and_bounds(n) -> None:
    s = place_cycles(n, WINDOW)
    assert len(s) == n
    assert s.min() >= 0 and s.max() <= WINDOW - 1


@pytest.mark.parametrize("n", [4, 12, 40])
def test_place_cycles_uniform_spacing(n) -> None:
    """Gaps between consecutive starts are all equal (to within rounding)."""
    gaps = np.diff(place_cycles(n, WINDOW))
    assert np.ptp(gaps) <= 1  # at most 1 h rounding spread
    assert math.isclose(gaps.mean(), WINDOW / n, abs_tol=1.0)


@pytest.mark.parametrize("n", [4, 12, 40])
def test_place_cycles_centred_margins(n) -> None:
    """Centred placement leaves ~half a spacing of running time at each end."""
    s = place_cycles(n, WINDOW)
    half = WINDOW / n / 2
    assert math.isclose(s[0], half, abs_tol=1.0)
    assert math.isclose(WINDOW - s[-1], half, abs_tol=1.0)


def test_place_cycles_single_is_centred() -> None:
    assert place_cycles(1, WINDOW)[0] == WINDOW // 2


def test_place_cycles_zero_is_empty() -> None:
    assert place_cycles(0, WINDOW).size == 0


def test_place_cycles_sorted_ascending() -> None:
    s = place_cycles(40, WINDOW)
    assert np.all(np.diff(s) > 0)


@pytest.mark.parametrize("n, w", [(-1, WINDOW), (4, 0)])
def test_place_cycles_raises_on_bad_input(n, w) -> None:
    with pytest.raises(ValueError):
        place_cycles(n, w)


# ====================================== Step 4: size_cycles ======================================

MIN_DUR = 2


@pytest.mark.parametrize(
    "n, f, expected",
    [(12, 0.93, 13), (20, 0.90, 11), (2, 0.97, 32), (40, 0.55, 24), (12, 0.60, 72)],
)
def test_size_cycles_uniform_value(n, f, expected) -> None:
    """duration = round((1-f) * window / n), identical for every cycle."""
    d = size_cycles(n, f, WINDOW, MIN_DUR)
    assert len(d) == n
    assert np.all(d == d[0])
    assert d[0] == expected


@pytest.mark.parametrize("n, f", [(12, 0.93), (40, 0.55), (2, 0.97)])
def test_size_cycles_fits_slot(n, f) -> None:
    """(1-f)*spacing < spacing, so a cycle never overruns the next."""
    assert size_cycles(n, f, WINDOW, MIN_DUR)[0] < WINDOW / n


@pytest.mark.parametrize("n, f", [(12, 0.93), (8, 0.93), (40, 0.55), (12, 0.60)])
def test_size_cycles_total_off_matches_budget(n, f) -> None:
    """The core property: sum of durations ~= (1-f)*window (within integer rounding)."""
    total = int(size_cycles(n, f, WINDOW, MIN_DUR).sum())
    assert abs(total - (1 - f) * WINDOW) <= n  # at most ~1 h/cycle rounding


def test_size_cycles_floor_applies() -> None:
    """f=1 (never off) would round to 0 -> floored to the minimum."""
    assert size_cycles(5, 1.0, WINDOW, MIN_DUR)[0] == MIN_DUR


def test_size_cycles_zero_is_empty() -> None:
    assert size_cycles(0, 0.9, WINDOW, MIN_DUR).size == 0


@pytest.mark.parametrize(
    "n, f, w, m",
    [(-1, 0.9, WINDOW, 2), (5, 1.5, WINDOW, 2), (5, 0.9, 0, 2), (5, 0.9, WINDOW, 0)],
)
def test_size_cycles_raises_on_bad_input(n, f, w, m) -> None:
    with pytest.raises(ValueError):
        size_cycles(n, f, w, m)


# ====================================== Step 5: cooldown_reference ======================================


@pytest.mark.parametrize(
    "op, mn, expected",
    [
        (90, 15, "ambient"),     # ordinary hot
        (320, 15, "ambient"),    # reactor — still ordinary hot (no special case)
        (-40, -50, "ambient"),   # cold-service: slides up toward ambient
        (-50, -55, "ambient"),   # refrigerated tank
        (250, -10, "min"),       # wide-swing: hot op, driven sub-ambient
        (0, -5, "ambient"),      # op not > 0 -> not wide-swing
    ],
)
def test_cooldown_reference(op, mn, expected) -> None:
    assert cooldown_reference(op, mn) == expected


# ====================================== Step 6: build_target_series ======================================


def _two_cycle_setup():
    """20-hour window, ambient = 10..29, cycles at [4,14] lasting [3,2] h."""
    ambient = np.arange(10, 30, dtype=float)
    starts = np.array([4, 14])
    durations = np.array([3, 2])
    return ambient, starts, durations


def test_build_target_no_cycles_is_baseline() -> None:
    ambient, _, _ = _two_cycle_setup()
    t = build_target_series(90, 15, np.array([], int), np.array([], int), "ambient", ambient)
    assert t.shape == ambient.shape
    assert np.all(t == 90)


def test_build_target_ambient_windows_equal_ambient_slice() -> None:
    """Core: window hours take the ambient values; everything else stays at op."""
    ambient, starts, durations = _two_cycle_setup()
    t = build_target_series(90, 15, starts, durations, "ambient", ambient)
    assert np.array_equal(t[4:7], ambient[4:7])   # cycle 0 window
    assert np.array_equal(t[14:16], ambient[14:16])  # cycle 1 window
    running = np.ones(20, bool)
    running[4:7] = False
    running[14:16] = False
    assert np.all(t[running] == 90)


def test_build_target_min_windows_equal_min() -> None:
    ambient, starts, durations = _two_cycle_setup()
    t = build_target_series(250, -10, starts, durations, "min", ambient)
    assert np.all(t[4:7] == -10)
    assert np.all(t[14:16] == -10)
    running = np.ones(20, bool)
    running[4:7] = False
    running[14:16] = False
    assert np.all(t[running] == 250)


def test_build_target_length_matches_ambient() -> None:
    ambient = np.zeros(WINDOW)
    t = build_target_series(90, 15, np.array([0]), np.array([5]), "ambient", ambient)
    assert t.size == WINDOW


def test_build_target_clips_window_at_window_end() -> None:
    """A cycle running past the window end paints only up to the end (no error)."""
    ambient, _, _ = _two_cycle_setup()  # len 20
    t = build_target_series(90, 15, np.array([18]), np.array([10]), "ambient", ambient)
    assert np.array_equal(t[18:20], ambient[18:20])  # only hours 18,19 painted
    assert np.all(t[:18] == 90)


@pytest.mark.parametrize(
    "op, mn, starts, durs, ref, amb, why",
    [
        (90, 15, np.array([4]), np.array([3]), "bad", np.arange(10, 30.0), "bad ref_kind"),
        (90, 15, np.array([4, 14]), np.array([3]), "ambient", np.arange(10, 30.0), "len mismatch"),
        (90, 15, np.array([4]), np.array([3]), "ambient", np.array([]), "empty ambient"),
    ],
)
def test_build_target_raises_on_bad_input(op, mn, starts, durs, ref, amb, why) -> None:
    with pytest.raises(ValueError):
        build_target_series(op, mn, starts, durs, ref, amb)


# ====================================== Step 7: apply_thermal_lag (engine) ======================================

_OP, _AMB = 90.0, 20.0
_GAP = _OP - _AMB


def _step_down(tau_hold_hours=600, step_at=5):
    """A target that steps from op to ambient at hour `step_at` and stays there."""
    t = np.full(tau_hold_hours, _OP)
    t[step_at:] = _AMB
    return t


def test_apply_thermal_lag_seeds_at_first_target() -> None:
    assert apply_thermal_lag(np.array([90.0, 20, 20, 20]), 5.5)[0] == 90.0


def test_apply_thermal_lag_reaches_target_on_long_hold() -> None:
    """Held well past 3*tau -> settles at the target (genuinely cold)."""
    temp = apply_thermal_lag(_step_down(), 37.0)
    assert math.isclose(temp[-1], _AMB, abs_tol=0.5)


def test_apply_thermal_lag_63_95_curve() -> None:
    """Core: ~63% of the gap closed at t=tau, ~95% at t=3*tau (large tau, so rounding is negligible)."""
    tau = 50.0
    temp = apply_thermal_lag(_step_down(), tau)
    f_tau = (_OP - temp[5 + round(tau)]) / _GAP
    f_3tau = (_OP - temp[5 + round(3 * tau)]) / _GAP
    assert math.isclose(f_tau, 0.63, abs_tol=0.04)
    assert f_3tau >= 0.93


def test_apply_thermal_lag_monotone_and_jump_free() -> None:
    tau = 5.5
    temp = apply_thermal_lag(_step_down(tau_hold_hours=200), tau)
    assert np.all(np.diff(temp[5:60]) <= 1e-9)  # descent never goes back up
    first_step = _GAP * (1 - math.exp(-1 / tau))  # biggest possible hourly move
    assert np.abs(np.diff(temp)).max() <= first_step + 1e-6
    assert np.abs(np.diff(temp)).max() < _GAP     # never a vertical jump


def test_apply_thermal_lag_short_dip_stays_shallow() -> None:
    """A slow asset (large tau) dips deeper the longer it's off; a brief dip stays shallow."""
    tau = 37.0

    def depth(dur):
        t = np.full(200, _OP)
        t[5 : 5 + dur] = _AMB
        return (_OP - apply_thermal_lag(t, tau).min()) / _GAP

    assert depth(2) < depth(6) < depth(20)
    assert depth(2) < 0.15  # dip well under tau never gets far


def test_apply_thermal_lag_recovers_to_op() -> None:
    t = np.full(200, _OP)
    t[5:25] = _AMB
    assert math.isclose(apply_thermal_lag(t, 5.5)[-1], _OP, abs_tol=0.5)


def test_apply_thermal_lag_does_not_mutate_target() -> None:
    t = np.full(50, _OP)
    t[5:20] = _AMB
    before = t.copy()
    apply_thermal_lag(t, 5.5)
    assert np.array_equal(t, before)


@pytest.mark.parametrize("tau", [0.0, -1.0])
def test_apply_thermal_lag_raises_bad_tau(tau) -> None:
    with pytest.raises(ValueError):
        apply_thermal_lag(np.full(10, _OP), tau)


def test_apply_thermal_lag_raises_empty() -> None:
    with pytest.raises(ValueError):
        apply_thermal_lag(np.array([]), 5.5)


def test_apply_thermal_lag_per_hour_tau_recovers_faster() -> None:
    """A shorter tau on the recovery leg makes the climb back to op faster."""
    op, amb = 90.0, 20.0
    target = np.full(200, op)
    target[20:80] = amb  # long shutdown, then recovery
    tau_profile = np.where(target == op, 5.5 * 0.5, 5.5)  # recovery legs 2x faster
    fast = apply_thermal_lag(target, tau_profile)
    slow = apply_thermal_lag(target, 5.5)  # symmetric
    # identical cooldown (same tau on the dip), faster recovery
    assert np.allclose(fast[20:80], slow[20:80])
    rec_fast = int(np.argmax(fast[80:] >= op - 1))
    rec_slow = int(np.argmax(slow[80:] >= op - 1))
    assert rec_fast < rec_slow


def test_apply_thermal_lag_per_hour_tau_length_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        apply_thermal_lag(np.full(10, 90.0), np.full(9, 5.5))


def test_apply_thermal_lag_per_hour_tau_nonpositive_raises() -> None:
    with pytest.raises(ValueError):
        apply_thermal_lag(np.full(5, 90.0), np.array([5.5, 5.5, 0.0, 5.5, 5.5]))


# ====================================== Step 8: add_running_noise ======================================


def _noise_setup():
    """Running at op=90 everywhere except a dip window [10,20) where target != op."""
    op = 90.0
    target = np.full(500, op)
    target[10:20] = 20.0
    temp = target.copy()  # pretend the engine produced exactly the target, for clean checks
    return op, target, temp


def test_add_running_noise_only_touches_running_hours() -> None:
    """Core: dip/slide hours (target != op) are left exactly unchanged."""
    op, target, temp = _noise_setup()
    out = add_running_noise(temp, target, op, np.random.default_rng(0), 2.0)
    non_running = target != op
    assert np.array_equal(out[non_running], temp[non_running])


def test_add_running_noise_bounded_by_amplitude() -> None:
    op, target, temp = _noise_setup()
    amp = 2.0
    out = add_running_noise(temp, target, op, np.random.default_rng(1), amp)
    delta = out - temp
    running = target == op
    assert delta[running].min() >= -amp - 1e-9
    assert delta[running].max() <= amp + 1e-9


def test_add_running_noise_mean_near_zero() -> None:
    op, target, temp = _noise_setup()
    out = add_running_noise(temp, target, op, np.random.default_rng(2), 2.0)
    running = target == op
    assert abs((out - temp)[running].mean()) < 0.2  # uniform +/-2 over ~490 h


def test_add_running_noise_zero_amplitude_is_identity() -> None:
    op, target, temp = _noise_setup()
    out = add_running_noise(temp, target, op, np.random.default_rng(3), 0.0)
    assert np.array_equal(out, temp)


def test_add_running_noise_does_not_mutate_input() -> None:
    op, target, temp = _noise_setup()
    before = temp.copy()
    add_running_noise(temp, target, op, np.random.default_rng(4), 2.0)
    assert np.array_equal(temp, before)


def test_add_running_noise_raises_negative_amplitude() -> None:
    op, target, temp = _noise_setup()
    with pytest.raises(ValueError):
        add_running_noise(temp, target, op, np.random.default_rng(5), -1.0)


def test_add_running_noise_raises_length_mismatch() -> None:
    with pytest.raises(ValueError):
        add_running_noise(np.zeros(5), np.zeros(6), 90.0, np.random.default_rng(6), 2.0)


# ====================================== Step 9: clamp_series ======================================


def test_clamp_series_clips_to_asset_bounds() -> None:
    """Core: nothing falls below min or above max."""
    s = np.array([-5.0, 10, 50, 90, 130, 600])
    out = clamp_series(s, 15, 115, GLOBAL_MIN, GLOBAL_MAX)
    assert out.min() >= 15 and out.max() <= 115
    assert np.array_equal(out, np.array([15.0, 15, 50, 90, 115, 115]))


def test_clamp_series_cold_service_max_cap() -> None:
    """Cold-service warm-up toward ambient (28) is capped at the asset's max (10)."""
    s = np.array([-40.0, -20, 0, 15, 28])
    out = clamp_series(s, -50, 10, GLOBAL_MIN, GLOBAL_MAX)
    assert out.max() == 10
    assert np.array_equal(out, np.array([-40.0, -20, 0, 10, 10]))


def test_clamp_series_global_backstop() -> None:
    """Even with absurd asset bounds, values stay within the global range."""
    s = np.array([-300.0, 700.0])
    out = clamp_series(s, -500, 900, GLOBAL_MIN, GLOBAL_MAX)
    assert out.min() >= GLOBAL_MIN and out.max() <= GLOBAL_MAX
    assert np.array_equal(out, np.array([GLOBAL_MIN, GLOBAL_MAX]))


def test_clamp_series_does_not_mutate_input() -> None:
    s = np.array([200.0, -200.0])
    before = s.copy()
    clamp_series(s, 15, 115, GLOBAL_MIN, GLOBAL_MAX)
    assert np.array_equal(s, before)


@pytest.mark.parametrize(
    "mn, mx, gmin, gmax",
    [(115, 15, GLOBAL_MIN, GLOBAL_MAX), (15, 115, 500, -100)],
)
def test_clamp_series_raises_on_inverted_bounds(mn, mx, gmin, gmax) -> None:
    with pytest.raises(ValueError):
        clamp_series(np.array([50.0]), mn, mx, gmin, gmax)
