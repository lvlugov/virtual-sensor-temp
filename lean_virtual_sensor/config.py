"""Shared YAML config loader for ``lean_virtual_sensor``.

The config file path is resolved in this order:

1. ``LEAN_VS_CONFIG`` environment variable (absolute or relative path)
2. ``config.yaml`` shipped alongside this package

Modules that consume config should call :func:`load_section` to fetch their
own top-level block, supplying the keys they require for up-front validation.
Scripts that need the whole document can use :func:`load_config` directly.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml

CONFIG_ENV_VAR = "LEAN_VS_CONFIG"
PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = PACKAGE_ROOT / "config.yaml"


def resolve_config_path() -> Path:
    """Locate ``config.yaml`` via the env var or the package default.

    Returns:
        Resolved absolute path to the config file.

    Raises:
        FileNotFoundError: If no config file is found at either location.
    """
    env_value = os.environ.get(CONFIG_ENV_VAR)
    path = (Path(env_value).expanduser() if env_value else DEFAULT_CONFIG_PATH).resolve()
    if not path.is_file():
        raise FileNotFoundError(
            f"Config file not found at {path}. "
            f"Set ${CONFIG_ENV_VAR} or place config.yaml at {DEFAULT_CONFIG_PATH}."
        )
    return path


def load_config() -> dict[str, Any]:
    """Load and return the full ``config.yaml`` document as a mapping.

    Returns:
        Parsed YAML as a dict.

    Raises:
        FileNotFoundError: If no config file is found.
        ValueError: If the config file is not a YAML mapping.
    """
    path = resolve_config_path()
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Config at {path} must be a YAML mapping.")
    return data


def load_section(section: str, required_keys: Iterable[str] = ()) -> dict[str, Any]:
    """Load a single top-level section from ``config.yaml``.

    Args:
        section: Top-level key in ``config.yaml`` (for example, ``"asset_temperature"``).
        required_keys: Sub-keys that must be present in the section; missing keys
            raise ``KeyError`` so misconfiguration fails up front rather than at use.

    Returns:
        The section as a dict.

    Raises:
        KeyError: If the section is absent, or any of ``required_keys`` is missing.
        ValueError: If the section is not a mapping.
    """
    data = load_config()
    if section not in data:
        raise KeyError(f"config.yaml is missing required key: {section!r}")
    section_data = data[section]
    if not isinstance(section_data, dict):
        raise ValueError(f"config.yaml section {section!r} must be a mapping.")
    for key in required_keys:
        if key not in section_data:
            raise KeyError(f"{section} section is missing required key: {key!r}")
    return section_data
