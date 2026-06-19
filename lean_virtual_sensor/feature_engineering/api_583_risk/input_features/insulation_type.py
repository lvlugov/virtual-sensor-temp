"""API 583 CUI risk — insulation-type scorer.

Maps the insulation material to a 1, 3, or 5 CUI-likelihood score per
API 583 Annex A. Closed-cell or low-wicking materials (foam glass,
expanded perlite) score 1; moderately absorbent materials (calcium
silicate, fibreglass) score 3; high-wicking, legacy, or unknown
materials (standard mineral wool, asbestos, unknown) score 5.

Missing insulation data (``None``) is silently treated as
``"UNKNOWN"`` (conservative default).

The full insulation-material → score mapping lives in
``api_583_risk/config.yaml``; this module reads from it on every call.
"""

from __future__ import annotations

from lean_virtual_sensor.feature_engineering.api_583_risk._config import (
    load_api_583_section,
)

CONFIG_SUBSECTION = "insulation_type"
REQUIRED_KEYS = ("score",)


# ====================================== Step helpers ======================================


def _validate_inputs(insulation_material: str, allowed: set[str]) -> None:
    """Reject unknown insulation materials."""
    if insulation_material not in allowed:
        raise ValueError(f"Bad insulation_material: {insulation_material}")


# ====================================== Public entry point ======================================


def score_insulation_type(insulation_material: str | None) -> int:
    """Score insulation type against API 583 Annex A.

    Args:
        insulation_material: One of the keys in ``insulation_type.score``
            in ``api_583_risk/config.yaml``, or ``None`` (treated as
            ``"UNKNOWN"``).

    Returns:
        CUI-likelihood score in ``{1, 3, 5}`` per the configured lookup.

    Raises:
        ValueError: If ``insulation_material`` is non-null but not in
            the configured lookup.
    """
    cfg = load_api_583_section(CONFIG_SUBSECTION, REQUIRED_KEYS)
    score_lookup: dict[str, int] = cfg["score"]
    allowed = set(score_lookup.keys())

    if insulation_material is None:
        insulation_material = "UNKNOWN"
    _validate_inputs(insulation_material, allowed)
    return score_lookup[insulation_material]
