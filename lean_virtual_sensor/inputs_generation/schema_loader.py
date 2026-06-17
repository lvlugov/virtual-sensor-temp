"""
schema_loader.py
================
Loads and validates all config files into structured Python objects.
All other inputs_generation modules import from here — they never read YAML directly.

Exposes:
    load_all_configs(config_dir, generation_config_path=...) -> GeneratorConfig
        Loads and cross-validates schema.yaml, asset_class_config.yaml,
        conditional_rules.yaml, generation_config.yaml, and
        operating_temperature_config.yaml.

    GeneratorConfig
        Dataclass holding all config namespaces as typed attributes.

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
_COLD_SERVICE_PROFILE_BY_CLASS = {
    "PIPE": "PIPE_COLD_SERVICE",
    "PRESSURE_VESSEL": "PRESSURE_VESSEL_COLD_SERVICE",
    "STORAGE_TANK": "STORAGE_TANK_REFRIGERATED",
}


@dataclass
class GeneratorConfig:
    schema: dict[str, Any]
    asset_class: dict[str, Any]
    conditional_rules: dict[str, Any]
    generation: dict[str, Any]
    operating_temperature: dict[str, Any]


def load_all_configs(
    config_dir: Path,
    *,
    generation_config_path: Path | None = None,
) -> GeneratorConfig:
    """Load and cross-validate all config files.

    Args:
        config_dir: Directory containing ``schema.yaml``, ``asset_class_config.yaml``,
            ``conditional_rules.yaml``, and ``operating_temperature_config.yaml``.
        generation_config_path: Path to ``generation_config.yaml``. Defaults to
            ``config_dir / "generation_config.yaml"``.

    Returns:
        GeneratorConfig with all configs loaded and validated.

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
        "operating_temperature": config_dir / "operating_temperature_config.yaml",
    }
    for label, path in paths.items():
        if not path.is_file():
            raise FileNotFoundError(f"Missing {label} config: {path}")

    config = GeneratorConfig(
        schema=_load_yaml(paths["schema"]),
        asset_class=_load_yaml(paths["asset_class"]),
        conditional_rules=_load_yaml(paths["conditional_rules"]),
        generation=_load_yaml(paths["generation"]),
        operating_temperature=_load_yaml(paths["operating_temperature"]),
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

    _validate_conditional_rules(config.conditional_rules)
    _validate_geometry_config(config)
    _validate_operating_temperature_config(config)


def _validate_geometry_config(config: GeneratorConfig) -> None:
    """Validate PIPE NPS catalog and non-pipe geometry_sampling blocks."""
    pipe_class_cfg = config.asset_class.get("PIPE")
    if not isinstance(pipe_class_cfg, dict):
        raise ValueError("asset_class_config.yaml must define PIPE")

    geometry_standards = config.conditional_rules.get("geometry_standards")
    if not isinstance(geometry_standards, dict):
        raise ValueError("conditional_rules.yaml must define geometry_standards")
    pipe_nps = geometry_standards.get("pipe_nps")
    if not isinstance(pipe_nps, dict):
        raise ValueError("geometry_standards.pipe_nps is required")

    _validate_pipe_nps_catalog(pipe_class_cfg, pipe_nps)

    for class_name, class_cfg in config.asset_class.items():
        if class_name == "PIPE":
            continue
        if not isinstance(class_cfg, dict):
            continue
        _validate_non_pipe_geometry_sampling(class_name, class_cfg)


def _validate_pipe_nps_catalog(pipe_class_cfg: dict[str, Any], pipe_nps: dict[str, Any]) -> None:
    catalog = pipe_nps.get("nps_catalog")
    if not isinstance(catalog, list) or not catalog:
        raise ValueError("geometry_standards.pipe_nps.nps_catalog must be a non-empty list")

    diameter_limits = pipe_class_cfg.get("component_diameter")
    wall_limits = pipe_class_cfg.get("furnished_thickness")
    if not isinstance(diameter_limits, dict) or not isinstance(wall_limits, dict):
        raise ValueError("PIPE must define component_diameter and furnished_thickness bounds")

    diam_min = float(diameter_limits["min"])
    diam_max = float(diameter_limits["max"])
    wall_min = float(wall_limits["min"])
    wall_max = float(wall_limits["max"])

    total_weight = 0.0
    for index, row in enumerate(catalog):
        if not isinstance(row, dict):
            raise ValueError(f"pipe_nps.nps_catalog[{index}] must be a mapping")
        for key in ("od_mm", "wall_mm", "weight"):
            if key not in row:
                raise ValueError(f"pipe_nps.nps_catalog[{index}] missing {key!r}")
        od_mm = float(row["od_mm"])
        wall_mm = float(row["wall_mm"])
        total_weight += float(row["weight"])
        if not (diam_min <= od_mm <= diam_max):
            raise ValueError(
                f"pipe_nps.nps_catalog[{index}] od_mm {od_mm} outside PIPE "
                f"component_diameter [{diam_min}, {diam_max}]"
            )
        if not (wall_min <= wall_mm <= wall_max):
            raise ValueError(
                f"pipe_nps.nps_catalog[{index}] wall_mm {wall_mm} outside PIPE "
                f"furnished_thickness [{wall_min}, {wall_max}]"
            )

    if total_weight <= 0:
        raise ValueError("pipe_nps.nps_catalog weights must sum to a positive value")


def _validate_non_pipe_geometry_sampling(class_name: str, class_cfg: dict[str, Any]) -> None:
    geometry_sampling = class_cfg.get("geometry_sampling")
    if not isinstance(geometry_sampling, dict):
        raise ValueError(f"asset_class_config[{class_name}] missing geometry_sampling block")

    diameter_limits = class_cfg.get("component_diameter")
    if not isinstance(diameter_limits, dict):
        raise ValueError(f"asset_class_config[{class_name}] missing component_diameter")
    if "mode" not in diameter_limits:
        raise ValueError(f"asset_class_config[{class_name}].component_diameter missing mode")

    diam_min = float(diameter_limits["min"])
    diam_max = float(diameter_limits["max"])
    diam_mode = float(diameter_limits["mode"])
    if not (diam_min <= diam_mode <= diam_max):
        raise ValueError(
            f"asset_class_config[{class_name}].component_diameter.mode must lie "
            f"between min and max (got {diam_mode}, range [{diam_min}, {diam_max}])"
        )

    method = geometry_sampling.get("method")
    wall_cfg = geometry_sampling.get("wall")
    if not isinstance(wall_cfg, dict):
        raise ValueError(f"asset_class_config[{class_name}].geometry_sampling missing wall block")

    if method == "triangular_coupled_wall":
        for key in ("t_over_d_min", "t_over_d_max", "clamp_min", "clamp_max"):
            if key not in wall_cfg:
                raise ValueError(
                    f"asset_class_config[{class_name}].geometry_sampling.wall missing {key!r}"
                )
        t_min = float(wall_cfg["t_over_d_min"])
        t_max = float(wall_cfg["t_over_d_max"])
        if t_min <= 0 or t_max < t_min:
            raise ValueError(
                f"asset_class_config[{class_name}] invalid t_over_d band [{t_min}, {t_max}]"
            )
        clamp_min = float(wall_cfg["clamp_min"])
        clamp_max = float(wall_cfg["clamp_max"])
        if clamp_min > clamp_max:
            raise ValueError(
                f"asset_class_config[{class_name}] wall clamp_min must be <= clamp_max"
            )
        return

    if method == "triangular_fixed_wall":
        for key in ("min", "max"):
            if key not in wall_cfg:
                raise ValueError(
                    f"asset_class_config[{class_name}].geometry_sampling.wall missing {key!r}"
                )
        fixed_min = float(wall_cfg["min"])
        fixed_max = float(wall_cfg["max"])
        if fixed_min > fixed_max:
            raise ValueError(
                f"asset_class_config[{class_name}] fixed wall min must be <= max"
            )
        return

    raise ValueError(
        f"asset_class_config[{class_name}].geometry_sampling.method must be "
        f"triangular_coupled_wall or triangular_fixed_wall (got {method!r})"
    )


def _validate_conditional_rules(conditional_rules: dict[str, Any]) -> None:
    """Validate Tier 1 scope and rule IDs in conditional_rules.yaml."""
    _validate_deterministic_rules(conditional_rules)
    _validate_rule_ids(conditional_rules)


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
                "docs/synthetic_inputs_methodology.md §6, not conditional_rules.yaml."
            )
        rules = block.get("rules")
        if not isinstance(rules, list) or not rules:
            raise ValueError(f"deterministic_rules.{rule_name} must define a non-empty rules list")
        for index, rule in enumerate(rules):
            if not isinstance(rule, dict):
                raise ValueError(
                    f"deterministic_rules.{rule_name}.rules[{index}] must be a mapping"
                )
            if rule.get("action") != "set_value":
                raise ValueError(
                    f"deterministic_rules.{rule_name}.rules[{index}] action must be 'set_value'"
                )
            if "value" not in rule:
                raise ValueError(
                    f"deterministic_rules.{rule_name}.rules[{index}] missing 'value'"
                )


def _validate_rule_ids(conditional_rules: dict[str, Any]) -> None:
    """Require unique stable rule IDs on generation rule blocks."""
    seen: set[str] = set()

    def register(rule_id: Any, location: str) -> None:
        if not isinstance(rule_id, str) or not rule_id.strip():
            raise ValueError(f"{location}: missing required id (expected R-... format)")
        if not rule_id.startswith("R-"):
            raise ValueError(f"{location}: id must start with 'R-' (got {rule_id!r})")
        if rule_id in seen:
            raise ValueError(f"Duplicate rule id {rule_id!r} at {location}")
        seen.add(rule_id)

    for section in ("deterministic_rules", "conditional_weights", "geometry_standards"):
        blocks = conditional_rules.get(section)
        if not isinstance(blocks, dict):
            continue
        for block_name, block in blocks.items():
            location = f"{section}.{block_name}"
            if not isinstance(block, dict):
                raise ValueError(f"{location} must be a mapping, got {type(block).__name__}")
            register(block.get("id"), location)


def _validate_operating_temperature_config(config: GeneratorConfig) -> None:
    """Validate operating_temperature_config.yaml structure and cross-references."""
    ot_cfg = config.operating_temperature
    if not isinstance(ot_cfg, dict):
        raise ValueError("operating_temperature_config.yaml root must be a mapping")

    wide_frac = float(ot_cfg.get("wide_swing_fraction", -1))
    if not (0.0 <= wide_frac <= 1.0):
        raise ValueError(
            f"operating_temperature_config.wide_swing_fraction must be in [0, 1] "
            f"(got {wide_frac})"
        )

    max_excursion = float(ot_cfg.get("max_excursion_fraction", -1))
    if max_excursion < 0:
        raise ValueError(
            "operating_temperature_config.max_excursion_fraction must be non-negative"
        )

    cold_fracs = ot_cfg.get("cold_service_fraction")
    if not isinstance(cold_fracs, dict) or not cold_fracs:
        raise ValueError(
            "operating_temperature_config.yaml must define 'cold_service_fraction'"
        )
    for class_name, fraction in cold_fracs.items():
        if class_name not in _COLD_SERVICE_PROFILE_BY_CLASS:
            raise ValueError(
                f"cold_service_fraction key {class_name!r} is not an eligible cold-service class"
            )
        if class_name not in config.asset_class:
            raise ValueError(
                f"cold_service_fraction key {class_name!r} has no entry in asset_class_config.yaml"
            )
        frac = float(fraction)
        if not (0.0 <= frac <= 1.0):
            raise ValueError(
                f"cold_service_fraction[{class_name!r}] must be in [0, 1] (got {frac})"
            )

    default_profiles = ot_cfg.get("asset_class_default_profile")
    if not isinstance(default_profiles, dict) or not default_profiles:
        raise ValueError(
            "operating_temperature_config.yaml must define 'asset_class_default_profile'"
        )

    profiles = ot_cfg.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError("operating_temperature_config.yaml must define 'profiles'")

    if "WIDE_SWING" not in profiles:
        raise ValueError("operating_temperature_config.profiles must include WIDE_SWING")

    for class_name in config.asset_class:
        if class_name not in default_profiles:
            raise ValueError(
                f"asset_class_default_profile missing key for asset class {class_name!r}"
            )

    for class_name, profile_key in default_profiles.items():
        if class_name not in config.asset_class:
            raise ValueError(
                f"asset_class_default_profile key {class_name!r} is not in asset_class_config.yaml"
            )
        if profile_key not in profiles:
            raise ValueError(
                f"asset_class_default_profile[{class_name!r}] references unknown profile "
                f"{profile_key!r}"
            )

    for class_name, profile_key in _COLD_SERVICE_PROFILE_BY_CLASS.items():
        if profile_key not in profiles:
            raise ValueError(
                f"operating_temperature_config.profiles must include {profile_key!r} "
                f"for cold-service class {class_name!r}"
            )

    for profile_key, profile in profiles.items():
        _validate_temperature_profile_block(profile_key, profile)


def _validate_temperature_profile_block(profile_key: str, profile: Any) -> None:
    if not isinstance(profile, dict):
        raise ValueError(f"profiles[{profile_key!r}] must be a mapping")

    op_block = profile.get("operating_temperature")
    if not isinstance(op_block, dict):
        raise ValueError(f"profiles[{profile_key!r}].operating_temperature is required")
    _validate_triangular_block(f"profiles[{profile_key!r}].operating_temperature", op_block)

    min_block = profile.get("min_operating_temperature")
    if not isinstance(min_block, dict):
        raise ValueError(f"profiles[{profile_key!r}].min_operating_temperature is required")
    _validate_min_max_block(
        f"profiles[{profile_key!r}].min_operating_temperature", min_block
    )

    max_block = profile.get("max_operating_temperature")
    if not isinstance(max_block, dict):
        raise ValueError(f"profiles[{profile_key!r}].max_operating_temperature is required")
    _validate_min_max_block(
        f"profiles[{profile_key!r}].max_operating_temperature", max_block
    )

    cycles_block = profile.get("avg_cycles_per_quarter")
    if not isinstance(cycles_block, dict):
        raise ValueError(f"profiles[{profile_key!r}].avg_cycles_per_quarter is required")
    _validate_integer_min_max_block(
        f"profiles[{profile_key!r}].avg_cycles_per_quarter", cycles_block
    )

    fraction_block = profile.get("operation_vs_shutdown_fraction")
    if not isinstance(fraction_block, dict):
        raise ValueError(
            f"profiles[{profile_key!r}].operation_vs_shutdown_fraction is required"
        )
    lo, hi = _validate_min_max_block(
        f"profiles[{profile_key!r}].operation_vs_shutdown_fraction", fraction_block
    )
    if lo < 0.0 or hi > 1.0:
        raise ValueError(
            f"profiles[{profile_key!r}].operation_vs_shutdown_fraction must lie in [0, 1]"
        )


def _validate_triangular_block(label: str, block: dict[str, Any]) -> None:
    for key in ("min", "mode", "max"):
        if key not in block:
            raise ValueError(f"{label} missing {key!r}")
    low = float(block["min"])
    mode = float(block["mode"])
    high = float(block["max"])
    if not (low <= mode <= high):
        raise ValueError(
            f"{label} requires min <= mode <= max (got min={low}, mode={mode}, max={high})"
        )


def _validate_min_max_block(label: str, block: dict[str, Any]) -> tuple[float, float]:
    for key in ("min", "max"):
        if key not in block:
            raise ValueError(f"{label} missing {key!r}")
    low = float(block["min"])
    high = float(block["max"])
    if low > high:
        raise ValueError(f"{label} requires min <= max (got min={low}, max={high})")
    return low, high


def _validate_integer_min_max_block(label: str, block: dict[str, Any]) -> None:
    low, high = _validate_min_max_block(label, block)
    if int(low) != low or int(high) != high:
        raise ValueError(f"{label} min and max must be integers (got {low}, {high})")


def _assert_weights_sum(label: str, weights: dict[str, Any], tol: float) -> None:
    s = sum(float(v) for v in weights.values())
    if abs(s - 1.0) > tol:
        raise ValueError(f"{label} weights sum to {s:.6f}, expected 1.0 (tol={tol})")
