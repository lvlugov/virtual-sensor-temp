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


def test_deterministic_rules_must_be_generation_scoped(tmp_path: Path) -> None:
    """Downstream-only rules must not live under deterministic_rules in YAML."""
    import shutil

    d = tmp_path / "cfg"
    d.mkdir()
    shutil.copy(CONFIG_DIR / "schema.yaml", d / "schema.yaml")
    shutil.copy(CONFIG_DIR / "asset_class_config.yaml", d / "asset_class_config.yaml")
    shutil.copy(CONFIG_DIR / "generation_config.yaml", d / "generation_config.yaml")

    bad_rules = CONFIG_DIR / "conditional_rules.yaml"
    text = bad_rules.read_text(encoding="utf-8")
    text = text.replace(
        "insulation_chloride_flag:\n    applies_at: generation",
        "insulation_chloride_flag:\n    applies_at: scoring",
    )
    (d / "conditional_rules.yaml").write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match="applies_at must be 'generation'"):
        load_all_configs(d)


def test_repo_conditional_rules_has_generation_only_deterministic_rules() -> None:
    """Guardrail: repo config must not reintroduce scoring-time Tier 1 blocks."""
    cfg = load_all_configs(CONFIG_DIR)
    blocks = cfg.conditional_rules.get("deterministic_rules", {})
    assert isinstance(blocks, dict)
    assert "coating_system_age_degradation" not in blocks
    for name, block in blocks.items():
        assert block.get("applies_at") == "generation", name
