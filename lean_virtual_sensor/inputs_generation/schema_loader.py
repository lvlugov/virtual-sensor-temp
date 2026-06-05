"""
schema_loader.py
================
Loads and validates all four config files into structured Python objects.
All other inputs_generation modules import from here — they never read YAML directly.

Exposes:
    load_all_configs(config_dir, generation_config_path=...) -> GeneratorConfig
        Loads and cross-validates schema.yaml, asset_class_config.yaml,
        conditional_rules.yaml, and generation_config.yaml.

    GeneratorConfig
        Dataclass holding all four config namespaces as typed attributes.

Part 1 (step 3) implements a **minimal** validation set sufficient to run the
pipeline; Part 2 expands checks to the full list in the original design (subset
checks of conditional rule values, exhaustive weight audits, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


_WEIGHT_SUM_TOLERANCE = 0.02


@dataclass
class GeneratorConfig:
    schema: dict[str, Any]
    asset_class: dict[str, Any]
    conditional_rules: dict[str, Any]
    generation: dict[str, Any]


def load_all_configs(
    config_dir: Path,
    *,
    generation_config_path: Path | None = None,
) -> GeneratorConfig:
    """Load and cross-validate all four config files.

    Args:
        config_dir: Directory containing ``schema.yaml``, ``asset_class_config.yaml``,
            and ``conditional_rules.yaml``.
        generation_config_path: Path to ``generation_config.yaml``. Defaults to
            ``config_dir / "generation_config.yaml"``.

    Returns:
        GeneratorConfig with all four configs loaded and validated.

    Raises:
        ValueError: If any cross-validation check fails.
        FileNotFoundError: If any config file is missing.
    """
    config_dir = config_dir.resolve()
    if not config_dir.is_dir():
        raise FileNotFoundError(f"Config directory not found: {config_dir}")

    gen_path = (generation_config_path or (config_dir / "generation_config.yaml")).resolve()
    paths = {
        "schema": config_dir / "schema.yaml",
        "asset_class": config_dir / "asset_class_config.yaml",
        "conditional_rules": config_dir / "conditional_rules.yaml",
        "generation": gen_path,
    }
    for label, path in paths.items():
        if not path.is_file():
            raise FileNotFoundError(f"Missing {label} config: {path}")

    config = GeneratorConfig(
        schema=_load_yaml(paths["schema"]),
        asset_class=_load_yaml(paths["asset_class"]),
        conditional_rules=_load_yaml(paths["conditional_rules"]),
        generation=_load_yaml(paths["generation"]),
    )
    _validate_configs(config)
    return config


def _load_yaml(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        raise ValueError(f"Config is empty or null: {path}")
    if not isinstance(data, dict):
        raise ValueError(f"Config root must be a mapping: {path}")
    return data


def _validate_configs(config: GeneratorConfig) -> None:
    """Run cross-validation checks. Raises ValueError on failure."""
    variables = config.schema.get("variables")
    if not isinstance(variables, dict) or not variables:
        raise ValueError("schema.yaml must define a non-empty 'variables' mapping")

    gen = config.generation
    run = gen.get("run")
    if not isinstance(run, dict):
        raise ValueError("generation_config.yaml must contain a 'run' mapping")
    n_rows = int(run["n_rows"])

    props = gen.get("asset_class_proportions")
    if not isinstance(props, dict) or not props:
        raise ValueError("generation_config.yaml must define 'asset_class_proportions'")
    total = sum(int(v) for v in props.values())
    if total != n_rows:
        raise ValueError(
            f"asset_class_proportions sum ({total}) must equal run.n_rows ({n_rows})"
        )

    for ac in props:
        if ac not in config.asset_class:
            raise ValueError(
                f"asset_class_proportions key {ac!r} has no entry in asset_class_config.yaml"
            )

    ez = gen.get("exposure_zone_weights")
    if isinstance(ez, dict) and ez:
        _assert_weights_sum("exposure_zone_weights", ez, _WEIGHT_SUM_TOLERANCE)

    cg = gen.get("cycling_grade_weights")
    if isinstance(cg, dict) and cg:
        _assert_weights_sum("cycling_grade_weights", cg, _WEIGHT_SUM_TOLERANCE)

    cw = config.conditional_rules.get("conditional_weights")
    if isinstance(cw, dict):
        for var_name in cw:
            if var_name not in variables:
                raise ValueError(
                    f"conditional_weights key {var_name!r} is not a variable in schema.yaml"
                )

    for class_name, class_cfg in config.asset_class.items():
        if not isinstance(class_cfg, dict):
            continue
        for key in (
            "geometry_class_weights",
            "orientation_weights",
            "geometry_complexity_weights",
        ):
            w = class_cfg.get(key)
            if isinstance(w, dict) and w:
                _assert_weights_sum(
                    f"asset_class_config[{class_name}].{key}",
                    w,
                    _WEIGHT_SUM_TOLERANCE,
                )

    _validate_deterministic_rules(config.conditional_rules)


def _validate_deterministic_rules(conditional_rules: dict[str, Any]) -> None:
    """Ensure Tier 1 blocks in conditional_rules.yaml are generation-scoped only."""
    blocks = conditional_rules.get("deterministic_rules")
    if not isinstance(blocks, dict):
        return
    for rule_name, block in blocks.items():
        if not isinstance(block, dict):
            raise ValueError(
                f"deterministic_rules.{rule_name} must be a mapping, got {type(block).__name__}"
            )
        applies_at = block.get("applies_at")
        if applies_at != "generation":
            raise ValueError(
                f"deterministic_rules.{rule_name}.applies_at must be 'generation' "
                f"(got {applies_at!r}). Downstream rules belong in "
                "docs/downstream_product_semantics.md, not conditional_rules.yaml."
            )


def _assert_weights_sum(label: str, weights: dict[str, Any], tol: float) -> None:
    s = sum(float(v) for v in weights.values())
    if abs(s - 1.0) > tol:
        raise ValueError(f"{label} weights sum to {s:.6f}, expected 1.0 (tol={tol})")
