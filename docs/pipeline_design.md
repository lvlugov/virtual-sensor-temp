# Pipeline Design

## Context

The repo has synthetic data generation and feature engineering fully built, but no structure
for: (a) producing a labelled dataset end-to-end, or (b) training/evaluating models against
that dataset. This design adds the full pipeline wired up and running, with a mock LLM scorer
so the complete flow executes immediately on synthetic data.

Datasets are small -- commit all intermediate and final CSVs to the repo under `data/`.

## Overview

Two phases, clean boundary between them.
Each phase 1 step reads a CSV (or directory) and writes a CSV -- checkpointing, auditability,
and resume from any step.

```text
Phase 1: Dataset Production (each step: CSV in -> CSV out, all committed to repo)

  +----------+    +----------------+    +-----------+    +-----------+
  | Generate |--> | Gen Timeseries |--> | Featurise |--> | LLM Score |--> CSV
  +----------+    +----------------+    +-----------+    +-----------+
  raw_synthetic_  timeseries/           featurised_      dataset_*.csv
  inputs_*.csv    <ASSET>_*.csv         *.csv

Phase 2: Model Development (kotsu, directly)

  dataset_*.csv -> kotsu.run(model_registry, validation_registry) -> results.csv
```

The three raw inputs per run:
- `raw_synthetic_inputs_*.csv` — static per-asset inventory (output of `generate.py`)
- `timeseries/<ASSET>_*.csv` — per-asset process-temperature series (output of
  `generate_timeseries.py`); requires a weather cache directory; step skipped if absent
- weather cache directory — pre-fetched hourly weather per location (not generated here)

**Phase 1 configs** are dataclasses that define the parameters for each run.
A configs module holds named configs (e.g. `baseline_1k`).
The runner iterates configs, producing one CSV per config per step.
The config *is* the provenance record -- you can re-compute any CSV from its config.
Configs can reference upstream outputs by name -- e.g. a scoring-only config points at an
existing featurised CSV, so you can re-score without re-generating or re-featurising.

**Phase 2** uses kotsu directly -- no wrapper abstractions.
We register models and validations against kotsu's API and call `kotsu.run()`.

## Data storage

```text
data/
  raw_synthetic_inputs/   # step 1 output: static per-asset CSVs
    baseline_1k.csv
  timeseries/             # step 2 output: per-asset process-temperature CSVs
    baseline_1k/
      SYNTH-0001_<start>_<end>.csv
      ...
  featurised/             # step 3 output: static + derived features + API 583 total
    baseline_1k.csv
  datasets/               # step 4 output: featurised + cui_risk_score (0-100)
    baseline_1k.csv           # scored with mock scorer
    BASELINE_1K_LLM.csv       # same features, re-scored with different LLM config
  models/                 # trained model artefacts
  results/                # kotsu results CSVs
    results.csv
```

File names come from the config's `name`/`raw_synthetic_inputs_name`/`featurised_name` fields.
Multiple dataset configs can share the same upstream raw inputs and featurised CSVs.

---

## Phase 1: `lean_virtual_sensor/dataset/`

### `configs.py` -- named run configurations

Each config is a frozen dataclass defining all parameters for one dataset production run.
The generation step reuses the existing `generation_config.yaml` files; featurise and LLM
scoring steps get their params here too.

```python
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class DatasetConfig:
    name: str

    # Step 1: Generate
    generation_config_path: Path

    # Step 2+3: Featurise (timeseries step skipped if weather_dir absent)
    weather_dir: Path

    # Step 4: LLM Score
    llm_config: dict = field(default_factory=dict)

    # Reuse upstream outputs from a different config by name.
    # When None, defaults to self.name.
    raw_synthetic_inputs_name: str | None = None  # -> data/raw_synthetic_inputs/{name}.csv
    timeseries_name: str | None = None            # -> data/timeseries/{name}/
    featurised_name: str | None = None            # -> data/featurised/{name}.csv


BASELINE_1K = DatasetConfig(
    name="baseline_1k",
    generation_config_path=Path(
        "lean_virtual_sensor/inputs_generation/config/generation_config.yaml"
    ),
    weather_dir=Path("lean_virtual_sensor/output"),
    llm_config={"seed": 42},
)

# Example: same raw inputs + features, different LLM scorer config
BASELINE_1K_LLM = DatasetConfig(
    name="baseline_1k_llm",
    generation_config_path=BASELINE_1K.generation_config_path,
    weather_dir=BASELINE_1K.weather_dir,
    llm_config={"seed": 99},
    featurised_name="baseline_1k",  # reuse existing featurised CSV
)

ALL_CONFIGS: dict[str, DatasetConfig] = {
    "baseline_1k": BASELINE_1K,
    "baseline_1k_llm": BASELINE_1K_LLM,
}
```

### `featurise.py` -- raw synthetic inputs CSV -> featurised CSV

Thin wrapper over `inputs_generation.generate_features.append_features()`, which handles
all column mapping and feature computation.

```python
def featurise_inventory(
    raw_synthetic_inputs_csv: Path,
    timeseries_dir: Path,
    weather_dir: Path,
    output_csv: Path,
    *,
    reference_date: str,
    seed: int,
) -> Path:
    """Read raw synthetic inputs CSV, compute derived features + API 583 total, write output.

    Delegates to inputs_generation.generate_features.append_features().

    Input columns: schema.yaml variable names (output of generate.py).
    Output columns: all input columns + 6 derived feature columns + api583_total_score.
    """
```

**Field name mapping** (generation schema -> feature pipeline, handled inside `append_features`):

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
    llm_config: dict,
) -> Path:
    """Read featurised CSV, assign CUI risk score (0-100) per row, write output.

    Current implementation: mock scorer using random integers seeded from
    llm_config.get("seed", 42). Replace _call_llm() to use a real model.

    If output_csv already exists with some rows scored, skips those rows
    (resume support for expensive LLM runs).

    Output columns: all input columns + cui_risk_score (int 0-100).
    """


def _build_prompt(asset_row: dict) -> str:
    """Format one asset's features + API 583 scores into a scoring prompt."""
    raise NotImplementedError


def _call_llm(prompt: str, *, llm_config: dict) -> int:
    """Call LLM API, parse response, return integer 0-100."""
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
      generate      -> data/raw_synthetic_inputs/{raw_synthetic_inputs_name}.csv
      gen_timeseries-> data/timeseries/{timeseries_name}/   (skipped if weather_dir absent)
      featurise     -> reads  data/raw_synthetic_inputs/{raw_synthetic_inputs_name}.csv
                       writes data/featurised/{featurised_name}.csv
      llm_score     -> reads  data/featurised/{featurised_name}.csv
                       writes data/datasets/{name}.csv

    Where raw_synthetic_inputs_name/featurised_name default to config.name when not set.
    Skips a step when its output CSV/dir already exists.
    Returns path to the final dataset CSV.
    """


def run_all_configs(
    configs: dict[str, DatasetConfig] | None = None,
    **kwargs,
) -> list[Path]:
    """Run the pipeline for every config (default: ALL_CONFIGS)."""
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

    def fit(self, train_df: pd.DataFrame) -> None: ...

    def predict(self, input_df: pd.DataFrame) -> np.ndarray: ...


model_registry.register(
    id="linear-v1.0",
    entry_point=SklearnModel,
    kwargs={"estimator": LinearRegression(), "feature_columns": [...]},
)
```

### `validations.py` -- validation functions registered with kotsu

```python
import kotsu

validation_registry = kotsu.registration.ValidationRegistry()


def kfold_cv(model, *, dataset_path: str, n_splits: int = 5) -> dict[str, float]:
    """K-fold cross-validation. Returns {"mae": ..., "rmse": ..., "r2": ...}."""
    # real implementation using sklearn KFold


validation_registry.register(
    id="kfold-5-v1.0",
    entry_point=kfold_cv,
    kwargs={"dataset_path": "data/datasets/baseline_1k.csv", "n_splits": 5},
)
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

- **`pyproject.toml`**: add `anthropic`, `kotsu`, `scikit-learn` to dependencies
- **`CLAUDE.md`**: update architecture section to document `dataset/` and `modelling/`,
  replace TODO with current state

## Verification

End-to-end run:
```bash
python -c "
from lean_virtual_sensor.dataset.pipeline import run_dataset_pipeline
from lean_virtual_sensor.dataset.configs import BASELINE_1K
run_dataset_pipeline(BASELINE_1K)
"
# produces: data/raw_synthetic_inputs/baseline_1k.csv
#           data/featurised/baseline_1k.csv
#           data/datasets/baseline_1k.csv

python -c "
from lean_virtual_sensor.modelling.run import run_experiments
run_experiments()
"
# produces: data/results/results.csv
```

Plus:
1. `make lint` passes
2. `make test` passes
3. All modules importable cleanly
