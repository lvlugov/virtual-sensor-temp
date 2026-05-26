"""API 583 CUI risk — heat-tracing scorer.

Maps the asset's heat-tracing system to a 0–5 CUI-likelihood score.
CorrosionRadar refinement of API 583 Annex A's heat-tracing parameter:
steam tracing is split into integrity tiers (HIGH/MEDIUM/POOR) instead
of the standard's binary active/failed dimension, so a deteriorating
steam loop scores progressively higher without needing a separate
operational-state input. Electric and hot-oil tracing keep a single
score — neither presents the leak-mode CUI mechanism that drove the
original failed-steam escalation.

Missing tracing data (``None``) is silently treated as ``"NONE"``.

The allowed tracing-system values and their scores live in
``api_583_risk/config.yaml``.
"""

from __future__ import annotations

from lean_virtual_sensor.feature_engineering.api_583_risk._config import (
    load_api_583_section,
)

CONFIG_SUBSECTION = "heat_tracing"
REQUIRED_KEYS = ("allowed", "score")


def score_heat_tracing(tracing_system: str | None) -> int:
    """Score the heat-tracing system per the config score table.

    Args:
        tracing_system: One of the values listed under
            ``heat_tracing.allowed`` in ``api_583_risk/config.yaml``,
            or ``None`` (treated as ``"NONE"``).

    Returns:
        CUI-likelihood score from the ``heat_tracing.score`` table in
        ``api_583_risk/config.yaml``.

    Raises:
        ValueError: If ``tracing_system`` is non-null but outside the
            allowed set.
    """
    cfg = load_api_583_section(CONFIG_SUBSECTION, REQUIRED_KEYS)
    if tracing_system is None:
        tracing_system = "NONE"
    if tracing_system not in set(cfg["allowed"]):
        raise ValueError(f"Bad tracing_system: {tracing_system}")
    return cfg["score"][tracing_system]
