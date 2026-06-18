"""
Shared pytest fixtures for the synthetic dataset test suite.

The test suite is designed to run against ANY dataset CSV, not just the
synthetic one. Pass the target dataset via the --dataset CLI option::

    pytest tests/ --dataset \\
        lean_virtual_sensor/inputs_generation/config/outputs/synthetic_v1.0_seed42.csv

Or generate a fresh dataset and run all tests without saving it::

    make test-dataset

If --dataset is not provided, data-dependent tests skip.
Configs are loaded from ``lean_virtual_sensor/inputs_generation/config/``.

Fixtures provided:
    dataset_path  : Path to the CSV under test (from --dataset)
    df            : Loaded DataFrame
    schema        : Parsed schema.yaml
    asset_config  : Parsed asset_class_config.yaml
    gen_config    : Parsed generation_config.yaml (None if file missing)
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "lean_virtual_sensor" / "inputs_generation" / "config"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--dataset",
        action="store",
        default=None,
        help="Path to the CSV dataset to validate",
    )


@pytest.fixture(scope="session")
def dataset_path(request: pytest.FixtureRequest) -> Path | None:
    val = request.config.getoption("--dataset")
    return Path(val) if val else None


@pytest.fixture(scope="session")
def df(dataset_path: Path | None) -> pd.DataFrame | None:
    if dataset_path is None:
        return None
    return pd.read_csv(dataset_path)


@pytest.fixture(scope="session")
def schema() -> dict:
    with open(CONFIG_DIR / "schema.yaml") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="session")
def asset_config() -> dict:
    with open(CONFIG_DIR / "asset_class_config.yaml") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="session")
def gen_config() -> dict | None:
    path = CONFIG_DIR / "generation_config.yaml"
    if not path.exists():
        return None
    with open(path) as f:
        return yaml.safe_load(f)
