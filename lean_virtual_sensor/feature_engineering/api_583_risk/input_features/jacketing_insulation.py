"""API 583 CUI risk — jacketing/insulation-condition scorer.

Maps the cladding-integrity rating, the insulation-condition rating
(each ABOVE_AVERAGE / AVERAGE / BELOW_AVERAGE), and the
insulation-system age to a 0–5 CUI-likelihood score per API 583 Annex A.

The worst of the two ratings drives the cascade:
``BELOW_AVERAGE`` → 5, ``AVERAGE`` → 3, ``ABOVE_AVERAGE`` → 1. A new
system (younger than ``new_system_max_age``) with both ratings
``ABOVE_AVERAGE`` drops to 0. Missing condition ratings are treated as
``AVERAGE`` (conservative default).

Allowed condition ratings and the new-system age threshold live in
``api_583_risk/config.yaml``.
"""

from __future__ import annotations

from lean_virtual_sensor.feature_engineering.api_583_risk._config import (
    load_api_583_section,
)

CONFIG_SUBSECTION = "jacketing_insulation"
REQUIRED_KEYS = ("allowed", "new_system_max_age")


# ====================================== Step helpers ======================================


def _validate_inputs(
    cladding_integrity: str,
    insulation_condition: str,
    system_age_years: float | None,
    allowed: set[str],
) -> None:
    """Reject unknown condition ratings and negative system age."""
    if cladding_integrity not in allowed:
        raise ValueError(f"Bad cladding_integrity: {cladding_integrity}")
    if insulation_condition not in allowed:
        raise ValueError(f"Bad insulation_condition: {insulation_condition}")
    if system_age_years is not None and system_age_years < 0:
        raise ValueError("system_age_years is negative")


def _worse_of_two_conditions(
    cladding_integrity: str,
    insulation_condition: str,
) -> str:
    """Return the worse of the two ratings.

    Ordering (worst → best): ``BELOW_AVERAGE`` > ``AVERAGE`` >
    ``ABOVE_AVERAGE``.
    """
    ratings = (cladding_integrity, insulation_condition)
    if "BELOW_AVERAGE" in ratings:
        return "BELOW_AVERAGE"
    if "AVERAGE" in ratings:
        return "AVERAGE"
    return "ABOVE_AVERAGE"


def _is_new_system_with_above_average_ratings(
    cladding_integrity: str,
    insulation_condition: str,
    system_age_years: float | None,
    new_system_max_age: float,
) -> bool:
    """True when the system is younger than ``new_system_max_age`` and
    both ratings are ABOVE_AVERAGE."""
    return (
        system_age_years is not None
        and system_age_years < new_system_max_age
        and cladding_integrity == "ABOVE_AVERAGE"
        and insulation_condition == "ABOVE_AVERAGE"
    )


# ====================================== Public entry point ======================================


def score_jacketing_insulation_condition(
    cladding_integrity: str | None,
    insulation_condition: str | None,
    system_age_years: float | None,
) -> int:
    """Score jacketing and insulation condition against API 583 Annex A.

    The worst of the two condition ratings drives the score; an
    ``ABOVE_AVERAGE`` system younger than the configured new-system age
    drops a tier further to 0.

    Args:
        cladding_integrity: One of the values listed under
            ``jacketing_insulation.allowed`` in ``api_583_risk/config.yaml``,
            or ``None`` (treated as ``"AVERAGE"``).
        insulation_condition: Same allowed set as ``cladding_integrity``,
            or ``None`` (treated as ``"AVERAGE"``).
        system_age_years: Age of the insulation system in years, or
            ``None`` if unknown. Only consulted by the score-0 escape
            hatch.

    Returns:
        CUI-likelihood score in ``{0, 1, 3, 5}``. Higher scores mean
        higher CUI risk.

    Raises:
        ValueError: If either rating is non-null but outside the allowed
            set, or if ``system_age_years`` is negative.
    """
    cfg = load_api_583_section(CONFIG_SUBSECTION, REQUIRED_KEYS)
    allowed = set(cfg["allowed"])

    # Default missing ratings to AVERAGE.
    if cladding_integrity is None:
        cladding_integrity = "AVERAGE"
    if insulation_condition is None:
        insulation_condition = "AVERAGE"

    _validate_inputs(cladding_integrity, insulation_condition, system_age_years, allowed)

    # Score 0: new system with no deficiencies on either rating.
    if _is_new_system_with_above_average_ratings(
        cladding_integrity,
        insulation_condition,
        system_age_years,
        cfg["new_system_max_age"],
    ):
        return 0

    # Score 5 / 3 / 1: dispatch on the worse of the two ratings.
    worse = _worse_of_two_conditions(cladding_integrity, insulation_condition)
    if worse == "BELOW_AVERAGE":
        return 5
    if worse == "AVERAGE":
        return 3
    return 1  # both ABOVE_AVERAGE, but system not new enough for score 0
