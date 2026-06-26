"""CLI for the dataset production pipeline.

Usage:
    python -m lean_virtual_sensor.dataset                        run all datasets
    python -m lean_virtual_sensor.dataset baseline_1k            run one dataset
    python -m lean_virtual_sensor.dataset --force                re-run all steps
    python -m lean_virtual_sensor.dataset baseline_1k --force    re-run one dataset
    python -m lean_virtual_sensor.dataset --list                 list defined datasets
"""

import argparse
import logging
import sys

from lean_virtual_sensor.dataset.configs import ALL_CONFIGS
from lean_virtual_sensor.dataset.pipeline import run_all_configs, run_dataset_pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m lean_virtual_sensor.dataset",
        description="Produce datasets from registered configs (generate → featurise → llm_score).",
    )
    parser.add_argument(
        "config",
        nargs="?",
        metavar="CONFIG",
        help="Dataset name to run (default: all). Use --list to see available datasets.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run all steps even if outputs already exist.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List defined datasets and exit.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable DEBUG logging.")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    if args.list:
        print("Available datasets:")
        for name in ALL_CONFIGS:
            print(f"  {name}")
        return 0

    if args.config is not None:
        if args.config not in ALL_CONFIGS:
            print(f"Unknown dataset '{args.config}'. Use --list to see available datasets.")
            return 1
        run_dataset_pipeline(ALL_CONFIGS[args.config], force=args.force)
    else:
        run_all_configs(force=args.force)

    return 0


if __name__ == "__main__":
    sys.exit(main())
