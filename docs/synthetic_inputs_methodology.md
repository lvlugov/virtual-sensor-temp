# Synthetic Dataset Generation — Methodology

---

## 1. Purpose

This document records every decision made in the design of the synthetic input dataset for the CUI lean virtual sensor model. It exists so that:

- Any team member can understand *why* a parameter has a particular value
- Reviewers can see which decisions are SME-approved vs citation backlog vs open product questions
- Future versions can be diffed against this baseline
- The generation is reproducible and auditable

The synthetic dataset provides labelled training data for an ML model that predicts CUI risk. A separate real dataset (~70 records from an existing asset register) is held aside for validation.

---

## 2. Scope and Exclusions

### What is generated

All static and quasi-static input variables to the CUI model:

| Group | Variables |
|---|---|
| Asset Identification | asset_class, asset_commissioning_date, component_diameter, furnished_thickness, last_inspection_thickness |
| Material & Metallurgy | metallurgy_family |
| Geometry | most_prevalent_geometry_class, geometry_complexity, orientation |
| Environment & Exposure | exposure_zone, shelter_flag, sweating_asset |
| Process Conditions | operating_temperature, min/max_operating_temperature, avg_cycles_per_quarter, operation_vs_shutdown_fraction, tracing_system |
| Insulation | insulation_material, insulation_thickness, insulation_install_date, insulation_condition, cladding_integrity, insulation_chloride_flag |
| Coating | coating_system, coating_application_date |
| Inspection & Maintenance | latest_inspection_date, inspection_ever_done, washdown_records |

### What is explicitly excluded

| Variable | Reason |
|---|---|
| `T_ambient(t)`, `RH(t)`, `rainfall(t)`, `T_process(t)` | Hourly time-series. Generated separately in the temperature/weather module, which is out of scope for this dataset. |
| `Risk` | Output label. Assigned separately after the CUI model is applied. Not an input. |
| `Asset` (tag/ID) | Generated as sequential synthetic ID (`SYNTH-0001` etc.) in the pipeline directly. |

---

## 3. Architecture Overview

The generation system has four config files and a Python pipeline under **`lean_virtual_sensor/inputs_generation/`**. Validation tests live under the repository **`tests/`** tree (shared `tests/conftest.py`, test modules under `tests/lean_virtual_sensor/inputs_generation/`).

```
lean_virtual_sensor/inputs_generation/
  config/
    schema.yaml             ← Variable registry aligned to product data dictionary
    asset_class_config.yaml ← Per-class physical constraints and probability weights
    conditional_rules.yaml  ← Conditional generation rules (deterministic + reasoned weights)
    generation_config.yaml  ← Run parameters (seed, n_rows, proportions)

  pipeline.py               ← Orchestrates the full generation run
  layer_generators.py       ← One function per DAG layer
  constraints.py            ← Post-generation structural repair (dates, ordering, clamps)
  schema_loader.py          ← Parses config files into Python objects
  generate.py               ← CLI entry point

tests/
  conftest.py               ← Shared fixtures; --dataset CLI option; loads config YAMLs
  lean_virtual_sensor/inputs_generation/
    test_schema_compliance.py
    test_constraints.py
    test_date_chain.py
    test_completeness.py
    test_distributions.py
```

The pipeline reads all four config files, generates 1,000 rows in DAG layer order, runs the full test suite, and only writes output if all tests pass.

---

## 4. Variable Generation Order (DAG Layers)

Variables are not independent — many can only be correctly generated once others are known. The layers encode this dependency structure (a topological sort of the variable dependency graph).

The dependencies come directly from the data dictionary's **Constraint** and **Linked Variables** columns.

### Layer 1 — Independent anchors
No dependencies on other generated variables. Drawn first.

`asset_class`, `exposure_zone`, `metallurgy_family`, `asset_commissioning_date`

### Layer 2 — Depend on asset_class
Per-class probability weights and allowed value subsets are defined in `asset_class_config.yaml`.

`most_prevalent_geometry_class`, `geometry_complexity`, `orientation`, `shelter_flag`

### Layer 3 — Depend on asset_class + component geometry
Numeric ranges vary by asset class. `component_diameter` is drawn first in this layer; `furnished_thickness` and `insulation_thickness` drawn after.

`component_diameter`, `furnished_thickness`, `insulation_material`, `insulation_thickness`

### Layer 4 — Date / age chain
All dates are bounded by: `asset_commissioning_date` ≤ date ≤ `reference_date`.

`insulation_install_date`, `coating_application_date`, and `latest_inspection_date` are drawn independently within that window (inspection and insulation are not ordered relative to each other).

`insulation_install_date`, `coating_application_date`, `coating_system`, `latest_inspection_date`, `inspection_ever_done`

### Layer 5 — Temperature triplet + process parameters
`operating_temperature` is drawn first; `min` and `max` are then drawn as offsets relative to it, enforcing min ≤ op_temp ≤ max exactly.

`operating_temperature`, `min_operating_temperature`, `max_operating_temperature`, `avg_cycles_per_quarter`, `operation_vs_shutdown_fraction`, `tracing_system`, `sweating_asset`

### Layer 6 — Conditional flags
Generated after `exposure_zone`, `insulation_material`, and dates are known — all three are required to evaluate the chloride auto-flag rule.

`insulation_chloride_flag`, `insulation_condition`, `cladding_integrity`

### Layer 7 — Final variables
`last_inspection_thickness` depends on `furnished_thickness` (must be ≤ it). `washdown_records` is independent but placed last for simplicity.

`last_inspection_thickness`, `washdown_records`

---

## 5. Asset Class Proportions

### Target distribution (n=1,000)

| Asset Class | Count | % | Rationale |
|---|---|---|---|
| PIPE | 380 | 38% | Dominant class, dialled back from real-world ~60% for ML diversity |
| PRESSURE_VESSEL | 175 | 17.5% | Second most common insulated class in O&G |
| HEAT_EXCHANGER | 145 | 14.5% | Common in processing; distinct nozzle-heavy CUI profile |
| COLUMN | 105 | 10.5% | Distinct risk class: tall, vertical, complex, MARINE-exposed |
| STORAGE_TANK | 75 | 7.5% | Lower CUI priority but present on all sites |
| AIR_COOLER | 70 | 7% | Separate from HEAT_EXCHANGER per API 583 Table 4.1 |
| REACTOR | 50 | 5% | Thick-walled, high-consequence; small population |

### Basis and references

Real-world O&G facility asset registers are approximately 55–65% piping by count (HOIS Hydrocarbon Operations Inspection Scheme surveys; API 583 field evidence where piping is the primary focus equipment class). The proportions above deliberately reduce PIPE from ~60% to 38% to give the ML model adequate training samples for minority classes.

If the model is ultimately deployed against a real asset register that is 60% pipe, the class imbalance handling in the ML training step should account for this mismatch.

**References:**
- API 583:2014 *Corrosion Under Insulation and Fireproofing*, Table 4.1
- HOIS (Hydrocarbon Operations Inspection Scheme), published survey data — piping accounts for ~55–65% of CUI findings
- Energy Institute / TWI CUI Surveys (2014–2020) — vessel + exchanger populations at ~15–20% combined in typical refinery registers
- ISO 14224:2016 Table A.4 — equipment taxonomy and relative population guidance

---

## 6. Conditional Rules: Tier Classification

Rules in `conditional_rules.yaml` are classified into two tiers with different levels of evidential support.

### Tier 1 — Deterministic (fully auditable)

These rules are explicitly stated in the data dictionary or directly derivable from standards. They are enforced as hard constraints, not probabilities. Full definition: `conditional_rules.yaml` → `deterministic_rules`.

| Rule ID | Generator status | Citations |
|---|---|---|
| `R-CHLORIDE-01` | Executed from YAML at DAG layer 6 only; asserted by `test_chloride_auto_flag` | `citations_audit.md` rows 1, 36, 42 |

### Downstream rules (not in generator)

Rules that affect how the **CUI model** and product layer interpret stored metadata — but are **not** executed by the synthetic inputs generator. They must not be added to `conditional_rules.yaml` (`schema_loader` enforces `applies_at: generation` only). SME approval record: `docs/conditional_rules_sme_review.md` → `R-COAT-DEFER-01`.

#### `R-COAT-DEFER-01` — coating age and degraded susceptibility

**SME review:** approved (`2026-05-29-sme-draft-6`)  
**Citations log:** rows 2, 43 in `citations_audit.md`

When `coating_age_years` > 10 and `coating_system` is `EPOXY_HT_MULTI` or `EPOXY_HT_SINGLE`, downstream product logic (CUI model and SME assessment) should treat the coating as **degraded for susceptibility** (elevated `m_coat`) **without** requiring the stored metadata value to change.

`EPOXY_AGED` is **not** an installed coating type in the asset register sense. It represents a derived degraded state and is **not** in the data dictionary allowed values.

| Condition | Intended downstream action |
|-----------|---------------------------|
| `coating_age_years` > 10 AND `coating_system` in {EPOXY_HT_MULTI, EPOXY_HT_SINGLE} | Apply degraded coating susceptibility downstream; preserve `EPOXY_HT_*` in stored metadata |

**Source:** data dictionary — `coating_system` constraints; API 583 coating age rule `[CITATION_TBC]`

**Generator behaviour:** the synthetic generator **does not rewrite** old organic epoxy to `EPOXY_AGED`. Stored `coating_system` values remain `EPOXY_HT_MULTI` or `EPOXY_HT_SINGLE` as drawn. Degradation is a downstream model rule only.

**Contract test:** `test_coating_system_allowed_values` in `test_constraints.py` asserts no `EPOXY_AGED` in generated CSV output.

### Tier 2 — Physically reasoned (`[ENGINEERING_JUDGEMENT]`)

The *direction* of these effects is defensible from engineering physics and industry practice. The *specific probability values* are assumptions that have not been calibrated to a dataset.

Every Tier 2 value is tagged `[ENGINEERING_JUDGEMENT]` in `conditional_rules.yaml`. Weights were **reviewed and approved** by SME (`2026-05-29-sme-draft-6`; see `docs/conditional_rules_sme_review.md`). Recalibration against real register data remains optional future work.

| Rule ID | Variable | Summary |
|---|---|---|
| `R-INSMAT-W-01` | `insulation_material` | Weights by exposure zone (FOAMGLASS preference in MARINE) |
| `R-COAT-W-01` | `coating_system` | Weights by years since commissioning and exposure zone |
| `R-INSCOND-W-01` | `insulation_condition` | Degradation with insulation age / marine exposure |
| `R-CLAD-W-01` | `cladding_integrity` | Degradation with asset age |
| `R-TRACE-W-01` | `tracing_system` | Prevalence by operating temperature |
| `R-SWEAT-W-01` | `sweating_asset` | Sweating likelihood by operating temperature |
| `R-METAL-W-01` | `metallurgy_family` | CS dominant; more SS in severe exposure |

Geometry: `R-PIPE-NPS-01` — see `conditional_rules.yaml` → `geometry_standards` and [component geometry sizing](component_geometry_sizing.md).

### What was deliberately excluded

Purely statistically derived correlations (e.g. empirical co-occurrence rates from the 70-row real dataset) are excluded. That dataset is too small and too biased (heavily MARINE, heavily PIPE) to yield reliable distribution estimates. Using it for correlation fitting would encode its biases into the synthetic training data.

---

## 7. Handling of Nulls

### Synthetic dataset: no nulls

All 1,000 synthetic rows are fully populated. Nulls in the synthetic dataset would introduce noise without meaning (there is no real-world reason behind them). Full population improves ML training data quality.

### Real dataset: nulls are meaningful

When the real dataset is ingested for validation, nulls should **not** be imputed. In particular:

- `last_inspection_thickness = NULL` → asset has no UT inspection record. Model should treat this as `Evid_UT = 0` and `time_since_last_inspection = 10 years` (conservative maximum per data dictionary).
- `insulation_chloride_flag = NULL` → treat as FALSE (conservative default).

The test suite `test_completeness.py` enforces no-null rules on the synthetic dataset only. A separate validation script for the real dataset should handle nulls as informative signals.

---

## 8. Temperature Operating Ranges

Operating temperature ranges per metallurgy family are defined in `generation_config.yaml` under `operating_temperature_ranges`. These are drawn uniformly within the stated range.

The ranges reflect typical process service windows in O&G / refining:
- Carbon steel cryogenic (NGL) service: as low as −30°C
- Carbon steel hot refinery service: up to 300°C
- Austenitic SS and nickel alloys: elevated temperature / corrosive service

These ranges are `[ENGINEERING_JUDGEMENT]` and should be reviewed with a process engineering team.

The CUI active envelope for carbon steel (−4 to 175°C) and austenitic SS (50–175°C, peak ~120°C) is not enforced at generation time — assets outside this envelope are valid records (the CUI model would treat them as low susceptibility, which is useful training signal).

---

## 9. Wall Loss Distribution

`last_inspection_thickness` is generated as:

```
wall_loss_fraction ~ Beta(alpha=1.5, beta=8.0), clamped to [0.01, 0.60]
last_inspection_thickness = furnished_thickness × (1 − wall_loss_fraction)
```

The Beta(1.5, 8.0) distribution is right-skewed — most assets have minor wall loss (5–15%), with a tail of significantly thinned assets. The 60% cap reflects the practical limit beyond which an asset is typically retired or repaired.

**These Beta parameters are `[ENGINEERING_JUDGEMENT]` and have not been calibrated to real inspection data.** Review against UT thinning datasets when available.

---

## 10. Reproducibility

| Control | Mechanism |
|---|---|
| Deterministic output | Fixed `random_seed` in `generation_config.yaml` |
| Versioned output | Filename includes version and seed: `synthetic_v1.0_seed42.csv` |
| Config stability | All four config files are version-controlled. Changes require a version bump. |
| Library versions | `pyproject.toml` declares dependencies; `uv.lock` pins resolved versions (sync via `uv sync` / project `make sync` in Docker) |
| Quality gate | Output is only written if all pytest tests pass |

To generate a new independent dataset: increment `version`, change `random_seed`, re-run `python generate.py`.

---

## 11. Test Suite

The test suite under **`tests/`** (see Section 3) validates any CSV against the schema. It is designed to run on both the synthetic dataset (as a quality gate) and the real dataset (for validation). Shared fixtures and `--dataset` are defined in **`tests/conftest.py`**.

| Test file | Scope |
|---|---|
| `test_schema_compliance.py` | All categorical values within allowed sets; all numerics within range; correct types |
| `test_constraints.py` | Inter-variable rules: min ≤ op_temp ≤ max, last_inspection ≤ furnished_thickness, chloride auto-flag |
| `test_date_chain.py` | Date ordering: install/application dates within asset lifetime; inspection dates ≤ reference |
| `test_completeness.py` | No nulls in fields defined as nullable=false in schema.yaml |
| `test_distributions.py` | Asset class counts within ±5% of targets; no degenerate distributions |

Run from the **repository root**, with a path to the CSV (example synthetic output):

`pytest tests/ --dataset lean_virtual_sensor/inputs_generation/outputs/synthetic_v1.0_seed42.csv`

---

## 12. Known Limitations and Future Work

1. **Tier 2 rule calibration**: SME approved Tier 2 weights (`2026-05-29-sme-draft-6`). Optional future pass: calibrate against real inspection / register data.

2. **Correlated operating temperature and asset class**: No explicit conditioning of operating_temperature on asset_class. In practice, REACTORs and COLUMNs tend to run hotter than STORAGE_TANKs. This could be added as a Tier 2 rule.

3. **Inspection interval realism**: `latest_inspection_date` currently drawn uniformly within `[0.5, 10]` years from today.

4. **Risk labels**: Not generated here. Will be assigned separately using the CUI model.

---

## References

- API 581:2016 *Risk-Based Inspection Methodology*
- API 583:2014 *Corrosion Under Insulation and Fireproofing*
- ISO 14224:2016 *Collection and exchange of reliability and maintenance data for equipment*
- ISO 9223:2012 *Corrosion of metals and alloys — corrosivity of atmospheres*
- NACE SP0198-2010 *Control of Corrosion Under Thermal Insulation and Fireproofing Materials*
- HOIS (Hydrocarbon Operations Inspection Scheme) survey reports
- Energy Institute / TWI CUI Survey Reports (2014–2020)
