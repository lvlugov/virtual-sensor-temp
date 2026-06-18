"""Age features derived from date inputs in the fleet inventory.

Converts raw date fields (``coating_application_date``,
``insulation_install_date``, ...) into the integer "years elapsed"
values that downstream scorers consume — for example, the API 583
coating-age and jacketing-insulation scorers take ``coating_age_years``
and ``system_age_years`` rather than the raw dates themselves.

Centralised here so the date → age derivation lives in one place and
the scorers stay agnostic to whether the caller has raw dates or
pre-computed ages.

The orchestrator (the future ``feature_pipeline.compute_features_for_asset``)
will call this on every model run, because age depends on ``today`` and
drifts as time passes — the value is deliberately not cached.
"""

from __future__ import annotations

import pandas as pd

DAYS_PER_YEAR = 365


def compute_age_years(date: pd.Timestamp, today: pd.Timestamp) -> int:
    """Whole years elapsed between ``date`` and ``today``, floored.

    Args:
        date: A past date — typically ``coating_application_date`` (for
            ``coating_age_years``) or ``insulation_install_date`` (for
            ``system_age_years``).
        today: Reference date for the model run.

    Returns:
        Elapsed time as an integer number of whole years
        (``(today - date).days // 365``). Returns ``0`` for any
        ``date`` within the year preceding ``today``.

    Raises:
        ValueError: If ``date`` is later than ``today``. A negative age
            almost always means a swapped argument order or a typo
            upstream, not a real signal worth propagating.
    """
    if date > today:
        raise ValueError(f"date {date} is later than today {today} — age would be negative")
    return (today - date).days // DAYS_PER_YEAR
