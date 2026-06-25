#!/usr/bin/env python3
"""CLI entry point for synthetic inputs generation.

Resolves ``generation_config.yaml``, then delegates to ``pipeline.run_pipeline``.
Run from the repository with dependencies installed, typically after::

    cd lean_virtual_sensor/inputs_generation

See ``config/generation_config.yaml`` for run parameters (version, seed, n_rows).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def _inputs_generation_dir() -> Path:
    return Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate synthetic CUI lean virtual sensor input dataset CSV.",
    )
    parser.add_argument(
        "--generation-config",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "Path to generation_config.yaml "
            "(default: ./config/generation_config.yaml next to this script)"
        ),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable DEBUG logging",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=None,
        metavar="PATH",
        help="Override run.output_path from generation_config.yaml",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Do not write output CSV after generation",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    base = _inputs_generation_dir()
    config_path = (args.generation_config or (base / "config" / "generation_config.yaml")).resolve()

    if not config_path.is_file():
        logging.getLogger(__name__).error("Generation config not found: %s", config_path)
        return 1

    # Import after argparse so ``--help`` works without numpy/pandas installed.
    from lean_virtual_sensor.inputs_generation.pipeline import run_pipeline

    ok = run_pipeline(
        config_path,
        output_path_override=args.output_path,
        write_output=not args.no_write,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
