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

Four packages under `lean_virtual_sensor/`:

### `inputs_generation/` — Synthetic dataset generator
- `generate.py`: CLI entry point (`python -m lean_virtual_sensor.inputs_generation.generate`)
- `pipeline.py`: Orchestrates generation → constraint enforcement → pytest gate → CSV output
- `generate_timeseries.py`: Generates per-asset process-temperature time-series CSVs (`generate_population_series()`)
- `generate_features.py`: Appends derived features + API 583 total to static dataset (`append_features()`)
- `layer_generators.py`: DAG of column-generation steps (anchors → geometry → wall/insulation → dates → operating → flags → thickness)
- `config/`: YAML configs — `schema.yaml` (column definitions), `generation_config.yaml` (run params, seed, n_rows), `asset_class_config.yaml`, `conditional_rules.yaml`, `operating_temperature_config.yaml`
- All imports are absolute (`from lean_virtual_sensor.inputs_generation.x import ...`); the project is installed as an editable package via `uv sync --extra dev`

### `feature_engineering/` — Per-asset feature derivation
- `feature_pipeline.py`: Wires all feature primitives into one flat dict per asset
- Derived features: `age_features` (coating/system age), `system_flag_feature` (open/closed system), `asset_temperature` (ACH via thermal model + NACE damage curves), `cycle_features` (cooldown cycles via prominence), `historical_weather_feature` (recency-weighted wet load), `external_temperature` (Visual Crossing weather API client)
- `api_583_risk/`: Seven API 583 CUI likelihood parameter scorers + likelihood-band pipeline. Has its own `config.yaml` and `_config.py` loader, separate from the project-wide `config.yaml`

### `dataset/` — End-to-end dataset production pipeline
- `configs.py`: `DatasetConfig` frozen dataclass + named configs (`BASELINE_1K`, `BASELINE_1K_LLM`, `ALL_CONFIGS`)
- `pipeline.py`: `run_dataset_pipeline(config)` — orchestrates all 4 steps with skip-if-exists; `run_all_configs()` iterates all configs
- `featurise.py`: `featurise_inventory()` — wraps `inputs_generation.generate_features.append_features()`; falls back to direct feature pipeline call with empty DataFrames when weather cache is absent
- `llm_scoring.py`: `score_dataset()` — mock scorer (random int 0-100, seeded via `llm_config`); `_build_prompt`/`_call_llm` stubbed for future real LLM implementation

Run order for Phase 1:
1. `generate` → `data/raw_synthetic_inputs/{name}.csv`
2. `gen_timeseries` → `data/timeseries/{name}/` (skipped if weather cache absent)
3. `featurise` → `data/featurised/{name}.csv`
4. `llm_score` → `data/datasets/{name}.csv`

### `modelling/` — Model training and validation (kotsu)
Uses [kotsu](https://github.com/datavaluepeople/kotsu) directly — no wrapper abstractions.
- `models.py`: `SklearnModel` (fit/predict wrapper for sklearn estimators) + `model_registry` with `linear-v1.0` (LinearRegression on 16 numeric feature columns)
- `validations.py`: `KFoldCV` class + `validation_registry` with `kfold-5-v1.0` (5-fold CV on `data/datasets/baseline_1k.csv`, returns mae/rmse/r2)
- `run.py`: `run_experiments()` → `kotsu.run.run()` → `data/results/results.csv`

### Config system
- `lean_virtual_sensor/config.yaml`: Project-wide config (thermal constants, NACE curve params, weather API settings, fleet locations, historical weather tuning). Loaded via `lean_virtual_sensor/config.py` → `load_section()`
- `lean_virtual_sensor/feature_engineering/api_583_risk/config.yaml`: API 583–specific thresholds/lookup tables. Loaded via `_config.py` → `load_api_583_section()`
- Config path overridable via `LEAN_VS_CONFIG` env var

### Test structure
- `tests/test_feature_engineering/`: Unit tests for each feature module + `test_api_583_risk/` subdirectory
- `tests/test_dataset/`: Tests for `llm_scoring` (mock + resume) and `pipeline` (path resolution)
- `tests/test_modelling/`: Tests for `SklearnModel` fit/predict round-trip
- `tests/lean_virtual_sensor/inputs_generation/`: Dataset validation tests (schema compliance, distributions, constraints). Many use the `df` fixture which requires `--dataset`
- `tests/conftest.py`: Provides `--dataset` CLI option and session-scoped fixtures (`df`, `schema`, `asset_config`, `gen_config`)

## Conventions

- Python 3.12, ruff for linting/formatting (line length 100, select E/F/I/UP/W)
- DataFrames should have descriptive names (`weather_df`, `process_history_df`), not bare `df` (exception: the `df` test fixture)
- Weather API key via `VISUAL_CROSSING_API_KEY` env var (from `.env`, never committed)

## CI

GitHub Actions workflow (`.github/workflows/ci.yml`) runs on pushes to `main` and PRs targeting `main`. It builds the Docker image and runs `ruff check` + `pytest` inside it.

## Data

Intermediate and final CSVs are committed to `data/`:
- `data/raw_synthetic_inputs/` — static per-asset CSVs (output of generate step)
- `data/timeseries/` — per-asset process-temperature CSVs (requires weather cache)
- `data/featurised/` — static + derived features + API 583 total
- `data/datasets/` — featurised + `cui_risk_score` (currently mock random scores)
- `data/models/` — trained model artefacts
- `data/results/` — kotsu results CSVs
