# API 583 CUI Risk Scorer — Design, Decisions, and Standard-vs-Implementation

This document records how the API 583 CUI-likelihood scorer is implemented in
`lean_virtual_sensor/feature_engineering/api_583_risk/`, how each of the seven
parameter scorers maps to API 583 Annex A, every deliberate deviation from the
standard, and the exact input variables each section consumes.

It is the audit companion to the single calibration file
[`api_583_risk/config.yaml`](../lean_virtual_sensor/feature_engineering/api_583_risk/config.yaml):
every threshold, allowed-value list, and lookup quoted below lives in that file,
so the calibration can be reviewed against the standard in one place.

---

## 1. Scope

This mapping covers:

- Parameters 1–7 of API 583 Annex A Tables A.1 (carbon/low-alloy steel) and A.8
  (austenitic/duplex stainless steel).
- Final aggregation per Tables A.7 (carbon/low-alloy) and A.9 (stainless) to a
  Likelihood Rating A–E.
- Asset routing by `metallurgy_family`, including out-of-scope handling for
  `NICKEL_ALLOY`.

### Out of scope

- **API 583 Annex A Table A.5 (CUF — Corrosion Under Fireproofing).** Fireproofed
  assets are a separate workstream.
- **Translation of the API 583 Likelihood Rating into a downstream API 581 damage
  factor or RBI inspection date.**
- **The Lean Virtual Sensor's bespoke CUI risk model** — a parallel output with
  its own specification.

---

## 2. Metallurgy routing

Each asset is routed by `metallurgy_family`. Routing decides which tables apply
for Parameter 1 (operating temperature, §5.1) and for the final aggregation (the
likelihood band, §3). Parameters 2–7 use identical rules regardless of
metallurgy.

| `metallurgy_family` | Parameter 1 table | Aggregation table | Status |
|---|:---:|:---:|---|
| `CARBON_STEEL` | A.1 | A.7 | In scope |
| `LOW_ALLOY_STEEL` | A.1 | A.7 | In scope |
| `AUSTENITIC_SS` | A.8 | A.9 | In scope |
| `DUPLEX_SS` | A.8 | A.9 | In scope (treated as austenitic) |
| `NICKEL_ALLOY` | — | — | Out of scope — no API 583 score |

Config: `operating_temperature.{allowed_metallurgy, carbon_steel_families,
stainless_steel_families}` and `pipeline.carbon_steel_families`.

**Assumption A0 — Duplex SS treatment.** Duplex stainless steels are treated
identically to austenitic stainless per Tables A.8 and A.9. The standard's
footnote that duplex "may warrant" an increased rating is informative only — no
adjustment formula is given — so any per-asset uplift is left to engineering
override at the final-score review stage.

> **Note — NICKEL_ALLOY handling differs from spec v1.0 (unresolved).** The
> source specification calls for Parameter 1 to return `None` and the aggregator
> to return `likelihood = None` with an `out_of_scope` flag. The current code
> instead **raises `ValueError`** on an unknown metallurgy; the population runner
> catches it and records a NaN total. No `NICKEL_ALLOY` assets exist in the
> current dataset, so this has not surfaced in practice. Flagged for
> reconciliation.

---

## 3. Pipeline overview

API 583 Annex A scores CUI *likelihood* as the sum of seven independent
parameter scores, then maps the total to a letter band (A–E) using a
metallurgy-dependent table.

```
                 ┌─ operating_temperature ─┐
                 ├─ coating_age            ┤
  asset dict ──► ├─ jacketing_insulation   ┤──► 7 scores ──► sum = total ──► band (A–E)
                 ├─ heat_tracing           ┤                          (Table A.7 / A.9)
                 ├─ external_environment   ┤
                 ├─ insulation_type        ┤
                 └─ line_size              ┘
```

Code entry points ([`pipeline.py`](../lean_virtual_sensor/feature_engineering/api_583_risk/pipeline.py)):

- `compute_api_583_scores(asset)` → the seven per-parameter scores.
- `compute_api_583_likelihood(asset)` → `{scores, total, table_used, likelihood, flag}`.

Each parameter scores in `{0, 1, 3, 5}` (line_size and external_environment can
also be 0), mirroring the standard's "none / low / moderate / high" bands.

### Likelihood band mapping (total → letter)

The carbon/low-alloy steel families use **Table A.7**; austenitic/duplex
stainless use **Table A.9**. Family membership is set by
`pipeline.carbon_steel_families`.

| Total | Carbon / low-alloy (A.7) | Stainless (A.9) |
|------:|:------------------------:|:---------------:|
| ≤ 6   | A | A |
| 7–13  | B | B |
| 14–20 | C | C *(only 14–17)* |
| 18–20 | C | **undefined** → `likelihood = None`, `flag = "ss_gap_18_to_20"` |
| 21–27 | D | D |
| > 27  | E | E |

**Decision — the stainless 18–20 gap is preserved, not patched.** API 583
Table A.9 leaves totals 18–20 undefined for stainless. Rather than silently fold
them into C or D, the pipeline returns `likelihood = None` with an explicit
`flag = "ss_gap_18_to_20"` so the gap is visible to downstream consumers instead
of being masked. Config keys: `ss_band_c_max: 17`, `ss_gap_max: 20`.

---

## 4. Input variables — what each section consumes

`compute_api_583_scores` requires **17 keys**. Fifteen are raw inventory
fields; **two are derived features** computed upstream by the feature pipeline
(`coating_age_years`, `system_age_years` from `age_features.compute_age_years`).
This is why API 583 is run *after* the feature pipeline in
`generate_features.py`.

| Scorer | Input variables | Source |
|---|---|---|
| `operating_temperature` | `metallurgy_family`, `operating_temperature`, `min_operating_temperature`, `max_operating_temperature`, `avg_cycles_per_quarter` | raw inventory |
| `coating_age` | `coating_system`, `coating_age_years` ⭑, `system_age_years` ⭑ | ⭑ derived |
| `jacketing_insulation` | `cladding_integrity`, `insulation_condition`, `system_age_years` ⭑ | ⭑ derived |
| `heat_tracing` | `tracing_system` | raw inventory |
| `external_environment` | `exposure_zone`, `shelter_flag`, `sweating_asset` | raw inventory |
| `insulation_type` | `insulation_material` | raw inventory |
| `line_size` | `asset_class`, `component_diameter` | raw inventory |

`component_diameter` is only read when `asset_class == "PIPE"`; `coating_age_years`
and `system_age_years` are optional (`None`-tolerant) within their scorers but
are always supplied here because the feature pipeline computes them.

---

## 5. The seven parameters — standard vs. implementation

For each parameter: the API 583 Annex A reference, the implemented score buckets
(with config keys), the missing-data default, and any deviation from the
standard.

### 5.1 `operating_temperature` — Annex A Table A.1 (CS) / Table A.8 (SS)

Representative operating temperature → CUI/ECSCC band. Split by metallurgy.

**Carbon / low-alloy steel (Table A.1), steady-state buckets (°C):**

| Operating temperature | Score | Config keys |
|---|:---:|---|
| 77 ≤ T ≤ 110 (CUI peak) | 5 | `cs_peak_low_c`, `cs_peak_high_c` |
| 38 ≤ T < 77 **or** 110 < T ≤ 132 | 3 | `cs_mod_lower_low_c`, `cs_mod_upper_high_c` |
| −4 ≤ T < 38 **or** 132 < T ≤ 177 | 1 | `cs_envelope_low_c`, `cs_envelope_high_c` |
| outside [−4, 177] | 0 | — |

**Cyclic-service override (CS only):** if `max_operating_temperature > 177` **and**
`min_operating_temperature < 110` **and** `avg_cycles_per_quarter > 0` → **5**,
regardless of the steady-state bucket. Config: `cyclic_max_temp_above_c: 177`,
`cyclic_min_temp_below_c: 110`.

**Austenitic / duplex stainless (Table A.8), ECSCC buckets (°C):**

| Operating temperature | Score | Config keys |
|---|:---:|---|
| 60 ≤ T ≤ 121 (ECSCC peak) | 5 | `ss_peak_low_c`, `ss_peak_high_c` |
| 121 < T ≤ 204 | 3 | `ss_elev_high_c` |
| 49 ≤ T < 60 | 1 | `ss_envelope_low_c` |
| outside | 0 | — |

**Validation:** raises if `metallurgy_family` is not in `allowed_metallurgy`, or
if `operating_temperature` falls outside `[min, max]`. No silent default —
operating temperature is a primary signal and a bad envelope is a data error.

### 5.2 `coating_age` — Annex A (coating quality × age)

Coating-system class × coating age, with a class-independent escalation on
insulation-system age. Rules are evaluated top-to-bottom (5-escalations → 0 → 1
→ 3 → conservative 5 fallback); first match wins.

**Coating → class map** (`coating_age.class`): `TSA`, `IOZ`, `EPOXY_HT_MULTI` →
**Quality**; `EPOXY_HT_SINGLE` → **General**; `BARE` → **BARE**; `UNKNOWN` →
**UNKNOWN**. Legacy code `EPOXY_AGED` is silently mapped to `UNKNOWN`
(`coating_age.legacy`).

| Condition | Score | Config keys |
|---|:---:|---|
| class UNKNOWN or BARE | 5 | — |
| `system_age_years ≥ 30` | 5 | `system_mid_max_age` |
| General + `coating_age_years > 15` | 5 | `general_max_age` |
| Quality + `coating_age_years < 8` | 0 | `quality_low_max_age` |
| `system_age_years < 15` | 0 | `system_low_max_age` |
| Quality + `8 ≤ coating_age_years < 15` | 1 | `quality_mid_max_age` |
| `15 ≤ system_age_years < 30` | 1 | `system_low/mid_max_age` |
| General + `coating_age_years ≤ 15` (incl. < 8) | 3 | `quality_low_max_age`, `general_max_age` |
| no rule matched (missing data) | 5 (fallback) | — |

**Validation:** raises on unknown `coating_system` or negative age. Missing ages
(`None`) are tolerated and fall through to the conservative 5 fallback.

### 5.3 `jacketing_insulation` — Annex A (cladding + insulation condition)

Worst of the two condition ratings drives the score; a new system in pristine
condition drops to 0.

| Condition | Score |
|---|:---:|
| new system (`system_age_years < 5`) **and** both ratings `ABOVE_AVERAGE` | 0 |
| worse-of-two = `BELOW_AVERAGE` | 5 |
| worse-of-two = `AVERAGE` | 3 |
| worse-of-two = `ABOVE_AVERAGE` (but not new enough for 0) | 1 |

Config: `jacketing_insulation.allowed = [ABOVE_AVERAGE, AVERAGE, BELOW_AVERAGE]`,
`new_system_max_age: 5`. Missing ratings default to `AVERAGE` (conservative).

**Decision — condition vocabulary is `ABOVE_AVERAGE / AVERAGE / BELOW_AVERAGE`.**
This three-level scale matches the synthetic data dictionary and the
`system_flag_feature` open/closed logic, so cladding/insulation condition uses
one vocabulary across the whole codebase (not a GOOD/FAIR/POOR variant).

### 5.4 `heat_tracing` — Annex A (CorrosionRadar refinement)

Pure lookup from `heat_tracing.score`:

| `tracing_system` | Score |
|---|:---:|
| `NONE` | 0 |
| `HIGH_INTEGRITY_STEAM_TRACED` | 1 |
| `MEDIUM_INTEGRITY_STEAM_TRACED` | 3 |
| `POOR_INTEGRITY_STEAM_TRACED` | 5 |
| `ELECTRIC_TRACED` | 1 |
| `HOT_OIL_TRACED` | 1 |

Missing data (`None`) → `NONE` → 0.

**Decision — steam tracing is split into integrity tiers rather than the
standard's binary active/failed dimension.** A deteriorating steam loop scores
progressively higher (1 → 3 → 5) without needing a separate operational-state
input. Electric and hot-oil tracing keep a single score (1) — neither presents
the leak-mode CUI mechanism that drove the original failed-steam escalation.

### 5.5 `external_environment` — Annex A (exposure × shelter × sweating)

Cascade (first match wins):

1. `sweating_asset is False` → **0** (no sweating mechanism → no CUI).
2. `shelter_flag == "DAMAGED"` → **5** (local water source).
3. `exposure_zone in {MARINE, SEVERE}` → **5**.
4. `exposure_zone == "ARID_DRY"` → **1**.
5. `exposure_zone == "TEMPERATE"` (catch-all) → **3**.

Config: `external_environment.allowed_exposure = [MARINE, TEMPERATE, ARID_DRY, SEVERE]`,
`allowed_shelter = [PROTECTED, NORMAL, DAMAGED]`. Missing exposure → `TEMPERATE`,
missing shelter → `NORMAL`, `sweating_asset = None` → treated as `True`
(conservative).

**Decisions:**

- **`sweating_asset` replaces the earlier `ach_90d == 0` escape hatch** — an
  explicit per-asset inventory attribute instead of a derived signal, so the
  API 583 risk layer no longer depends on the asset-temperature module.
- **Exposure vocabulary aligned to the data dictionary.** The scorer originally
  knew only `MARINE / TEMPERATE / ARID`. The synthetic data uses `ARID_DRY`
  (same concept) and adds `SEVERE`, so both were added at the root (config +
  dispatch + tests). `ARID_DRY` is the arid-inland bucket → 1.
- **`SEVERE → 5`** (folded into the MARINE branch). SEVERE is the harshest
  exposure class; scored at the coastal-corrosivity maximum. *(Confirmed scoring
  choice — not defined by the standard, which has no SEVERE class.)*

### 5.6 `insulation_type` — Annex A (material water-handling)

Pure lookup from `insulation_type.score`:

| `insulation_material` | Score | Rationale |
|---|:---:|---|
| `FOAMGLASS`, `PERLITE` | 1 | closed-cell / low-wicking |
| `CALCIUM_SILICATE`, `FIBERGLASS` | 3 | moderately absorbent |
| `MINERAL_WOOL`, `ASBESTOS`, `UNKNOWN` | 5 | high-wicking / legacy / unknown |

Missing data (`None`) → `UNKNOWN` → 5. Raises on any non-null material not in
the table.

**Decision — `PERLITE` spelling corrected at the root.** The lookup key was
previously misspelled `PEARLITE`, which does not exist in the data dictionary
(the data uses `PERLITE`). Every `PERLITE` asset raised "Bad insulation_material"
until the key was corrected in this config and the matching `asset_temperature`
conductivity table and tests.

### 5.7 `line_size` — Annex A (line/nozzle size)

Piping CUI risk rises as diameter falls (small bore traps water, hard to
inspect). Equipment has only short nozzles, so it short-circuits to 0.

| `asset_class` | `component_diameter` | Score |
|---|---|:---:|
| equipment (see below) | ignored | 0 |
| `PIPE` | OD > 168.3 mm (> 6 in. NPS) | 1 |
| `PIPE` | 60.3 < OD ≤ 168.3 mm (> 2 to 6 in.) | 3 |
| `PIPE` | OD ≤ 60.3 mm (≤ 2 in. NPS) | 5 |

Config: `od_2in_nps_mm: 60.3`, `od_6in_nps_mm: 168.3` (ASME B36.10).
`equipment_classes = [PRESSURE_VESSEL, HEAT_EXCHANGER, AIR_COOLER, STORAGE_TANK,
COLUMN, REACTOR]`. Raises on an `asset_class` not in `allowed_asset_class`, on
non-positive diameter, or on a `PIPE` missing its diameter.

**Decision — `COLUMN` and `REACTOR` are equipment (score 0).** The synthetic
data includes `COLUMN` (105 assets) and `REACTOR` (50 assets), which the config
did not list. Both are vessels with short nozzles, not piping runs, so they were
added to *both* `allowed_asset_class` and `equipment_classes` → score 0, exactly
like `PRESSURE_VESSEL`. Scoring them by shell diameter as if they were pipe NPS
would be physically meaningless.

---

## 6. Integration & engineering decisions (this work)

- **API 583 runs after the feature pipeline.** Two of its inputs
  (`coating_age_years`, `system_age_years`) are derived features, so
  `generate_features.py` computes the feature row first, then scores API 583 on
  the combined record. `sweating_asset` is the only API 583 input the feature
  pipeline does not echo, so it is read directly from the static row.
- **Only `api583_total_score` is appended** to the output dataset
  (`synthetic_v1.0_seed42_features.csv`) — the summed seven-parameter total.
  The per-parameter breakdown, likelihood band, and flag are computed but not
  written. Add columns later if the band/flag are needed downstream.
- **Per-asset robustness.** A row whose API 583 scoring raises is left with a
  NaN total rather than failing the run; the reason is counted and logged.
- **Config parse is cached.** `_config.py` memoises the parsed YAML
  (`functools.lru_cache`); without it, a population run re-read the config
  thousands of times (seven scorers per asset, several reads each).

### Vocabulary reconciliations made at the root

Running the scorers across the full 1000-asset population surfaced four
data↔scorer vocabulary gaps. All were fixed at the source (config + scorer +
tests), never patched per-call:

| Gap | Assets affected | Resolution |
|---|---:|---|
| `PERLITE` insulation (was misspelled `PEARLITE`) | 44 | corrected spelling (§3.6) |
| `COLUMN`, `REACTOR` rejected by line-size | 155 | added as equipment → 0 (§3.7) |
| `ARID_DRY` exposure label (scorer knew `ARID`) | 160 | scorer + config use `ARID_DRY` → 1 (§3.5) |
| `SEVERE` exposure had no branch | 106 | added `SEVERE` → 5 (§3.5) |

---

## 7. Where everything lives

| Item | Path |
|---|---|
| Pipeline (scores, total, band) | `api_583_risk/pipeline.py` |
| Seven scorers | `api_583_risk/input_features/*.py` |
| Single calibration file | `api_583_risk/config.yaml` |
| Cached config loader | `api_583_risk/_config.py` |
| Population runner (appends `api583_total_score`) | `inputs_generation/generate_features.py` |
| Tests | `tests/test_feature_engineering/test_api_583_risk/` |
