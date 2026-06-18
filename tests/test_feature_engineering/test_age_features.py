"""Tests for lean_virtual_sensor.feature_engineering.age_features.

Covers the year-floor convention, the same-day → 0 edge case, and the
future-date rejection.
"""

import pandas as pd
import pytest
from lean_virtual_sensor.feature_engineering.age_features import (
    compute_age_years,
)

TODAY = pd.Timestamp("2026-05-26")


def test_exact_year_returns_one():
    # 365 days before today → exactly one full year.
    date = TODAY - pd.Timedelta(days=365)
    assert compute_age_years(date, TODAY) == 1


def test_one_day_short_of_a_year_returns_zero():
    # 364 days before today → not quite a full year yet → floor to 0.
    date = TODAY - pd.Timedelta(days=364)
    assert compute_age_years(date, TODAY) == 0


def test_same_day_returns_zero():
    assert compute_age_years(TODAY, TODAY) == 0


def test_typical_coating_age():
    # Coating applied 2020-06-01, today 2026-05-26 → ~5.98 years → floor 5.
    date = pd.Timestamp("2020-06-01")
    assert compute_age_years(date, TODAY) == 5


def test_typical_system_age():
    # Insulation installed 2015-03-15, today 2026-05-26 → ~11.20 years → 11.
    date = pd.Timestamp("2015-03-15")
    assert compute_age_years(date, TODAY) == 11


def test_returns_int_not_float():
    age = compute_age_years(TODAY - pd.Timedelta(days=730), TODAY)
    assert isinstance(age, int)
    assert age == 2


def test_future_date_raises():
    future = TODAY + pd.Timedelta(days=10)
    with pytest.raises(ValueError, match="later than today"):
        compute_age_years(future, TODAY)


def test_one_day_in_the_future_raises():
    # Strict: even one day off counts as the wrong argument order, not a
    # rounding-zone forgiveness.
    future = TODAY + pd.Timedelta(days=1)
    with pytest.raises(ValueError):
        compute_age_years(future, TODAY)
