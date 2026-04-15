#!/usr/bin/env python3
"""End-to-end driver: asset_similarity → water_factor → risk_calc."""

from __future__ import annotations

import virtual_sensor.asset_similarity
import virtual_sensor.risk_calc
import virtual_sensor.water_factor


def run_pipeline() -> None:
    """Run the pipeline in order. Implementations are added per component."""
    _ = (
        virtual_sensor.asset_similarity,
        virtual_sensor.water_factor,
        virtual_sensor.risk_calc,
    )


def main() -> None:
    run_pipeline()


if __name__ == "__main__":
    main()
