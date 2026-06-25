"""Config loader scoped to the ``api_583_risk`` package.

Reads from ``api_583_risk/config.yaml`` (shipped alongside this
package) so that every API 583 threshold, allowed-value list, and
lookup mapping lives in one auditable file next to the scorer code.
The project-wide :mod:`lean_virtual_sensor.config` loader is left
untouched for cross-cutting features.
"""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"


@lru_cache(maxsize=1)
def _load_api_583_doc() -> dict[str, Any]:
    """Parse ``api_583_risk/config.yaml`` once and memoise it.

    The config is static for a process's lifetime, so caching the parse turns
    the thousands of ``load_api_583_section`` calls a population run makes (seven
    scorers per asset, some called more than once) into a single disk read.
    """
    if not _CONFIG_PATH.is_file():
        raise FileNotFoundError(f"API 583 config not found at {_CONFIG_PATH}")
    with _CONFIG_PATH.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{_CONFIG_PATH} must be a YAML mapping")
    return data


def load_api_583_section(
    subsection: str,
    required_keys: Iterable[str] = (),
) -> dict[str, Any]:
    """Load one subsection from ``api_583_risk/config.yaml``.

    Args:
        subsection: Top-level key in the package config (for example,
            ``"operating_temperature"``).
        required_keys: Keys that must be present under ``subsection``;
            missing keys raise ``KeyError`` so misconfiguration fails
            up front rather than at use.

    Returns:
        The subsection as a dict.

    Raises:
        FileNotFoundError: If ``config.yaml`` is missing from the
            package directory.
        KeyError: If ``subsection`` is absent or any of
            ``required_keys`` is missing.
        ValueError: If the resolved subsection is not a YAML mapping.
    """
    data = _load_api_583_doc()
    if subsection not in data:
        raise KeyError(f"{_CONFIG_PATH.name} is missing subsection: {subsection!r}")
    section = data[subsection]
    if not isinstance(section, dict):
        raise ValueError(f"{_CONFIG_PATH.name} subsection {subsection!r} must be a mapping")
    for key in required_keys:
        if key not in section:
            raise KeyError(f"{subsection} subsection is missing required key: {key!r}")
    return section
