"""Tests for the bulk fleet pre-fetch in external_temperature.

HTTP is mocked at ``external_temperature.requests.get``; ``load_config``
and ``load_section`` are mocked at the same import site so the function
runs with a tiny in-memory location list, without touching real
config.yaml or hitting Visual Crossing. The API key is read from the
``VISUAL_CROSSING_API_KEY`` env var, which an autouse fixture sets to
a fake value for every test.
"""

from datetime import timedelta
from unittest.mock import patch

import pandas as pd
import pytest
import requests
from lean_virtual_sensor.feature_engineering.external_temperature import (
    fetch_bulk_to_disk,
    fetch_hourly_window,
    load_cached_weather,
)


@pytest.fixture(autouse=True)
def _fake_api_key(monkeypatch):
    """Set a fake VISUAL_CROSSING_API_KEY for every test in this module.

    The real key lives in .env at runtime; tests should never touch the
    real env var. monkeypatch scopes the override to one test and reverts
    automatically.
    """
    monkeypatch.setenv("VISUAL_CROSSING_API_KEY", "fake-test-key")


FAKE_API_CONFIG = {
    "base_url": "https://fake.test/timeline",
    "request_timeout_seconds": 30,
}

FAKE_LOCATIONS = [
    {
        "operator": "DOW",
        "site": "Freeport",
        "country": "USA",
        "latitude": 28.9544,
        "longitude": -95.3597,
    },
    {
        "operator": "Aramco",
        "site": "Berth 51",
        "country": "Saudi Arabia",
        "latitude": 26.644,
        "longitude": 50.1583,
    },
]


def _vc_payload(start, end, *, temp=20.0, dew=15.0, humidity=70, precip=0.0):
    """Minimal Visual Crossing-shaped payload of constant hourly values."""
    days = []
    cursor = start
    while cursor <= end:
        days.append(
            {
                "datetime": cursor.strftime("%Y-%m-%d"),
                "hours": [
                    {
                        "datetime": f"{h:02d}:00:00",
                        "temp": temp,
                        "dew": dew,
                        "humidity": humidity,
                        "precip": precip,
                    }
                    for h in range(24)
                ],
            }
        )
        cursor = cursor + timedelta(days=1)
    return {"days": days}


class _FakeResponse:
    """Minimal stand-in for requests.Response: .json() and .raise_for_status()."""

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


@patch("lean_virtual_sensor.feature_engineering.external_temperature.resolve_config_path")
@patch("lean_virtual_sensor.feature_engineering.external_temperature.load_config")
@patch("lean_virtual_sensor.feature_engineering.external_temperature.load_section")
@patch("lean_virtual_sensor.feature_engineering.external_temperature.requests.get")
def test_fetch_bulk_to_disk_writes_one_csv_per_location(
    mock_get, mock_load_section, mock_load_config, mock_resolve_path, tmp_path
):
    mock_load_section.return_value = FAKE_API_CONFIG
    mock_load_config.return_value = {"locations": FAKE_LOCATIONS}
    mock_resolve_path.return_value = tmp_path / "config.yaml"

    # All locations get the same tiny payload (3 days) so the test runs
    # fast; the bulk function still requests 10 years upstream.
    today = pd.Timestamp.today().normalize().date()
    start = today - timedelta(days=2)
    mock_get.return_value = _FakeResponse(_vc_payload(start, today))

    n_ok = fetch_bulk_to_disk(output_dir=tmp_path / "weather_cache")

    assert n_ok == 2
    assert (tmp_path / "weather_cache" / "dow_freeport.csv").exists()
    assert (tmp_path / "weather_cache" / "aramco_berth_51.csv").exists()

    df = pd.read_csv(tmp_path / "weather_cache" / "dow_freeport.csv")
    assert set(df.columns) == {"datetime", "temp", "dew", "humidity", "precip"}
    # Exact row count is sensitive to chunking; verify the file has rows
    # and the rows are whole-day multiples (hourly cadence preserved).
    assert len(df) > 0
    assert len(df) % 24 == 0


@patch("lean_virtual_sensor.feature_engineering.external_temperature.resolve_config_path")
@patch("lean_virtual_sensor.feature_engineering.external_temperature.load_config")
@patch("lean_virtual_sensor.feature_engineering.external_temperature.load_section")
def test_fetch_bulk_to_disk_raises_on_empty_locations(
    mock_load_section, mock_load_config, mock_resolve_path, tmp_path
):
    mock_load_section.return_value = FAKE_API_CONFIG
    mock_load_config.return_value = {"locations": []}
    mock_resolve_path.return_value = tmp_path / "config.yaml"

    with pytest.raises(KeyError):
        fetch_bulk_to_disk(output_dir=tmp_path / "weather_cache")


@patch("lean_virtual_sensor.feature_engineering.external_temperature.resolve_config_path")
@patch("lean_virtual_sensor.feature_engineering.external_temperature.load_config")
@patch("lean_virtual_sensor.feature_engineering.external_temperature.load_section")
@patch("lean_virtual_sensor.feature_engineering.external_temperature.requests.get")
def test_fetch_bulk_to_disk_skips_failing_locations(
    mock_get, mock_load_section, mock_load_config, mock_resolve_path, tmp_path
):
    mock_load_section.return_value = FAKE_API_CONFIG
    mock_load_config.return_value = {"locations": FAKE_LOCATIONS}
    mock_resolve_path.return_value = tmp_path / "config.yaml"

    today = pd.Timestamp.today().normalize().date()
    start = today - timedelta(days=2)
    good_payload = _vc_payload(start, today)

    def _side_effect(url, params, timeout):
        # DOW/Freeport (lat 28.9544) succeeds; Aramco/Berth 51 raises.
        if "28.9544" in url:
            return _FakeResponse(good_payload)
        raise requests.RequestException("simulated network failure")

    mock_get.side_effect = _side_effect

    n_ok = fetch_bulk_to_disk(output_dir=tmp_path / "weather_cache")

    assert n_ok == 1
    assert (tmp_path / "weather_cache" / "dow_freeport.csv").exists()
    assert not (tmp_path / "weather_cache" / "aramco_berth_51.csv").exists()


# =================================== Single-asset target filter ===================================


@patch("lean_virtual_sensor.feature_engineering.external_temperature.resolve_config_path")
@patch("lean_virtual_sensor.feature_engineering.external_temperature.load_config")
@patch("lean_virtual_sensor.feature_engineering.external_temperature.load_section")
@patch("lean_virtual_sensor.feature_engineering.external_temperature.requests.get")
def test_fetch_bulk_to_disk_target_writes_only_matching_location(
    mock_get, mock_load_section, mock_load_config, mock_resolve_path, tmp_path
):
    mock_load_section.return_value = FAKE_API_CONFIG
    mock_load_config.return_value = {"locations": FAKE_LOCATIONS}
    mock_resolve_path.return_value = tmp_path / "config.yaml"

    today = pd.Timestamp.today().normalize().date()
    start = today - timedelta(days=2)
    mock_get.return_value = _FakeResponse(_vc_payload(start, today))

    n_ok = fetch_bulk_to_disk(
        output_dir=tmp_path / "weather_cache",
        target=("DOW", "Freeport"),
    )

    assert n_ok == 1
    assert (tmp_path / "weather_cache" / "dow_freeport.csv").exists()
    # The other location must not be written when target is set.
    assert not (tmp_path / "weather_cache" / "aramco_berth_51.csv").exists()


@patch("lean_virtual_sensor.feature_engineering.external_temperature.resolve_config_path")
@patch("lean_virtual_sensor.feature_engineering.external_temperature.load_config")
@patch("lean_virtual_sensor.feature_engineering.external_temperature.load_section")
@patch("lean_virtual_sensor.feature_engineering.external_temperature.requests.get")
def test_fetch_bulk_to_disk_target_is_case_insensitive(
    mock_get, mock_load_section, mock_load_config, mock_resolve_path, tmp_path
):
    mock_load_section.return_value = FAKE_API_CONFIG
    mock_load_config.return_value = {"locations": FAKE_LOCATIONS}
    mock_resolve_path.return_value = tmp_path / "config.yaml"

    today = pd.Timestamp.today().normalize().date()
    start = today - timedelta(days=2)
    mock_get.return_value = _FakeResponse(_vc_payload(start, today))

    n_ok = fetch_bulk_to_disk(
        output_dir=tmp_path / "weather_cache",
        target=("dow", "freeport"),  # lowercase, fixture has 'DOW' / 'Freeport'
    )

    assert n_ok == 1


@patch("lean_virtual_sensor.feature_engineering.external_temperature.resolve_config_path")
@patch("lean_virtual_sensor.feature_engineering.external_temperature.load_config")
@patch("lean_virtual_sensor.feature_engineering.external_temperature.load_section")
def test_fetch_bulk_to_disk_target_raises_on_unknown(
    mock_load_section, mock_load_config, mock_resolve_path, tmp_path
):
    mock_load_section.return_value = FAKE_API_CONFIG
    mock_load_config.return_value = {"locations": FAKE_LOCATIONS}
    mock_resolve_path.return_value = tmp_path / "config.yaml"

    with pytest.raises(ValueError):
        fetch_bulk_to_disk(
            output_dir=tmp_path / "weather_cache",
            target=("Nope", "Nowhere"),
        )


# ====================================== Chunking ======================================


@patch("lean_virtual_sensor.feature_engineering.external_temperature.load_section")
@patch("lean_virtual_sensor.feature_engineering.external_temperature.requests.get")
def test_fetch_hourly_window_chunks_long_requests(mock_get, mock_load_section):
    """Windows longer than CHUNK_DAYS are split into sequential sub-requests.

    Visual Crossing caps single requests at ~10 000 records. fetch_hourly_window
    must split a long window (here ~2 years) into multiple ~1-year HTTP calls
    and concatenate the rows.
    """
    from datetime import date

    mock_load_section.return_value = FAKE_API_CONFIG

    def _side_effect(url, params, timeout):
        # Each chunk returns a small 2-day payload; date range from URL
        # doesn't matter for this structural test.
        start_dummy = date(2020, 1, 1)
        end_dummy = date(2020, 1, 2)
        return _FakeResponse(_vc_payload(start_dummy, end_dummy))

    mock_get.side_effect = _side_effect

    # 2-year window → exceeds CHUNK_DAYS (365), forces at least 2 chunks.
    today = date(2024, 1, 1)
    last_inspection = today - timedelta(days=730)
    df = fetch_hourly_window(40.0, -74.0, last_inspection, today)

    # 2 years / 365-day chunks = at least 2 calls; with the +1-day stride it's 3.
    assert mock_get.call_count >= 2
    # Concatenated rows from all chunks should be present.
    assert len(df) > 0
    assert set(df.columns) == {"datetime", "temp", "dew", "humidity", "precip"}


# ====================================== load_cached_weather ======================================


def test_load_cached_weather_round_trips_a_written_csv(tmp_path):
    """Write a CSV via the bulk path then read it back via the loader."""
    df = pd.DataFrame(
        {
            "datetime": pd.date_range("2024-01-01", periods=3, freq="h"),
            "temp": [10.0, 11.0, 12.0],
            "dew": [5.0, 5.5, 6.0],
            "humidity": [80, 82, 85],
            "precip": [0.0, 0.2, 0.5],
        }
    )
    df.to_csv(tmp_path / "dow_freeport.csv", index=False)

    loaded = load_cached_weather("DOW", "Freeport", cache_dir=tmp_path)

    assert list(loaded.columns) == ["datetime", "temp", "dew", "humidity", "precip"]
    assert pd.api.types.is_datetime64_any_dtype(loaded["datetime"])
    assert len(loaded) == 3


def test_load_cached_weather_slugifies_operator_and_site(tmp_path):
    """Names with spaces / mixed case still resolve to the slug filename."""
    pd.DataFrame(
        {
            "datetime": pd.date_range("2024-01-01", periods=1, freq="h"),
            "temp": [10.0],
            "dew": [5.0],
            "humidity": [80],
            "precip": [0.0],
        }
    ).to_csv(tmp_path / "aramco_berth_51.csv", index=False)

    # Original casing + space in the site name should still find the file.
    loaded = load_cached_weather("Aramco", "Berth 51", cache_dir=tmp_path)
    assert len(loaded) == 1


def test_load_cached_weather_raises_when_csv_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_cached_weather("Nope", "Nowhere", cache_dir=tmp_path)
