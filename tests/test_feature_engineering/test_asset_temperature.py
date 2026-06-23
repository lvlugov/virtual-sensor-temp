"""Tests for lean_virtual_sensor.feature_engineering.asset_temperature.

Expected numerical values depend on the calibration in
``lean_virtual_sensor/config.yaml`` (NACE coefficients, Magnus constants,
wetness band). When those change, update the expected values here.
"""

import pandas as pd
import pytest
from lean_virtual_sensor.feature_engineering.asset_temperature import (
    compute_ach,
    compute_ach_for_asset,
    compute_f_closed,
    compute_f_open,
    compute_hour_score,
    compute_k,
    compute_t_dew,
    compute_t_skin,
    compute_wetness,
)

# The standard test asset, as individual fields — the feature functions take
# separate scalar args (no dataclass/dict), so each field is passed explicitly
# at every call site below.
INSULATION_MATERIAL = "MINERAL_WOOL"
INSULATION_THICKNESS = 50
COMPONENT_DIAMETER = 100
FURNISHED_THICKNESS = 5
INSULATION_CONDITION = "ABOVE_AVERAGE"
CLADDING_INTEGRITY = "ABOVE_AVERAGE"

# Fixed reference dates so every test's window placement is deterministic.
# LAST_INSPECTION is well before TODAY - 90 days, so the ACH window is the
# full configured 90-day trailing slice and the tests' small DataFrames
# (whose datetimes end at TODAY) sit comfortably inside it.
TODAY = pd.Timestamp("2026-05-26")
LAST_INSPECTION = pd.Timestamp("2024-01-01")


def _weather_df(temp: float, humidity: float, n_hours: int = 3) -> pd.DataFrame:
    """Small hourly weather frame whose datetimes end at TODAY."""
    return pd.DataFrame(
        {
            "datetime": pd.date_range(end=TODAY, periods=n_hours, freq="h"),
            "temp": [temp] * n_hours,
            "humidity": [humidity] * n_hours,
        }
    )


def _process_df(t_process: float, n_hours: int = 3) -> pd.DataFrame:
    """Small hourly process-historian frame matching _weather_df's datetimes."""
    return pd.DataFrame(
        {
            "datetime": pd.date_range(end=TODAY, periods=n_hours, freq="h"),
            "process_temperature_c": [t_process] * n_hours,
        }
    )


# --- Step 1: Surface temperature ---


def test_compute_k_in_unit_interval():
    k = compute_k(
        "MINERAL_WOOL", insulation_thickness_mm=50, pipe_diameter_mm=100, wall_thickness_mm=5
    )
    assert 0 < k < 1


def test_compute_k_rejects_unknown_insulation():
    with pytest.raises(ValueError):
        compute_k("UNOBTAINIUM", 50, 100, 5)


def test_compute_k_rejects_non_positive_insulation_thickness():
    with pytest.raises(ValueError):
        compute_k(
            "MINERAL_WOOL", insulation_thickness_mm=0, pipe_diameter_mm=100, wall_thickness_mm=5
        )


def test_compute_k_rejects_non_positive_pipe_diameter():
    with pytest.raises(ValueError):
        compute_k(
            "MINERAL_WOOL", insulation_thickness_mm=50, pipe_diameter_mm=-10, wall_thickness_mm=5
        )


def test_compute_k_rejects_non_positive_wall_thickness():
    with pytest.raises(ValueError):
        compute_k(
            "MINERAL_WOOL", insulation_thickness_mm=50, pipe_diameter_mm=100, wall_thickness_mm=0
        )


def test_compute_k_rejects_wall_thickness_leaving_no_bore():
    # wall_thickness >= pipe_diameter / 2 → bore radius ≤ 0 → division by zero
    # in the internal film resistance. Fail fast with a clear message instead.
    with pytest.raises(ValueError):
        compute_k(
            "MINERAL_WOOL", insulation_thickness_mm=50, pipe_diameter_mm=100, wall_thickness_mm=50
        )


def test_compute_k_thicker_insulation_lowers_k():
    k_thin = compute_k("MINERAL_WOOL", 25, 100, 5)
    k_thick = compute_k("MINERAL_WOOL", 100, 100, 5)
    assert k_thick < k_thin


def test_compute_k_gas_service_raises_k_above_liquid_service():
    # k = R_inside / R_total. Low h_internal (gas, ~50) inflates R_inside,
    # so k rises and T_skin is pulled toward T_ambient.
    k_gas = compute_k("MINERAL_WOOL", 50, 100, 5, h_internal=50)
    k_liquid = compute_k("MINERAL_WOOL", 50, 100, 5, h_internal=1000)
    assert k_gas > k_liquid


def test_compute_t_skin_k_zero_returns_process_temperature():
    assert compute_t_skin(t_process=150, t_ambient=20, k=0) == 150


def test_compute_t_skin_k_one_returns_ambient_temperature():
    assert compute_t_skin(t_process=150, t_ambient=20, k=1) == 20


def test_compute_t_skin_midpoint():
    assert compute_t_skin(t_process=100, t_ambient=0, k=0.5) == 50


# --- Step 2: NACE damage factor ---


def test_compute_f_closed_zero_below_band():
    assert compute_f_closed(-10) == 0.0


def test_compute_f_closed_zero_above_band():
    assert compute_f_closed(200) == 0.0


def test_compute_f_closed_linear_within_band():
    # slope_closed = 0.00525, t_low = -4 → f(50) = 0.00525 * 54 = 0.2835
    assert compute_f_closed(50) == pytest.approx(0.2835)


def test_compute_f_open_zero_below_band():
    assert compute_f_open(-10) == 0.0


def test_compute_f_open_zero_above_band():
    assert compute_f_open(200) == 0.0


def test_compute_f_open_passes_through_knot_at_80c():
    # Digitised peak knot: (80 °C, 0.42).
    assert compute_f_open(80) == pytest.approx(0.42)


def test_compute_f_open_linear_extrapolates_below_lowest_knot():
    # Below 40 °C but inside the active band: linear extrapolation with the
    # slope of the (40, 60) segment = (0.35 - 0.27) / 20 = 0.004.
    # f(20) = 0.27 + 0.004 * (20 - 40) = 0.19.
    assert compute_f_open(20) == pytest.approx(0.19)


def test_compute_f_open_linear_extrapolates_above_highest_knot():
    # Above 100 °C but inside the active band: slope of (90, 100) segment
    # = (0.35 - 0.40) / 10 = -0.005. f(150) = 0.35 + (-0.005) * 50 = 0.10.
    assert compute_f_open(150) == pytest.approx(0.10)


# --- Step 3: Dew point and wetness ---


def test_compute_t_dew_rejects_zero_humidity():
    with pytest.raises(ValueError):
        compute_t_dew(t_ambient=20, rh_percent=0)


def test_compute_t_dew_rejects_negative_humidity():
    with pytest.raises(ValueError):
        compute_t_dew(t_ambient=20, rh_percent=-5)


def test_compute_t_dew_rejects_above_100_humidity():
    # Above-100 RH is physically impossible — likely a bad-data sentinel.
    with pytest.raises(ValueError):
        compute_t_dew(t_ambient=20, rh_percent=120)


def test_compute_t_dew_at_full_saturation_equals_ambient():
    # RH = 100 % → air is saturated → dew point coincides with ambient.
    assert compute_t_dew(t_ambient=20, rh_percent=100) == pytest.approx(20, abs=1e-9)


def test_compute_wetness_condensing_at_or_below_dew_point():
    assert compute_wetness(t_skin=5, t_dew=10) == 1.0
    assert compute_wetness(t_skin=10, t_dew=10) == 1.0


def test_compute_wetness_dry_at_or_above_transition_band():
    # band = 10 °C → at T_skin = T_dew + 10 and beyond, w = 0.
    assert compute_wetness(t_skin=20, t_dew=10) == 0.0
    assert compute_wetness(t_skin=25, t_dew=10) == 0.0


def test_compute_wetness_linear_inside_transition_band():
    # T_skin halfway through the 10 °C band → w = 0.5.
    assert compute_wetness(t_skin=15, t_dew=10) == pytest.approx(0.5)


# --- Step 4: Hourly damage score ---


def test_compute_hour_score_multiplies_factors():
    assert compute_hour_score(f_t_skin=0.42, wetness=0.5) == pytest.approx(0.21)


def test_compute_hour_score_zero_when_either_factor_zero():
    assert compute_hour_score(0.42, 0.0) == 0.0
    assert compute_hour_score(0.0, 1.0) == 0.0


# --- Step 5: Active CUI Hours ---


def test_compute_ach_empty_sequence_is_zero():
    assert compute_ach([]) == 0


def test_compute_ach_sums_per_hour_scores():
    assert compute_ach([0.1, 0.2, 0.3]) == pytest.approx(0.6)


# --- Pipeline: tie Steps 1-5 together ---


def test_compute_ach_for_asset_dry_hot_is_zero():
    # Hot process + warm dry air → T_skin sits far above T_dew + band, so
    # wetness = 0 every hour → ACH = 0.
    ach = compute_ach_for_asset(
        INSULATION_MATERIAL,
        INSULATION_THICKNESS,
        COMPONENT_DIAMETER,
        FURNISHED_THICKNESS,
        INSULATION_CONDITION,
        CLADDING_INTEGRITY,
        _weather_df(temp=30, humidity=20),
        _process_df(t_process=100),
        LAST_INSPECTION,
        TODAY,
    )
    assert ach == 0.0


def test_compute_ach_for_asset_wet_warm_is_positive():
    # Modest process temp with cool wet ambient → T_skin lands inside the
    # wetness transition band → both f and w positive → ACH > 0.
    ach = compute_ach_for_asset(
        INSULATION_MATERIAL,
        INSULATION_THICKNESS,
        COMPONENT_DIAMETER,
        FURNISHED_THICKNESS,
        INSULATION_CONDITION,
        CLADDING_INTEGRITY,
        _weather_df(temp=15, humidity=95),
        _process_df(t_process=20),
        LAST_INSPECTION,
        TODAY,
    )
    assert ach > 0


def test_compute_ach_for_asset_open_vs_closed_differs():
    # Same geometry; differ only on condition strings. Both ABOVE_AVERAGE →
    # closed (uses compute_f_closed); cladding BELOW_AVERAGE → open (uses
    # compute_f_open). At low T_skin those two curves disagree, so ACH differs.
    weather = _weather_df(temp=15, humidity=95, n_hours=24)
    process = _process_df(t_process=20, n_hours=24)
    ach_closed = compute_ach_for_asset(
        INSULATION_MATERIAL,
        INSULATION_THICKNESS,
        COMPONENT_DIAMETER,
        FURNISHED_THICKNESS,
        "ABOVE_AVERAGE",
        "ABOVE_AVERAGE",
        weather,
        process,
        LAST_INSPECTION,
        TODAY,
    )
    ach_open = compute_ach_for_asset(
        INSULATION_MATERIAL,
        INSULATION_THICKNESS,
        COMPONENT_DIAMETER,
        FURNISHED_THICKNESS,
        "ABOVE_AVERAGE",
        "BELOW_AVERAGE",
        weather,
        process,
        LAST_INSPECTION,
        TODAY,
    )
    assert ach_closed != ach_open


def test_compute_ach_for_asset_inspection_in_or_after_today_is_zero():
    # When last_inspection_date is at or beyond today, the window collapses
    # to empty — no trailing period exists to summarise. Symmetric with
    # compute_wet_load's behaviour for the pre-ACH window.
    ach = compute_ach_for_asset(
        INSULATION_MATERIAL,
        INSULATION_THICKNESS,
        COMPONENT_DIAMETER,
        FURNISHED_THICKNESS,
        INSULATION_CONDITION,
        CLADDING_INTEGRITY,
        _weather_df(temp=15, humidity=95),
        _process_df(t_process=20),
        TODAY,  # inspection == today
        TODAY,
    )
    assert ach == 0.0


def test_compute_ach_for_asset_empty_frames_is_zero():
    # Empty weather + process frames → empty joined window → ACH = 0.
    empty_weather = pd.DataFrame(columns=["datetime", "temp", "humidity"])
    empty_process = pd.DataFrame(columns=["datetime", "process_temperature_c"])
    ach = compute_ach_for_asset(
        INSULATION_MATERIAL,
        INSULATION_THICKNESS,
        COMPONENT_DIAMETER,
        FURNISHED_THICKNESS,
        INSULATION_CONDITION,
        CLADDING_INTEGRITY,
        empty_weather,
        empty_process,
        LAST_INSPECTION,
        TODAY,
    )
    assert ach == 0.0


def test_compute_ach_for_asset_propagates_bad_geometry():
    # Geometry is validated at point of use; a bad value surfaces from
    # compute_k when the pipeline runs.
    with pytest.raises(ValueError):
        compute_ach_for_asset(
            INSULATION_MATERIAL,
            -50,  # insulation_thickness — invalid
            COMPONENT_DIAMETER,
            FURNISHED_THICKNESS,
            INSULATION_CONDITION,
            CLADDING_INTEGRITY,
            _weather_df(temp=15, humidity=95, n_hours=1),
            _process_df(t_process=20, n_hours=1),
            LAST_INSPECTION,
            TODAY,
        )


def test_compute_ach_for_asset_propagates_bad_rh():
    with pytest.raises(ValueError):
        compute_ach_for_asset(
            INSULATION_MATERIAL,
            INSULATION_THICKNESS,
            COMPONENT_DIAMETER,
            FURNISHED_THICKNESS,
            INSULATION_CONDITION,
            CLADDING_INTEGRITY,
            _weather_df(temp=15, humidity=150, n_hours=1),
            _process_df(t_process=20, n_hours=1),
            LAST_INSPECTION,
            TODAY,
        )


def test_compute_ach_for_asset_resamples_subhourly_process_data_to_hourly():
    # Process historian samples every 15 minutes (4 rows per hour) at
    # timestamps that don't land on :00:00. With a raw exact-datetime
    # merge, none of these rows would match the hourly weather data and
    # ACH would be 0. The internal resample-to-hourly bucket lets it
    # match — score should equal what we'd get from clean hourly process
    # data at the same value.
    n_hours = 3
    process_subhourly = pd.DataFrame(
        {
            "datetime": pd.date_range(end=TODAY, periods=4 * n_hours, freq="15min"),
            "process_temperature_c": [20.0] * (4 * n_hours),
        }
    )
    weather = _weather_df(temp=15, humidity=95, n_hours=n_hours)
    ach_subhourly = compute_ach_for_asset(
        INSULATION_MATERIAL,
        INSULATION_THICKNESS,
        COMPONENT_DIAMETER,
        FURNISHED_THICKNESS,
        INSULATION_CONDITION,
        CLADDING_INTEGRITY,
        weather,
        process_subhourly,
        LAST_INSPECTION,
        TODAY,
    )
    ach_hourly = compute_ach_for_asset(
        INSULATION_MATERIAL,
        INSULATION_THICKNESS,
        COMPONENT_DIAMETER,
        FURNISHED_THICKNESS,
        INSULATION_CONDITION,
        CLADDING_INTEGRITY,
        weather,
        _process_df(t_process=20, n_hours=n_hours),
        LAST_INSPECTION,
        TODAY,
    )
    assert ach_subhourly == pytest.approx(ach_hourly)
