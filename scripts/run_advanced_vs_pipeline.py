#!/usr/bin/env python3
"""End-to-end driver: asset_similarity → water_factor → risk_calc."""

from __future__ import annotations

import advanced_virtual_sensor.asset_similarity
import advanced_virtual_sensor.risk_calc
import advanced_virtual_sensor.water_factor


def run_pipeline() -> None:
    """Run the pipeline in order. Implementations are added per component."""
    _ = (
        advanced_virtual_sensor.asset_similarity,
        advanced_virtual_sensor.water_factor,
        advanced_virtual_sensor.risk_calc,
    )


def main() -> None:
    run_pipeline()


if __name__ == "__main__":
    main()
