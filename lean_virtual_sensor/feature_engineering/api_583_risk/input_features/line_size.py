"""API 583 CUI risk — line/nozzle-size scorer.

Maps the asset class and, for piping, the outer diameter to a 0–5
CUI-likelihood score per API 583 Annex A.

Equipment classes (pressure vessels, heat exchangers, air coolers,
storage tanks) score 0 — their nozzles are short-circuited.

Piping is bucketed by ASME B36.10 outer diameter:
- ``> 6 in. NPS`` (OD > 168.3 mm) → 1
- ``> 2 in. to 6 in. NPS`` (60.3 < OD ≤ 168.3 mm) → 3
- ``≤ 2 in. NPS`` (OD ≤ 60.3 mm) → 5

``asset_class`` is required; ``component_diameter`` is required only
when ``asset_class == "PIPE"`` and is ignored otherwise.

Allowed asset classes, the equipment subset, and the two OD thresholds
live in ``api_583_risk/config.yaml``.
"""

from __future__ import annotations

from lean_virtual_sensor.feature_engineering.api_583_risk._config import (
    load_api_583_section,
)

CONFIG_SUBSECTION = "line_size"
REQUIRED_KEYS = (
    "allowed_asset_class",
    "equipment_classes",
    "od_2in_nps_mm",
    "od_6in_nps_mm",
)


# ====================================== Step helpers ======================================


def _validate_inputs(
    asset_class: str | None,
    component_diameter: float | None,
    allowed_asset_class: set[str],
) -> None:
    """Reject missing/unknown asset class and non-positive diameter."""
    if asset_class is None:
        raise ValueError("asset_class is required")
    if asset_class not in allowed_asset_class:
        raise ValueError(f"Bad asset_class: {asset_class}")
    if component_diameter is not None and component_diameter <= 0:
        raise ValueError(f"component_diameter must be > 0, got {component_diameter}")


def _score_pipe_diameter(
    component_diameter: float,
    od_2in_nps_mm: float,
    od_6in_nps_mm: float,
) -> int:
    """Pipe OD bucket: 1 (>6 in. NPS), 3 (>2 to 6 in. NPS), 5 (≤2 in. NPS)."""
    if component_diameter > od_6in_nps_mm:
        return 1
    if component_diameter > od_2in_nps_mm:
        return 3
    return 5


# ====================================== Public entry point ======================================


def score_line_size(
    asset_class: str | None,
    component_diameter: float | None,
) -> int:
    """Score line/nozzle size against API 583 Annex A.

    Args:
        asset_class: One of the values listed under
            ``line_size.allowed_asset_class`` in ``api_583_risk/config.yaml``.
            Required.
        component_diameter: Outer diameter in millimetres. Required
            when ``asset_class == "PIPE"``; ignored for equipment
            classes.

    Returns:
        CUI-likelihood score in ``{0, 1, 3, 5}``. Equipment classes
        always return 0; pipe diameter buckets return 1, 3, or 5.

    Raises:
        ValueError: If ``asset_class`` is missing or unknown, if
            ``component_diameter`` is non-positive, or if a pipe is
            missing its diameter.
    """
    cfg = load_api_583_section(CONFIG_SUBSECTION, REQUIRED_KEYS)
    allowed_asset_class = set(cfg["allowed_asset_class"])
    equipment_classes = set(cfg["equipment_classes"])

    _validate_inputs(asset_class, component_diameter, allowed_asset_class)

    # Equipment classes — nozzle size short-circuits to 0.
    if asset_class in equipment_classes:
        return 0

    # PIPE: diameter required.
    if component_diameter is None:
        raise ValueError("component_diameter is required for asset_class = PIPE")
    return _score_pipe_diameter(component_diameter, cfg["od_2in_nps_mm"], cfg["od_6in_nps_mm"])
