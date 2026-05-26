"""API 583 CUI risk — external-environment scorer.

Maps the asset's exposure zone (MARINE / TEMPERATE / ARID), local
shelter condition (PROTECTED / NORMAL / DAMAGED), and an explicit
``sweating_asset`` flag to a 0–5 CUI-likelihood score per API 583
Annex A.

Cascade (top-to-bottom, first match wins):
1. ``sweating_asset is False`` → 0 (no sweating mechanism present;
   CUI cannot develop on this asset regardless of exposure).
2. ``shelter_flag == "DAMAGED"`` → 5 (local water source).
3. ``exposure_zone == "MARINE"`` → 5 (coastal corrosivity).
4. ``exposure_zone == "ARID"`` → 1 (arid inland).
5. ``exposure_zone == "TEMPERATE"`` → 3 (catch-all).

Missing categorical inputs are silently defaulted to ``"TEMPERATE"``
and ``"NORMAL"`` respectively; ``sweating_asset = None`` is treated as
``True`` (conservative — assume the asset can sweat until proven
otherwise).

``sweating_asset`` replaces the earlier ``ach_90d == 0`` escape: an
explicit per-asset attribute rather than a derived signal from the
asset_temperature module, so the API 583 risk layer no longer depends
on ACH.

Allowed exposure and shelter values live in ``api_583_risk/config.yaml``.
"""

from __future__ import annotations

from lean_virtual_sensor.feature_engineering.api_583_risk._config import (
    load_api_583_section,
)

CONFIG_SUBSECTION = "external_environment"
REQUIRED_KEYS = ("allowed_exposure", "allowed_shelter")


def score_external_environment(
    exposure_zone: str | None,
    shelter_flag: str | None,
    sweating_asset: bool | None,
) -> int:
    """Score external environment against API 583 Annex A.

    Args:
        exposure_zone: One of the values listed under
            ``external_environment.allowed_exposure`` in
            ``api_583_risk/config.yaml``, or ``None`` (treated as
            ``"TEMPERATE"``).
        shelter_flag: One of the values listed under
            ``external_environment.allowed_shelter``, or ``None``
            (treated as ``"NORMAL"``).
        sweating_asset: ``True`` when the asset can experience surface
            condensation / wetting under its operating envelope,
            ``False`` when it physically cannot, ``None`` if unknown
            (treated as ``True`` — conservative). Only consulted by the
            score-0 escape hatch.

    Returns:
        CUI-likelihood score in ``{0, 1, 3, 5}``.

    Raises:
        ValueError: If ``exposure_zone`` or ``shelter_flag`` is non-null
            but outside the allowed set.
    """
    cfg = load_api_583_section(CONFIG_SUBSECTION, REQUIRED_KEYS)

    if exposure_zone is None:
        exposure_zone = "TEMPERATE"
    if shelter_flag is None:
        shelter_flag = "NORMAL"

    if exposure_zone not in set(cfg["allowed_exposure"]):
        raise ValueError(f"Bad exposure_zone: {exposure_zone}")
    if shelter_flag not in set(cfg["allowed_shelter"]):
        raise ValueError(f"Bad shelter_flag: {shelter_flag}")

    # Score 0: asset physically cannot sweat → no CUI mechanism.
    if sweating_asset is False:
        return 0

    # Score 5: damaged shelter introduces a local water source.
    if shelter_flag == "DAMAGED":
        return 5

    # Score 5 / 1 / 3: dispatch on exposure zone.
    if exposure_zone == "MARINE":
        return 5
    if exposure_zone == "ARID":
        return 1
    return 3  # TEMPERATE — catch-all
