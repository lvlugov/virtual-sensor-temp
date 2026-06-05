# Conditional rules — SME review pack

**Review id:** `2026-05-29-sme-draft-6`  
**Source file:** `lean_virtual_sensor/inputs_generation/config/conditional_rules.yaml`

> **Phase 1 note (2026-06):** `coating_system_age_degradation` was relocated to `docs/downstream_product_semantics.md` (`R-COAT-DEFER-01`). This pack remains a historical SME snapshot; Tier 1 coating text below is retained for audit trail.

## How to use this document

- Tier 2 rules are evaluated **in order**; the **first matching** condition applies.
- **`[ENGINEERING_JUDGEMENT]`** — numeric weights are assumptions for SME review.
- **`[CITATION_TBC]`** — standard reference not yet verified.
- **Tier 1 generation rules** — hard rules when building synthetic rows (see `conditional_rules.yaml` → `deterministic_rules`).
- **Downstream product semantics** — rules that affect model/scoring but not generator config; see `docs/downstream_product_semantics.md`.

Please review **conditions, rationale, and weight tables**. Optional feedback table at the end.

---

## Tier 1 — deterministic rules (specification)

### `insulation_chloride_flag` (`applies_at: generation`)

**Source:** Data dictionary — `insulation_chloride_flag` (Edge Cases); NACE SP0198-2010 Section 5.4 `[CITATION_TBC]`; API 583 Table 4.2 `[CITATION_TBC]`

| Condition | Action | Value |
|-----------|--------|-------|
| `exposure_zone` = MARINE AND `insulation_material` = CALCIUM_SILICATE AND `insulation_age_years` > 5 | `set_value` | `true` |

---

### `coating_system_age_degradation` (relocated — historical SME text)

**Current location:** `docs/downstream_product_semantics.md` (`R-COAT-DEFER-01`). No longer in generator config.

**Source:** Data dictionary — `coating_system` constraints; API 583 coating age rule `[CITATION_TBC]`

`EPOXY_AGED` is **not** a generated coating type. Do not store it in `coating_system`. Apply degraded susceptibility at scoring time when age > 10 yr and type is `EPOXY_HT_MULTI` or `EPOXY_HT_SINGLE`.

| Condition | Action |
|-----------|--------|
| `coating_age_years` > 10 AND `coating_system` in {EPOXY_HT_MULTI, EPOXY_HT_SINGLE} | `treat_as_degraded_at_scoring` (metadata unchanged) |

---

## Tier 2 — conditional weights (used by generator)

### `insulation_material`

**Source:** API 583 Table 4.3 `[CITATION_TBC]`; NACE SP0198-2010 Table 1 `[CITATION_TBC]`; `[ENGINEERING_JUDGEMENT]` weights

| # | Condition | FOAMGLASS | MINERAL_WOOL | FIBERGLASS | CALCIUM_SILICATE | PEARLITE | UNKNOWN |
|---|-----------|-----------|--------------|------------|------------------|----------|---------|
| 1 | MARINE | 0.40 | 0.30 | 0.10 | 0.10 | 0.05 | 0.05 |
| 2 | ARID_DRY | 0.15 | 0.35 | 0.15 | 0.25 | 0.05 | 0.05 |
| 3 | SEVERE | 0.30 | 0.35 | 0.15 | 0.10 | 0.05 | 0.05 |
| 4 | Default | 0.25 | 0.40 | 0.15 | 0.12 | 0.04 | 0.04 |

---

### `coating_system`

Allowed generated types: **TSA, IOZ, EPOXY_HT_MULTI, EPOXY_HT_SINGLE, BARE, UNKNOWN** (not `EPOXY_AGED`).

**Source:** API 583 Table 4.4 `[CITATION_TBC]`; API 581 coating modifier `[CITATION_TBC]`; `[ENGINEERING_JUDGEMENT]` weights

| # | Condition | TSA | IOZ | EPOXY_HT_MULTI | EPOXY_HT_SINGLE | BARE | UNKNOWN |
|---|-----------|-----|-----|----------------|-----------------|------|---------|
| 1 | `asset_age` ≤ 10, MARINE | 0.25 | 0.25 | 0.30 | 0.15 | 0.03 | 0.02 |
| 2 | `asset_age` > 25, MARINE | 0.10 | 0.10 | 0.05 | 0.05 | 0.65 | 0.05 |
| 3 | `asset_age` ≤ 10 | 0.15 | 0.20 | 0.30 | 0.30 | 0.03 | 0.02 |
| 4 | `asset_age` > 25 | 0.05 | 0.08 | 0.05 | 0.07 | 0.70 | 0.05 |
| 5 | Default | 0.10 | 0.15 | 0.20 | 0.20 | 0.30 | 0.05 |

---

### `insulation_condition`

**Source:** API 583 Section 5.3 `[CITATION_TBC]`; API 581 insulation age modifier `[CITATION_TBC]`; `[ENGINEERING_JUDGEMENT]` weights

| # | Condition | GOOD | AVERAGE | POOR |
|---|-----------|------|---------|------|
| 1 | `insulation_age_years` ≤ 5 | 0.65 | 0.30 | 0.05 |
| 2 | `insulation_age_years` > 15, MARINE | 0.10 | 0.35 | 0.55 |
| 3 | `insulation_age_years` > 15 | 0.15 | 0.45 | 0.40 |
| 4 | 5 < `insulation_age_years` ≤ 15 | 0.35 | 0.50 | 0.15 |
| 5 | Default | 0.30 | 0.50 | 0.20 |

---

### `cladding_integrity`

**Source:** API 583 Section 5.3 `[CITATION_TBC]`; `[ENGINEERING_JUDGEMENT]` weights

| # | Condition | GOOD | AVERAGE | POOR |
|---|-----------|------|---------|------|
| 1 | `asset_age` ≤ 10 | 0.60 | 0.35 | 0.05 |
| 2 | `asset_age` > 20 | 0.15 | 0.45 | 0.40 |
| 3 | Default | 0.30 | 0.50 | 0.20 |

---

### `tracing_system`

Allowed values: **NONE**, **HIGH_INTEGRITY_STEAM_TRACED**, **MEDIUM_INTEGRITY_STEAM_TRACED**, **POOR_INTEGRITY_STEAM_TRACED**, **ELECTRIC_TRACED**, **HOT_OIL_TRACED**.

**Source:** API 583 Section 4.3 `[CITATION_TBC]`; `[ENGINEERING_JUDGEMENT]` weights (steam band split)

| # | Condition | NONE | HI_STEAM | MED_STEAM | POOR_STEAM | ELECTRIC | HOT_OIL |
|---|-----------|------|----------|-----------|------------|----------|---------|
| 1 | `operating_temperature` < 10 °C | 0.40 | 0.10 | 0.15 | 0.10 | 0.20 | 0.05 |
| 2 | `operating_temperature` ≥ 60 °C | 0.90 | 0.02 | 0.02 | 0.01 | 0.03 | 0.02 |
| 3 | Default | 0.72 | 0.05 | 0.07 | 0.04 | 0.08 | 0.04 |

---

### `sweating_asset`

Boolean **`true`** / **`false`**. Drawn after `operating_temperature` is known (layer 5).

**Source:** Data dictionary `[CITATION_TBC]`; `[ENGINEERING_JUDGEMENT]` weights

| # | Condition | true | false | Note |
|---|-----------|------|-------|------|
| 1 | `operating_temperature` < 10 °C | 0.35 | 0.65 | Cold service |
| 2 | `operating_temperature` ≥ 60 °C | 0.05 | 0.95 | Hot service |
| 3 | Default | 0.15 | 0.85 | SME to calibrate |

---

### `metallurgy_family`

Allowed: **CARBON_STEEL**, **LOW_ALLOY_STEEL**, **AUSTENITIC_SS**, **DUPLEX_SS** (not `NICKEL_ALLOY` or `OTHER`).

**Source:** ISO 14224:2016 Table A.41 `[CITATION_TBC]`; HOIS survey `[CITATION_TBC]`; `[ENGINEERING_JUDGEMENT]` weights

| # | Condition | CARBON_STEEL | LOW_ALLOY_STEEL | AUSTENITIC_SS | DUPLEX_SS |
|---|-----------|--------------|-----------------|---------------|-----------|
| 1 | SEVERE | 0.55 | 0.15 | 0.21 | 0.09 |
| 2 | Default | 0.74 | 0.12 | 0.10 | 0.04 |

---

## Citations to verify (backlog)

| Rule / variable | Reference to verify |
|-----------------|---------------------|
| `insulation_chloride_flag` | NACE SP0198-2010 §5.4; API 583 Table 4.2 |
| `coating_system_age_degradation` | API 583 coating age rule → see `docs/downstream_product_semantics.md` |
| `sweating_asset` | Data dictionary |
| `insulation_material` | API 583 Table 4.3; NACE SP0198-2010 Table 1 |
| `coating_system` | API 583 Table 4.4; API 581 coating modifier |
| `insulation_condition` | API 583 §5.3; API 581 insulation age modifier |
| `cladding_integrity` | API 583 §5.3 |
| `tracing_system` | API 583 §4.3 |
| `metallurgy_family` | ISO 14224:2016 Table A.41; HOIS survey |

---

## Implementation backlog (not in this rules commit)

| PR topic | Where it will be changed |
|----------|--------------------------|
| Remove `OTHER` asset class | `schema.yaml`, `generation_config.yaml`, `asset_class_config.yaml` |
| Standard DN / wall thickness sampling | `asset_class_config.yaml`, `layer_generators.py` |
| Stop rewriting `coating_system` in CSV | `layer_generators.py`, `constraints.py`, tests |
| Add `sweating_asset` bool | `schema.yaml`, `layer_generators.py`, tests, CSV |
| Remove `EPOXY_AGED` from `coating_system` | `schema.yaml`, `conditional_rules` (done), generators, constraints, tests, CSV |
| `tracing_system` six allowed values | `schema.yaml`, `conditional_rules` (done), generators, tests, CSV |
| Remove `NICKEL_ALLOY` / `OTHER` from `metallurgy_family` | `schema.yaml`, `conditional_rules` (done), `generation_config` op-temp ranges, tests, CSV |

---

## SME feedback (optional)

| Section | Approved? | Comments |
|---------|-------------|----------|
| Tier 1 — `insulation_chloride_flag` | Approved | |
| Tier 1 — `coating_system_age_degradation` | Approved| Some concerns regarding the Unknown option, if Unknown the value should not be close to the wrost case possible? Same coment for the remain. |
| `insulation_material` | Approved | |
| `coating_system` | Approved | |
| `insulation_condition` | Approved | |
| `cladding_integrity` | Approved | |
| `tracing_system` | Approved | |
| `sweating_asset` | Approved | |
| `metallurgy_family` | Approved | |
