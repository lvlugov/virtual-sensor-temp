# Pipeline Design

## Context

The repo has synthetic data generation and feature engineering fully built, but no structure
for: (a) producing a labelled dataset end-to-end, or (b) training/evaluating models against
that dataset. This design adds clear interfaces and stubs so the full flow is wired up, with
actual implementations filled in later.

Datasets are small -- commit all intermediate and final CSVs to the repo under `data/`.

## Overview

Two phases, clean boundary between them.
Each phase 1 step reads a CSV and writes a CSV -- checkpointing, auditability, and resume
from any step.

```text
Phase 1: Dataset Production (each step: CSV in -> CSV out, all committed to repo)

  +----------+       +-----------+       +-----------+
  | Generate |-> CSV | Featurise |-> CSV | LLM Score |-> CSV
  +----------+       +-----------+       +-----------+
  inventory_*.csv    featurised_*.csv    dataset_*.csv

Phase 2: Model Development (kotsu, directly)

  dataset_*.csv -> kotsu.run(model_registry, validation_registry) -> results.csv
```

**Phase 1 configs** are dataclasses that define the parameters for each run.
A configs module holds named configs (e.g. `baseline_1k`, `marine_heavy_500`).
The runner iterates configs, producing one CSV per config per step.
The config *is* the provenance record -- you can re-compute any CSV from its config.
Configs can reference upstream outputs by name -- e.g. a scoring-only config points at an
existing featurised CSV, so you can re-score without re-generating or re-featurising.

**Phase 2** uses kotsu directly -- no wrapper abstractions.
We register models and validations against kotsu's API and call `kotsu.run()`.

## Data storage

```text
data/
  inventories/          # step 1 output: raw synthetic inventory CSVs
    baseline_1k.csv
  featurised/           # step 2 output: inventory + derived features + API 583
    baseline_1k.csv
  datasets/             # step 3 output: featurised + cui_risk_score (0-100)
    baseline_1k.csv           # scored with sonnet
    baseline_1k_opus.csv      # same features, re-scored with opus
  models/               # trained model artefacts
  results/              # kotsu results CSVs
    results.csv
```

File names come from the config's `name`/`inventory_name`/`featurised_name` fields.
Multiple dataset configs can share the same upstream inventory and featurised CSVs.

---

## Phase 1: `lean_virtual_sensor/dataset/`

### `configs.py` -- named run configurations

Each config is a frozen dataclass defining all parameters for one dataset production run.
The generation step reuses the existing `generation_config.yaml` files; featurise and LLM
scoring steps get their params here too.

```python
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DatasetConfig:
    name: str

    # Step 1: Generate
    generation_config_path: Path

    # Step 2: Featurise
    reference_date: str                    # ISO format, e.g. "2026-05-13"

    # Step 3: LLM Score
    llm_model: str                         # e.g. "claude-sonnet-4-20250514"
    llm_temperature: float                 # e.g. 0.0 for deterministic scoring

    # Reuse upstream outputs from a different config by name.
    # When None, defaults to self.name.
    inventory_name: str | None = None      # -> data/inventories/{inventory_name}.csv
    featurised_name: str | None = None     # -> data/featurised/{featurised_name}.csv


BASELINE_1K = DatasetConfig(
    name="baseline_1k",
    generation_config_path=Path(
        "lean_virtual_sensor/inputs_generation/config/generation_config.yaml"
    ),
    reference_date="2026-05-13",
    llm_model="claude-sonnet-4-20250514",
    llm_temperature=0.0,
)

# Example: same inventory + features, different LLM scorer
BASELINE_1K_OPUS = DatasetConfig(
    name="baseline_1k_opus",
    generation_config_path=BASELINE_1K.generation_config_path,
    reference_date=BASELINE_1K.reference_date,
    llm_model="claude-opus-4-20250514",
    llm_temperature=0.0,
    featurised_name="baseline_1k",  # reuse existing featurised CSV
)

ALL_CONFIGS: dict[str, DatasetConfig] = {
    "baseline_1k": BASELINE_1K,
    "baseline_1k_opus": BASELINE_1K_OPUS,
}
```

### `featurise.py` -- inventory CSV -> featurised CSV

```python
def featurise_inventory(
    inventory_csv: Path,
    output_csv: Path,
    reference_date: str,
) -> Path:
    """Read inventory CSV, compute derived features + API 583 scores, write output CSV.

    For each row:
      1. compute_features_for_asset() -> coating_age_years, system_age_years,
         open_system, ach_90d, cycle_count, wet_load
      2. compute_api_583_likelihood() -> 7 parameter scores + total + likelihood band

    Input columns: schema.yaml variable names (output of generation).
    Output columns: all input columns + derived feature columns + API 583 columns.
    """
    raise NotImplementedError
```

**Field name mapping** (generation schema -> feature pipeline):

| Generation column              | Feature pipeline parameter | Notes                                     |
|--------------------------------|----------------------------|--------------------------------------------|
| `most_prevalent_geometry_class`| `geometry_class`           | Rename                                     |
| `latest_inspection_date`       | `last_inspection_date`     | Rename                                     |
| `asset_commissioning_date`     | `asset_age`                | Derived: years from commissioning to today |

### `llm_scoring.py` -- featurised CSV -> labelled dataset CSV

```python
def score_dataset(
    featurised_csv: Path,
    output_csv: Path,
    *,
    llm_model: str,
    llm_temperature: float,
) -> Path:
    """Read featurised CSV, get CUI risk score (0-100) from LLM per row, write output.

    If output_csv already exists with some rows scored, skips those rows
    (resume support for expensive LLM runs).

    Output columns: all input columns + cui_risk_score (int 0-100).
    """
    raise NotImplementedError


def _build_prompt(asset_row: dict) -> str:
    """Format one asset's features + API 583 scores into a scoring prompt."""
    raise NotImplementedError


def _call_llm(prompt: str, *, model: str, temperature: float) -> int:
    """Call Claude API, parse response, return integer 0-100."""
    raise NotImplementedError
```

### `pipeline.py` -- dataset production runner

```python
def run_dataset_pipeline(
    config: DatasetConfig,
    *,
    data_dir: Path = Path("data"),
) -> Path:
    """Run dataset production pipeline for one config.

    Path resolution per step:
      generate  -> writes data/inventories/{inventory_name}.csv
      featurise -> reads  data/inventories/{inventory_name}.csv
                   writes data/featurised/{featurised_name}.csv
      score     -> reads  data/featurised/{featurised_name}.csv
                   writes data/datasets/{name}.csv

    Where inventory_name/featurised_name default to config.name when not set.
    Skips a step when its output CSV already exists.
    """
    raise NotImplementedError


def run_all_configs(
    configs: dict[str, DatasetConfig] | None = None,
    **kwargs,
) -> list[Path]:
    """Run the pipeline for every config (default: ALL_CONFIGS)."""
    raise NotImplementedError
```

---

## Phase 2: `lean_virtual_sensor/modelling/`

Uses [kotsu](https://github.com/datavaluepeople/kotsu) directly.
No wrapper classes around kotsu's registry or specs.

### `models.py` -- model factories registered with kotsu

```python
import kotsu

model_registry = kotsu.registration.ModelRegistry()


class SklearnModel:
    """Thin wrapper so sklearn estimators have fit/predict against DataFrames."""

    def __init__(self, estimator, feature_columns: list[str], target: str = "cui_risk_score"):
        ...

    def fit(self, train_df: pd.DataFrame) -> None:
        raise NotImplementedError

    def predict(self, input_df: pd.DataFrame) -> np.ndarray:
        raise NotImplementedError


# Example registration -- actual models added as we go
# model_registry.register(id="xgb-v1.0", entry_point=SklearnModel, kwargs={...})
```

### `validations.py` -- validation functions registered with kotsu

```python
import kotsu

validation_registry = kotsu.registration.ValidationRegistry()


def kfold_cv(model, *, dataset_path: str, n_splits: int = 5) -> dict[str, float]:
    """K-fold cross-validation. Returns {"mae": ..., "rmse": ..., "r2": ...}."""
    raise NotImplementedError


# Example registration
# validation_registry.register(
#     id="kfold-5-v1.0",
#     entry_point=kfold_cv,
#     kwargs={"dataset_path": "data/datasets/baseline_1k.csv", "n_splits": 5},
# )
```

### `run.py` -- experiment runner entry point

```python
import kotsu

from lean_virtual_sensor.modelling.models import model_registry
from lean_virtual_sensor.modelling.validations import validation_registry


def run_experiments(
    results_path: str = "data/results/results.csv",
    force_rerun: str | list[str] | None = None,
) -> pd.DataFrame:
    """Run all registered models x validations via kotsu.

    Results appended incrementally to results_path (kotsu handles dedup).
    """
    return kotsu.run.run(
        model_registry=model_registry,
        validation_registry=validation_registry,
        results_path=results_path,
        force_rerun=force_rerun,
    )
```

---

## Files to modify

- **`pyproject.toml`**: add `anthropic` and `kotsu` to dependencies
- **`CLAUDE.md`**: update architecture section to document `dataset/` and `modelling/`,
  replace TODO with current state

## Verification

1. `make lint` passes
2. `make test` passes (stubs only, no new tests)
3. All modules importable:
   ```bash
   python -c "from lean_virtual_sensor.dataset import configs, pipeline, featurise, llm_scoring; \
              from lean_virtual_sensor.modelling import models, validations, run"
   ```
