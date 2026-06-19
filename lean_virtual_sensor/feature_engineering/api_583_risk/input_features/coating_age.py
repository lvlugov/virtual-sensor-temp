"""API 583 CUI risk — coating-age scorer.

Maps coating-system class plus pre-computed ages (coating age and
insulation-system age, in years) to a 0–5 CUI-likelihood score per API
583 Annex A. Quality coatings (TSA, IOZ, multi-coat high-temperature
epoxy) tolerate higher ages than General coatings (single-coat
high-temperature epoxy). Bare substrates and unknown coatings score the
maximum. Insulation-system age provides a class-independent escalation
once it exceeds the system_mid threshold.

All thresholds, allowed enums, the legacy-code list, and the
coating → class mapping live in ``api_583_risk/config.yaml``.
"""

from __future__ import annotations

from lean_virtual_sensor.feature_engineering.api_583_risk._config import (
    load_api_583_section,
)

CONFIG_SUBSECTION = "coating_age"
REQUIRED_KEYS = (
    "allowed",
    "legacy",
    "class",
    "quality_low_max_age",
    "quality_mid_max_age",
    "general_max_age",
    "system_low_max_age",
    "system_mid_max_age",
)


# ====================================== Step helpers ======================================


def _validate_inputs(
    coating_system: str,
    coating_age_years: float | None,
    system_age_years: float | None,
    allowed: set[str],
) -> None:
    """Reject unknown coatings and negative ages."""
    if coating_system not in allowed:
        raise ValueError(f"Unknown coating_system: {coating_system}")
    if coating_age_years is not None and coating_age_years < 0:
        raise ValueError("coating_age_years is negative")
    if system_age_years is not None and system_age_years < 0:
        raise ValueError("system_age_years is negative")


def _score_5_rules(
    api583_class: str,
    coating_age_years: float | None,
    system_age_years: float | None,
    cfg: dict,
) -> int | None:
    """Hard escalations to score 5 (unknown/bare class, ancient system,
    old General coating)."""
    if api583_class == "UNKNOWN":
        return 5
    if api583_class == "BARE":
        return 5
    if system_age_years is not None and system_age_years >= cfg["system_mid_max_age"]:
        return 5
    if (
        api583_class == "General"
        and coating_age_years is not None
        and coating_age_years > cfg["general_max_age"]
    ):
        return 5
    return None


def _score_0_rules(
    api583_class: str,
    coating_age_years: float | None,
    system_age_years: float | None,
    cfg: dict,
) -> int | None:
    """Score 0: new Quality coating or recently installed system."""
    if (
        api583_class == "Quality"
        and coating_age_years is not None
        and coating_age_years < cfg["quality_low_max_age"]
    ):
        return 0
    if system_age_years is not None and system_age_years < cfg["system_low_max_age"]:
        return 0
    return None


def _score_1_rules(
    api583_class: str,
    coating_age_years: float | None,
    system_age_years: float | None,
    cfg: dict,
) -> int | None:
    """Score 1: mid-life Quality coating or mid-life system."""
    if (
        api583_class == "Quality"
        and coating_age_years is not None
        and cfg["quality_low_max_age"] <= coating_age_years < cfg["quality_mid_max_age"]
    ):
        return 1
    if (
        system_age_years is not None
        and cfg["system_low_max_age"] <= system_age_years < cfg["system_mid_max_age"]
    ):
        return 1
    return None


def _score_3_rules(
    api583_class: str,
    coating_age_years: float | None,
    cfg: dict,
) -> int | None:
    """Score 3: General coating with age data (no system-age rule above fired)."""
    if api583_class != "General" or coating_age_years is None:
        return None
    if cfg["quality_low_max_age"] <= coating_age_years <= cfg["general_max_age"]:
        return 3
    if coating_age_years < cfg["quality_low_max_age"]:
        return 3
    return None


# ====================================== Public entry point ======================================


def score_coating_age(
    coating_system: str,
    coating_age_years: float | None,
    system_age_years: float | None,
) -> int:
    """Score coating and system age against API 583 Annex A.

    Rules are checked top-to-bottom in the order specified by the
    standard: score 5 escalations first, then 0, 1, and 3 in turn, then
    the conservative 5 fallback. The first matching rule wins.

    Args:
        coating_system: One of the values listed under
            ``coating_age.allowed`` in ``api_583_risk/config.yaml``.
            Legacy codes from ``coating_age.legacy`` are silently mapped
            to ``"UNKNOWN"``.
        coating_age_years: Age of the current coating in years, or
            ``None`` if unknown.
        system_age_years: Age of the insulation system in years, or
            ``None`` if unknown.

    Returns:
        CUI-likelihood score in ``{0, 1, 3, 5}``. Higher scores mean
        higher CUI risk; missing or unmatched data defaults to 5.

    Raises:
        ValueError: If ``coating_system`` is unknown or either age is
            negative.
    """
    cfg = load_api_583_section(CONFIG_SUBSECTION, REQUIRED_KEYS)
    allowed = set(cfg["allowed"])
    legacy = set(cfg["legacy"])
    class_map: dict[str, str] = cfg["class"]

    if coating_system in legacy:
        coating_system = "UNKNOWN"
    _validate_inputs(coating_system, coating_age_years, system_age_years, allowed)

    api583_class = class_map[coating_system]

    score = _score_5_rules(api583_class, coating_age_years, system_age_years, cfg)
    if score is not None:
        return score
    score = _score_0_rules(api583_class, coating_age_years, system_age_years, cfg)
    if score is not None:
        return score
    score = _score_1_rules(api583_class, coating_age_years, system_age_years, cfg)
    if score is not None:
        return score
    score = _score_3_rules(api583_class, coating_age_years, cfg)
    if score is not None:
        return score
    return 5
