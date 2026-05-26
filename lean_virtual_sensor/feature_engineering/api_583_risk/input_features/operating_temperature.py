"""API 583 CUI risk — operating-temperature scorer.

Maps an asset's operating temperature to a 0–5 CUI-likelihood score per
API 583 Annex A. Carbon and low-alloy steels follow Table A.1 with a
cyclic-service override; austenitic and duplex stainless steels follow
Table A.8 (no cyclic clause).

All thresholds, allowed enums, and family memberships are loaded from
:mod:`api_583_risk.config`.
"""

from __future__ import annotations

from lean_virtual_sensor.feature_engineering.api_583_risk._config import (
    load_api_583_section,
)

CONFIG_SUBSECTION = "operating_temperature"
REQUIRED_KEYS = (
    "allowed_metallurgy",
    "carbon_steel_families",
    "stainless_steel_families",
    "cyclic_max_temp_above_c",
    "cyclic_min_temp_below_c",
    "cs_peak_low_c",
    "cs_peak_high_c",
    "cs_mod_lower_low_c",
    "cs_mod_upper_high_c",
    "cs_envelope_low_c",
    "cs_envelope_high_c",
    "ss_peak_low_c",
    "ss_peak_high_c",
    "ss_elev_high_c",
    "ss_envelope_low_c",
)


# ====================================== Step helpers ======================================


def _validate_inputs(
    metallurgy_family: str,
    operating_temperature: float,
    min_operating_temperature: float,
    max_operating_temperature: float,
    allowed_metallurgy: set[str],
) -> None:
    """Reject unknown metallurgy or an out-of-envelope operating temperature."""
    if metallurgy_family not in allowed_metallurgy:
        raise ValueError(f"Unknown metallurgy_family: {metallurgy_family}")
    if min_operating_temperature > operating_temperature:
        raise ValueError("min_operating_temperature > operating_temperature")
    if max_operating_temperature < operating_temperature:
        raise ValueError("max_operating_temperature < operating_temperature")


def _is_cyclic_carbon_steel_service(
    min_operating_temperature: float,
    max_operating_temperature: float,
    avg_cycles_per_quarter: float,
    cyclic_max_temp_above_c: float,
    cyclic_min_temp_below_c: float,
) -> bool:
    """True when carbon-steel service swings above the upper cyclic threshold to
    below the lower cyclic threshold with active cycling."""
    return (
        max_operating_temperature > cyclic_max_temp_above_c
        and min_operating_temperature < cyclic_min_temp_below_c
        and avg_cycles_per_quarter > 0
    )


def _score_carbon_steel_buckets(operating_temperature: float, cfg: dict) -> int:
    """Table A.1 bucket lookup for carbon/low-alloy steel (steady-state)."""
    if cfg["cs_peak_low_c"] <= operating_temperature <= cfg["cs_peak_high_c"]:
        return 5
    if cfg["cs_mod_lower_low_c"] <= operating_temperature < cfg["cs_peak_low_c"]:
        return 3
    if cfg["cs_peak_high_c"] < operating_temperature <= cfg["cs_mod_upper_high_c"]:
        return 3
    if cfg["cs_envelope_low_c"] <= operating_temperature < cfg["cs_mod_lower_low_c"]:
        return 1
    if cfg["cs_mod_upper_high_c"] < operating_temperature <= cfg["cs_envelope_high_c"]:
        return 1
    return 0


def _score_stainless_steel_buckets(operating_temperature: float, cfg: dict) -> int:
    """Table A.8 bucket lookup for austenitic/duplex stainless steel."""
    if cfg["ss_peak_low_c"] <= operating_temperature <= cfg["ss_peak_high_c"]:
        return 5
    if cfg["ss_peak_high_c"] < operating_temperature <= cfg["ss_elev_high_c"]:
        return 3
    if cfg["ss_envelope_low_c"] <= operating_temperature < cfg["ss_peak_low_c"]:
        return 1
    return 0


# ====================================== Public entry point ======================================


def score_operating_temperature(
    metallurgy_family: str,
    operating_temperature: float,
    min_operating_temperature: float,
    max_operating_temperature: float,
    avg_cycles_per_quarter: float,
) -> int:
    """Score operating temperature against API 583 Annex A.

    Args:
        metallurgy_family: One of the values listed under
            ``operating_temperature.allowed_metallurgy`` in
            ``api_583_risk/config.yaml``.
        operating_temperature: Representative operating temperature
            in °C (process mean if available, else the static operating
            temperature).
        min_operating_temperature: Lower envelope of operating range, °C.
        max_operating_temperature: Upper envelope of operating range, °C.
        avg_cycles_per_quarter: Mean thermal cycles per quarter; gates
            the cyclic-service override for carbon/low-alloy steel.

    Returns:
        CUI-likelihood score in ``{0, 1, 3, 5}``.

    Raises:
        ValueError: If ``metallurgy_family`` is unknown, or if
            ``operating_temperature`` lies outside
            ``[min_operating_temperature, max_operating_temperature]``.
    """
    cfg = load_api_583_section(CONFIG_SUBSECTION, REQUIRED_KEYS)
    allowed_metallurgy = set(cfg["allowed_metallurgy"])
    carbon_steel_families = set(cfg["carbon_steel_families"])

    _validate_inputs(
        metallurgy_family,
        operating_temperature,
        min_operating_temperature,
        max_operating_temperature,
        allowed_metallurgy,
    )

    if metallurgy_family in carbon_steel_families:
        if _is_cyclic_carbon_steel_service(
            min_operating_temperature,
            max_operating_temperature,
            avg_cycles_per_quarter,
            cfg["cyclic_max_temp_above_c"],
            cfg["cyclic_min_temp_below_c"],
        ):
            return 5
        return _score_carbon_steel_buckets(operating_temperature, cfg)

    # Austenitic / duplex stainless (validated above)
    return _score_stainless_steel_buckets(operating_temperature, cfg)
