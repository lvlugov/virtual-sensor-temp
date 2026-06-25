# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Data science / model development for the **Lean Virtual Sensor** — a deterministic corrosion-under-insulation (CUI) risk model. Not the production deployment repo. The model computes per-asset feature rows (Active CUI Hours, cooldown cycles, wet load, API 583 risk scores) from synthetic or real asset inventory data plus hourly weather/process data.

## Development environment

All development runs inside Docker. Never install dependencies or run tools on the host directly.

```bash
make build          # build the dev image
make up             # start long-lived container
make shell          # open bash inside it
```

Inside the container, Python and all deps are available. `uv` manages dependencies via `pyproject.toml` / `uv.lock`. To add/change deps: edit `pyproject.toml`, run `uv lock`, then `make build`.

## Commands

```bash
make test           # pytest (dataset-dependent tests skip unless --dataset is passed)
make test-dataset   # generate fresh synthetic CSV → run full suite → discard CSV
make lint           # ruff check
make format         # ruff format + autofix
make sync           # uv sync --extra dev inside Docker
```

Run a single test from inside the container:
```bash
pytest tests/test_feature_engineering/test_asset_temperature.py -k "test_name"
```

Run dataset-dependent tests against a specific CSV:
```bash
pytest tests/ --dataset path/to/dataset.csv
```

## Architecture

Two main packages under `lean_virtual_sensor/`:

### `inputs_generation/` — Synthetic dataset generator
- `generate.py`: CLI entry point (`python -m lean_virtual_sensor.inputs_generation.generate`)
- `pipeline.py`: Orchestrates generation → constraint enforcement → pytest gate → CSV output
- `layer_generators.py`: DAG of column-generation steps (anchors → geometry → wall/insulation → dates → operating → flags → thickness)
- `config/`: YAML configs — `schema.yaml` (column definitions), `generation_config.yaml` (run params, seed, n_rows), `asset_class_config.yaml`, `conditional_rules.yaml`, `operating_temperature_config.yaml`
- All imports are absolute (`from lean_virtual_sensor.inputs_generation.x import ...`); the project is installed as an editable package via `uv sync --extra dev`

### `feature_engineering/` — Per-asset feature derivation
- `feature_pipeline.py`: Wires all feature primitives into one flat dict per asset
- Derived features: `age_features` (coating/system age), `system_flag_feature` (open/closed system), `asset_temperature` (ACH via thermal model + NACE damage curves), `cycle_features` (cooldown cycles via prominence), `historical_weather_feature` (recency-weighted wet load), `external_temperature` (Visual Crossing weather API client)
- `api_583_risk/`: Seven API 583 CUI likelihood parameter scorers + likelihood-band pipeline. Has its own `config.yaml` and `_config.py` loader, separate from the project-wide `config.yaml`

### Config system
- `lean_virtual_sensor/config.yaml`: Project-wide config (thermal constants, NACE curve params, weather API settings, fleet locations, historical weather tuning). Loaded via `lean_virtual_sensor/config.py` → `load_section()`
- `lean_virtual_sensor/feature_engineering/api_583_risk/config.yaml`: API 583–specific thresholds/lookup tables. Loaded via `_config.py` → `load_api_583_section()`
- Config path overridable via `LEAN_VS_CONFIG` env var

### Test structure
- `tests/test_feature_engineering/`: Unit tests for each feature module + `test_api_583_risk/` subdirectory
- `tests/lean_virtual_sensor/inputs_generation/`: Dataset validation tests (schema compliance, distributions, constraints). Many use the `df` fixture which requires `--dataset`
- `tests/conftest.py`: Provides `--dataset` CLI option and session-scoped fixtures (`df`, `schema`, `asset_config`, `gen_config`)

## Conventions

- Python 3.12, ruff for linting/formatting (line length 100, select E/F/I/UP/W)
- DataFrames should have descriptive names (`weather_df`, `process_history_df`), not bare `df` (exception: the `df` test fixture)
- Weather API key via `VISUAL_CROSSING_API_KEY` env var (from `.env`, never committed)
