"""Hourly weather fetch from Visual Crossing — per-asset and bulk paths.

Two entry points:

* :func:`fetch_hourly_window` — per-asset, live: one HTTP call covers
  ``[last_inspection_date, today]`` and returns a DataFrame. Used by
  :func:`...feature_pipeline.compute_features_for_asset` for inference.

* :func:`fetch_bulk_to_disk` — one-shot, fleet-wide: iterates the
  ``locations`` block in ``config.yaml`` and saves 10 years of hourly
  weather per location to one CSV each. Used to pre-build training data
  so downstream feature code doesn't re-hit Visual Crossing every run.

Visual Crossing chosen over Open-Meteo because per-asset windows can span
multiple years between inspections, and Visual Crossing's API-key-based
daily-record quota gives predictable headroom that Open-Meteo's
cost-weighted free tier did not.

Endpoint base URL, API key, and timeout come from the ``api`` section of
``config.yaml``.
"""

from __future__ import annotations

import os
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from dotenv import load_dotenv

from lean_virtual_sensor.config import load_config, load_section, resolve_config_path

# Auto-load .env on import so VISUAL_CROSSING_API_KEY is in os.environ
# before any fetch runs. `make env` creates .env from .env.example.
load_dotenv()

CONFIG_SECTION = "api"
REQUIRED_KEYS = (
    "base_url",
    "request_timeout_seconds",
)
API_KEY_ENV_VAR = "VISUAL_CROSSING_API_KEY"

# Fleet-wide pre-fetch covers a trailing 10-year window. Hardcoded rather
# than config-driven: this is a "decide once for training-set generation"
# parameter, not a per-call knob.
BULK_YEARS_BACK = 10

# Visual Crossing's free / starter plans cap each query at ~10 000 records.
# A 365-day hourly window is 8 760 records, comfortably under the cap. The
# fetch function splits any longer window into sequential ~1-year chunks
# and concatenates the results.
CHUNK_DAYS = 365

# Visual Crossing native field names (unitGroup=metric → °C, mm, %).
HOURLY_FIELDS: tuple[str, ...] = (
    "temp",      # air temperature, °C
    "dew",       # dew point, °C
    "humidity",  # relative humidity, %
    "precip",    # hourly precipitation, mm
)


def fetch_hourly_window(
    latitude: float,
    longitude: float,
    last_inspection_date: date,
    today: date | None = None,
) -> pd.DataFrame:
    """Fetch hourly weather for one location from last inspection through today.

    Args:
        latitude: Asset latitude in decimal degrees.
        longitude: Asset longitude in decimal degrees.
        last_inspection_date: First day in the window (inclusive). Typically
            the asset's most recent inspection date.
        today: Last day in the window (inclusive). Defaults to ``date.today()``.

    Returns:
        DataFrame with one row per hour. Columns:

        =================  ========================================
        ``datetime``       Naive ``pd.Timestamp`` (UTC wall-clock), hour resolution
        ``temp``           Air temperature, °C
        ``dew``            Dew point, °C
        ``humidity``       Relative humidity, %
        ``precip``         Hourly precipitation, mm
        =================  ========================================

    Raises:
        ValueError: If the ``VISUAL_CROSSING_API_KEY`` env var is empty.
        requests.HTTPError: For non-2xx responses from Visual Crossing.
        requests.RequestException: For network/timeout failures.
    """
    cfg = load_section(CONFIG_SECTION, REQUIRED_KEYS)
    api_key = os.environ.get(API_KEY_ENV_VAR, "")
    if not api_key:
        raise ValueError(
            f"{API_KEY_ENV_VAR} env var is not set. "
            f"Run `make env` to create a .env from the template, then "
            f"add your Visual Crossing API key to it."
        )

    end = today if today is not None else date.today()

    rows: list[dict] = []
    chunk_start = last_inspection_date
    while chunk_start <= end:
        chunk_end = min(end, chunk_start + timedelta(days=CHUNK_DAYS - 1))
        rows.extend(_fetch_chunk(cfg, api_key, latitude, longitude, chunk_start, chunk_end))
        chunk_start = chunk_end + timedelta(days=1)
    return pd.DataFrame(rows, columns=["datetime", *HOURLY_FIELDS])


def _fetch_chunk(
    cfg: dict[str, Any],
    api_key: str,
    latitude: float,
    longitude: float,
    start: date,
    end: date,
) -> list[dict]:
    """Issue one Visual Crossing request and return its hourly rows.

    Internal — :func:`fetch_hourly_window` splits its requested window
    into chunks of at most :data:`CHUNK_DAYS` days and calls this helper
    for each. Returns a list of row dicts ready to feed ``pd.DataFrame``.
    """
    url = (
        f"{str(cfg['base_url']).rstrip('/')}/"
        f"{latitude},{longitude}/"
        f"{start.isoformat()}/{end.isoformat()}"
    )
    params = {
        "key": api_key,
        "unitGroup": "metric",
        "include": "hours",
        "elements": "datetime," + ",".join(HOURLY_FIELDS),
        "contentType": "json",
        # Request UTC explicitly so the returned datetime strings are
        # unambiguous; we then store them tz-naive for consistency with
        # how dates flow through compute_wet_load and the orchestrator.
        "timezone": "UTC",
    }
    response = requests.get(url, params=params, timeout=cfg["request_timeout_seconds"])
    response.raise_for_status()
    payload = response.json()

    rows: list[dict] = []
    for day in payload.get("days", []):
        day_date = day["datetime"]
        for hour in day.get("hours", []):
            rows.append(
                {
                    "datetime": pd.Timestamp(f"{day_date} {hour['datetime']}"),
                    **{field: hour.get(field) for field in HOURLY_FIELDS},
                }
            )
    return rows


# ====================================== Bulk fleet pre-fetch ======================================


def _slugify(text: str) -> str:
    """Lowercase, replace non-alphanumeric runs with underscores."""
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "x"


def fetch_bulk_to_disk(
    output_dir: Path | str | None = None,
    target: tuple[str, str] | None = None,
) -> int:
    """Fetch the trailing 10 years of hourly weather and write one CSV per location.

    Reads the ``locations`` block from ``config.yaml`` and, for each
    matching entry, calls :func:`fetch_hourly_window` with a window of
    ``[today - 10 years, today]`` then writes the returned DataFrame to
    one CSV named ``{operator_slug}_{site_slug}.csv`` in ``output_dir``.
    Failures for individual locations are logged with ``print`` and
    skipped; successful locations are not retried.

    Args:
        output_dir: Destination directory for the CSVs. ``None`` resolves
            to ``output/`` relative to the directory containing
            ``config.yaml``.
        target: Optional ``(operator, site)`` pair. When set, only that
            one location is fetched; otherwise the full ``locations:``
            block is iterated. Case-insensitive match against the
            ``operator`` and ``site`` fields in config.

    Returns:
        Number of locations successfully fetched and written (``1`` in
        single-asset mode on success, ``0-N`` in fleet mode).

    Raises:
        KeyError: If ``locations`` is missing or empty in ``config.yaml``.
        ValueError: If ``target`` is supplied but no matching location
            exists, or propagated from :func:`fetch_hourly_window` when
            the ``VISUAL_CROSSING_API_KEY`` env var is empty.
    """
    cfg = load_config()
    locations: list[dict[str, Any]] = cfg.get("locations") or []
    if not locations:
        raise KeyError("config.yaml has no 'locations' block, or it is empty.")

    if target is not None:
        op_target, site_target = (s.casefold() for s in target)
        matched = [
            loc
            for loc in locations
            if loc["operator"].casefold() == op_target
            and loc["site"].casefold() == site_target
        ]
        if not matched:
            available = sorted(f"{loc['operator']}/{loc['site']}" for loc in locations)
            raise ValueError(
                f"target {target!r} not found. Available: {available}"
            )
        locations = matched

    if output_dir is None:
        output_dir = resolve_config_path().parent / "output"
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    today = date.today()
    start = today - timedelta(days=BULK_YEARS_BACK * 365)

    mode = "Single-asset fetch" if target is not None else "Bulk fetch"
    print(
        f"{mode}: {len(locations)} location(s) x {BULK_YEARS_BACK} years "
        f"({start} -> {today}). Output: {output_path}/"
    )

    n_ok = 0
    for i, loc in enumerate(locations, start=1):
        op = loc["operator"]
        site = loc["site"]
        filename = f"{_slugify(op)}_{_slugify(site)}.csv"
        try:
            df = fetch_hourly_window(
                latitude=loc["latitude"],
                longitude=loc["longitude"],
                last_inspection_date=start,
                today=today,
            )
        except requests.RequestException as exc:
            print(f"  WARN [{i}/{len(locations)}] {op}/{site}: {exc}")
            continue
        df.to_csv(output_path / filename, index=False)
        n_ok += 1
        print(f"  OK   [{i}/{len(locations)}] {op}/{site} -> {filename} ({len(df)} rows)")

    print(f"Done. {n_ok}/{len(locations)} locations written to {output_path}/.")
    return n_ok


def load_cached_weather(
    operator: str,
    site: str,
    cache_dir: Path | str | None = None,
) -> pd.DataFrame:
    """Load the cached hourly weather DataFrame for one asset.

    Reads ``{operator_slug}_{site_slug}.csv`` from ``cache_dir`` — the file
    written by :func:`fetch_bulk_to_disk` — and parses the ``datetime``
    column back to ``pd.Timestamp``. This is the production path
    consumed by :func:`...feature_pipeline.compute_features_for_asset`;
    no live HTTP call is made.

    Args:
        operator: Operator name as it appears in the ``locations:`` block
            (case is normalised by the slugifier).
        site: Site name (slug-normalised the same way).
        cache_dir: Directory containing the per-location CSVs. ``None``
            resolves to ``output/`` next to ``config.yaml``.

    Returns:
        DataFrame with columns ``datetime`` (naive ``pd.Timestamp``),
        ``temp``, ``dew``, ``humidity``, ``precip``.

    Raises:
        FileNotFoundError: If the expected CSV does not exist. Most often
            means ``fetch_bulk_to_disk`` hasn't been run for this fleet
            yet, or the operator/site names don't match what's on disk.
    """
    if cache_dir is None:
        cache_dir = resolve_config_path().parent / "output"
    filename = f"{_slugify(operator)}_{_slugify(site)}.csv"
    path = Path(cache_dir) / filename
    if not path.exists():
        raise FileNotFoundError(
            f"Cached weather not found at {path}. "
            f"Run fetch_bulk_to_disk() to generate the cache, or check "
            f"that operator={operator!r} / site={site!r} match a locations: entry."
        )
    return pd.read_csv(path, parse_dates=["datetime"])
