"""Unit tests for inputs_generation.schema_loader (no generated CSV required)."""

from __future__ import annotations

import shutil
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

_CONFIG_FILENAMES = (
    "schema.yaml",
    "asset_class_config.yaml",
    "conditional_rules.yaml",
    "generation_config.yaml",
    "operating_temperature_config.yaml",
)


def _copy_repo_configs(dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    for name in _CONFIG_FILENAMES:
        shutil.copy(CONFIG_DIR / name, dest_dir / name)


def test_load_all_configs_default_generation_path() -> None:
    cfg = load_all_configs(CONFIG_DIR)
    assert isinstance(cfg, GeneratorConfig)
    assert "variables" in cfg.schema
    assert "PIPE" in cfg.asset_class
    assert "conditional_weights" in cfg.conditional_rules
    assert cfg.generation["run"]["n_rows"] == 1000
    assert cfg.operating_temperature["wide_swing_fraction"] == 0.05
    assert "PIPE" in cfg.operating_temperature["profiles"]
    assert cfg.operating_temperature["asset_class_default_profile"]["REACTOR"] == "REACTOR"


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
    d = tmp_path / "cfg"
    _copy_repo_configs(d)
    (d / "generation_config.yaml").write_text(
        bad.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="asset_class_proportions sum"):
        load_all_configs(d)


def test_deterministic_rules_must_be_generation_scoped(tmp_path: Path) -> None:
    """Downstream-only rules must not live under deterministic_rules in YAML."""
    d = tmp_path / "cfg"
    _copy_repo_configs(d)

    text = (CONFIG_DIR / "conditional_rules.yaml").read_text(encoding="utf-8")
    text = text.replace(
        "    id: R-CHLORIDE-01\n    applies_at: generation",
        "    id: R-CHLORIDE-01\n    applies_at: downstream",
    )
    (d / "conditional_rules.yaml").write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match="applies_at must be 'generation'"):
        load_all_configs(d)


def test_repo_conditional_rules_has_generation_only_deterministic_rules() -> None:
    """Guardrail: repo config must not reintroduce downstream Tier 1 blocks."""
    cfg = load_all_configs(CONFIG_DIR)
    blocks = cfg.conditional_rules.get("deterministic_rules", {})
    assert isinstance(blocks, dict)
    assert "coating_system_age_degradation" not in blocks
    for name, block in blocks.items():
        assert block.get("applies_at") == "generation", name


def test_repo_conditional_rules_rule_ids_are_unique() -> None:
    """Every generation rule block in conditional_rules.yaml has a unique id."""
    cfg = load_all_configs(CONFIG_DIR)
    ids: list[str] = []
    for section in ("deterministic_rules", "conditional_weights", "geometry_standards"):
        blocks = cfg.conditional_rules.get(section, {})
        assert isinstance(blocks, dict)
        for block in blocks.values():
            rule_id = block.get("id")
            assert isinstance(rule_id, str) and rule_id.startswith("R-")
            ids.append(rule_id)
    assert len(ids) == len(set(ids))
    assert "R-CHLORIDE-01" in ids
    assert "R-INSMAT-W-01" in ids


def test_missing_rule_id_raises(tmp_path: Path) -> None:
    d = tmp_path / "cfg"
    _copy_repo_configs(d)

    text = (CONFIG_DIR / "conditional_rules.yaml").read_text(encoding="utf-8")
    text = text.replace("    id: R-CHLORIDE-01\n", "")
    (d / "conditional_rules.yaml").write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match="missing required id"):
        load_all_configs(d)


def test_operating_temperature_triangular_mode_out_of_range_raises(tmp_path: Path) -> None:
    d = tmp_path / "cfg"
    _copy_repo_configs(d)

    text = (CONFIG_DIR / "operating_temperature_config.yaml").read_text(encoding="utf-8")
    text = text.replace("mode: 100", "mode: 500", 1)
    (d / "operating_temperature_config.yaml").write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match="min <= mode <= max"):
        load_all_configs(d)


def test_operating_temperature_unknown_default_profile_raises(tmp_path: Path) -> None:
    d = tmp_path / "cfg"
    _copy_repo_configs(d)

    text = (CONFIG_DIR / "operating_temperature_config.yaml").read_text(encoding="utf-8")
    text = text.replace("PIPE: PIPE", "PIPE: NOT_A_PROFILE")
    (d / "operating_temperature_config.yaml").write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match="unknown profile"):
        load_all_configs(d)


def test_operating_temperature_wide_swing_fraction_out_of_range_raises(tmp_path: Path) -> None:
    d = tmp_path / "cfg"
    _copy_repo_configs(d)

    text = (CONFIG_DIR / "operating_temperature_config.yaml").read_text(encoding="utf-8")
    text = text.replace("wide_swing_fraction: 0.05", "wide_swing_fraction: 1.5")
    (d / "operating_temperature_config.yaml").write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match="wide_swing_fraction"):
        load_all_configs(d)
