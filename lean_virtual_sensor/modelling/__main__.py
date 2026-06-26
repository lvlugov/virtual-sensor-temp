"""CLI for running modelling experiments via kotsu.

Usage:
    python -m lean_virtual_sensor.modelling                      run all experiments
    python -m lean_virtual_sensor.modelling --force              force re-run all
    python -m lean_virtual_sensor.modelling --force linear-v1.0  force specific model(s)
    python -m lean_virtual_sensor.modelling --list               list registered models
"""

import argparse
import logging
import sys

from lean_virtual_sensor.modelling.models import model_registry
from lean_virtual_sensor.modelling.run import run_experiments


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m lean_virtual_sensor.modelling",
        description="Run model training and validation experiments via kotsu.",
    )
    parser.add_argument(
        "--force",
        nargs="*",
        metavar="MODEL_ID",
        help=(
            "Force re-run. With no arguments: re-runs all models. "
            "With model IDs: re-runs only those models."
        ),
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List registered model IDs and exit.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable DEBUG logging.")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    if args.list:
        print("Registered models:")
        for spec in model_registry.all():
            print(f"  {spec.id}")
        return 0

    # args.force is None (flag absent), [] (--force with no args), or [id, ...] (--force id ...)
    if args.force is None:
        force_rerun = None
    elif len(args.force) == 0:
        force_rerun = "all"
    else:
        force_rerun = args.force

    results_df = run_experiments(force_rerun=force_rerun)
    print(results_df.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
