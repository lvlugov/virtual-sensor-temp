"""Unit tests for inputs_generation.schema_loader (no generated CSV required)."""

from __future__ import annotations

from pathlib import Path

import pytest

from schema_loader import GeneratorConfig, load_all_configs


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise RuntimeError("Could not locate repository root (pyproject.toml)")


CONFIG_DIR = _repo_root() / "lean_virtual_sensor" / "inputs_generation" / "config"


def test_load_all_configs_default_generation_path() -> None:
    cfg = load_all_configs(CONFIG_DIR)
    assert isinstance(cfg, GeneratorConfig)
    assert "variables" in cfg.schema
    assert "PIPE" in cfg.asset_class
    assert "conditional_weights" in cfg.conditional_rules
    assert cfg.generation["run"]["n_rows"] == 1000


def test_load_all_configs_explicit_generation_path() -> None:
    gen_yaml = CONFIG_DIR / "generation_config.yaml"
    cfg = load_all_configs(CONFIG_DIR, generation_config_path=gen_yaml)
    assert cfg.generation["run"]["random_seed"] == 42


def test_asset_class_proportions_mismatch_raises(tmp_path: Path) -> None:
    bad = tmp_path / "generation_config.yaml"
    bad.write_text(
        """
run:
  n_rows: 10
  random_seed: 1
  version: "0"
  reference_date: "2026-01-01"
  output_path: "out.csv"
  halt_on_test_failure: false
asset_class_proportions:
  PIPE: 5
  OTHER: 4
""",
        encoding="utf-8",
    )
    # copy minimal slices — test only needs generation file + dir for others
    import shutil

    d = tmp_path / "cfg"
    d.mkdir()
    shutil.copy(CONFIG_DIR / "schema.yaml", d / "schema.yaml")
    shutil.copy(CONFIG_DIR / "asset_class_config.yaml", d / "asset_class_config.yaml")
    shutil.copy(CONFIG_DIR / "conditional_rules.yaml", d / "conditional_rules.yaml")
    shutil.copy(bad, d / "generation_config.yaml")

    with pytest.raises(ValueError, match="asset_class_proportions sum"):
        load_all_configs(d)
