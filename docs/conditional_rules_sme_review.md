# Conditional rules — SME review pack

**Review id:** `2026-05-29-sme-draft-6`  
**Source file:** `lean_virtual_sensor/inputs_generation/config/conditional_rules.yaml`  
**Status:** Tier 2 weights **approved** by SME (`2026-05-29-sme-draft-6`). Weight tables below were synced to post–dictionary-alignment terminology and YAML on **2026-06-14** (enum renames only; probabilities unchanged except `R-INSMAT-W-01` ASBESTOS at 0.01–0.04).

## How to use this document

- **Approval record** — SME feedback table at the end records sign-off from May 2026.
- Tier 2 rules are evaluated **in order**; the **first matching** condition applies.
- **`[ENGINEERING_JUDGEMENT]`** — numeric weights are assumptions; approved in principle by SME.
- **`[CITATION_TBC]`** — standard reference not yet verified (see `citations_audit.md`).
- **Rule IDs** — stable identifiers in `conditional_rules.yaml`. Weight tables below mirror YAML; YAML is authoritative if they diverge.
- **Downstream rules** — not in generator config (e.g. `R-COAT-DEFER-01`); documented in this pack and `docs/synthetic_inputs_methodology.md` §6.
- **Age predicates** — `asset_age_lte` / `asset_age_gt` in YAML mean years since `asset_commissioning_date` (derived at evaluation time).

---

## Tier 1 — deterministic rules (specification)

### `R-CHLORIDE-01` — `insulation_chloride_flag` (`applies_at: generation`)

**Source:** Data dictionary — `insulation_chloride_flag` (Edge Cases); NACE SP0198-2010 Section 5.4 `[CITATION_TBC]`; API 583 Table 4.2 `[CITATION_TBC]`

| Condition | Action | Value |
|-----------|--------|-------|
| `exposure_zone` = MARINE AND `insulation_material` = CALCIUM_SILICATE AND `insulation_age_years` > 5 | `set_value` | `true` |

---

### `R-COAT-DEFER-01` — coating age (downstream only)

**Not in generator config** — see `docs/synthetic_inputs_methodology.md` §6 and SME feedback below.

**Source:** Data dictionary — `coating_system` constraints; API 583 coating age rule `[CITATION_TBC]`

`EPOXY_AGED` is **not** a generated coating type. Apply degraded susceptibility downstream when age > 10 yr and type is `EPOXY_HT_MULTI` or `EPOXY_HT_SINGLE`.

| Condition | Action |
|-----------|--------|
| `coating_age_years` > 10 AND `coating_system` in {EPOXY_HT_MULTI, EPOXY_HT_SINGLE} | Treat as degraded downstream (metadata unchanged) |

---

## Tier 2 — conditional weights (used by generator)

### `R-INSMAT-W-01` — `insulation_material`

**Source:** API 583 Table 4.3 `[CITATION_TBC]`; NACE SP0198-2010 Table 1 `[CITATION_TBC]`; `[ENGINEERING_JUDGEMENT]` weights

| # | Condition | FOAMGLASS | MINERAL_WOOL | FIBERGLASS | CALCIUM_SILICATE | PERLITE | UNKNOWN | ASBESTOS |
|---|-----------|-----------|--------------|------------|------------------|---------|---------|----------|
| 1 | MARINE | 0.40 | 0.30 | 0.10 | 0.10 | 0.05 | 0.04 | 0.01 |
| 2 | ARID_DRY | 0.15 | 0.35 | 0.15 | 0.24 | 0.05 | 0.04 | 0.01 |
| 3 | SEVERE | 0.30 | 0.35 | 0.15 | 0.09 | 0.05 | 0.04 | 0.01 |
| 4 | Default | 0.25 | 0.40 | 0.15 | 0.11 | 0.04 | 0.03 | 0.01 |

*ASBESTOS column added June 2026 for dictionary alignment (near-zero legacy prevalence).*

---

### `R-COAT-W-01` — `coating_system`

Allowed generated types: **TSA, IOZ, EPOXY_HT_MULTI, EPOXY_HT_SINGLE, BARE, UNKNOWN** (not `EPOXY_AGED`).

**Source:** API 583 Table 4.4 `[CITATION_TBC]`; API 581 coating modifier `[CITATION_TBC]`; `[ENGINEERING_JUDGEMENT]` weights

| # | Condition | TSA | IOZ | EPOXY_HT_MULTI | EPOXY_HT_SINGLE | BARE | UNKNOWN |
|---|-----------|-----|-----|----------------|-----------------|------|---------|
| 1 | years since commissioning ≤ 10, MARINE | 0.25 | 0.25 | 0.30 | 0.15 | 0.03 | 0.02 |
| 2 | years since commissioning > 25, MARINE | 0.10 | 0.10 | 0.05 | 0.05 | 0.65 | 0.05 |
| 3 | years since commissioning ≤ 10 | 0.15 | 0.20 | 0.30 | 0.30 | 0.03 | 0.02 |
| 4 | years since commissioning > 25 | 0.05 | 0.08 | 0.05 | 0.07 | 0.70 | 0.05 |
| 5 | Default | 0.10 | 0.15 | 0.20 | 0.20 | 0.30 | 0.05 |

---

### `R-INSCOND-W-01` — `insulation_condition`

**Source:** API 583 Section 5.3 `[CITATION_TBC]`; API 581 insulation age modifier `[CITATION_TBC]`; `[ENGINEERING_JUDGEMENT]` weights

| # | Condition | ABOVE_AVERAGE | AVERAGE | BELOW_AVERAGE |
|---|-----------|---------------|---------|---------------|
| 1 | `insulation_age_years` ≤ 5 | 0.65 | 0.30 | 0.05 |
| 2 | `insulation_age_years` > 15, MARINE | 0.10 | 0.35 | 0.55 |
| 3 | `insulation_age_years` > 15 | 0.15 | 0.45 | 0.40 |
| 4 | 5 < `insulation_age_years` ≤ 15 | 0.35 | 0.50 | 0.15 |
| 5 | Default | 0.30 | 0.50 | 0.20 |

---

### `R-CLAD-W-01` — `cladding_integrity`

**Source:** API 583 Section 5.3 `[CITATION_TBC]`; `[ENGINEERING_JUDGEMENT]` weights

| # | Condition | ABOVE_AVERAGE | AVERAGE | BELOW_AVERAGE |
|---|-----------|---------------|---------|---------------|
| 1 | years since commissioning ≤ 10 | 0.60 | 0.35 | 0.05 |
| 2 | years since commissioning > 20 | 0.15 | 0.45 | 0.40 |
| 3 | Default | 0.30 | 0.50 | 0.20 |

---

### `R-TRACE-W-01` — `tracing_system`

Allowed values: **NONE**, **HIGH_INTEGRITY_STEAM_TRACED**, **MEDIUM_INTEGRITY_STEAM_TRACED**, **POOR_INTEGRITY_STEAM_TRACED**, **ELECTRIC_TRACED**, **HOT_OIL_TRACED**.

**Source:** API 583 Section 4.3 `[CITATION_TBC]`; `[ENGINEERING_JUDGEMENT]` weights (steam band split)

| # | Condition | NONE | HI_STEAM | MED_STEAM | POOR_STEAM | ELECTRIC | HOT_OIL |
|---|-----------|------|----------|-----------|------------|----------|---------|
| 1 | `operating_temperature` < 10 °C | 0.40 | 0.10 | 0.15 | 0.10 | 0.20 | 0.05 |
| 2 | `operating_temperature` ≥ 60 °C | 0.90 | 0.02 | 0.02 | 0.01 | 0.03 | 0.02 |
| 3 | Default | 0.72 | 0.05 | 0.07 | 0.04 | 0.08 | 0.04 |

---

### `R-SWEAT-W-01` — `sweating_asset`

Boolean **`true`** / **`false`**. Drawn after `operating_temperature` is known (layer 5).

**Source:** Data dictionary `[CITATION_TBC]`; `[ENGINEERING_JUDGEMENT]` weights

| # | Condition | true | false | Note |
|---|-----------|------|-------|------|
| 1 | `operating_temperature` < 10 °C | 0.35 | 0.65 | Cold service |
| 2 | `operating_temperature` ≥ 60 °C | 0.05 | 0.95 | Hot service |
| 3 | Default | 0.15 | 0.85 | |

---

### `R-METAL-W-01` — `metallurgy_family`

Allowed: **CARBON_STEEL**, **LOW_ALLOY_STEEL**, **AUSTENITIC_SS**, **DUPLEX_SS** (not `NICKEL_ALLOY` or `OTHER`).

**Source:** ISO 14224:2016 Table A.41 `[CITATION_TBC]`; HOIS survey `[CITATION_TBC]`; `[ENGINEERING_JUDGEMENT]` weights

| # | Condition | CARBON_STEEL | LOW_ALLOY_STEEL | AUSTENITIC_SS | DUPLEX_SS |
|---|-----------|--------------|-----------------|---------------|-----------|
| 1 | SEVERE | 0.55 | 0.15 | 0.21 | 0.09 |
| 2 | Default | 0.74 | 0.12 | 0.10 | 0.04 |

---

## Citations to verify (backlog)

| Rule ID | Reference to verify |
|---------|---------------------|
| `R-CHLORIDE-01` | NACE SP0198-2010 §5.4; API 583 Table 4.2 |
| `R-COAT-DEFER-01` | API 583 coating age rule → `docs/synthetic_inputs_methodology.md` §6 |
| `R-SWEAT-W-01` | Data dictionary |
| `R-INSMAT-W-01` | API 583 Table 4.3; NACE SP0198-2010 Table 1 |
| `R-COAT-W-01` | API 583 Table 4.4; API 581 coating modifier |
| `R-INSCOND-W-01` | API 583 §5.3; API 581 insulation age modifier |
| `R-CLAD-W-01` | API 583 §5.3 |
| `R-TRACE-W-01` | API 583 §4.3 |
| `R-METAL-W-01` | ISO 14224:2016 Table A.41; HOIS survey |
| `R-PIPE-NPS-01` | ASME B36.10M; repo NPS PDF |

---

## Dictionary alignment (2026-06) — completed

The following items from the pre-alignment backlog are **done** in config, code, and tests:

| Topic | Status |
|-------|--------|
| Remove `OTHER` asset class | Done |
| Remove `NICKEL_ALLOY` / `OTHER` metallurgy | Done |
| Stop rewriting `coating_system` to `EPOXY_AGED` | Done — downstream rule only |
| `sweating_asset` bool in generator | Done |
| `tracing_system` six allowed values | Done |
| `PERLITE` spelling; `BELOW_AVERAGE` / `ABOVE_AVERAGE` condition enums | Done |
| `asset_commissioning_date`; `inspection_ever_done` | Done |
| Per-class diameter bands (dictionary) | Done |
| `SPHERICAL_SHELL` on `PRESSURE_VESSEL` | Done |

**Still open (not SME review):** regenerate committed sample CSV.

---

## SME feedback

| Section | Approved? | Comments |
|---------|-------------|----------|
| `R-CHLORIDE-01` | Approved | |
| `R-COAT-DEFER-01` | Approved | Some concerns regarding the Unknown option — if Unknown, the value should not be close to the worst case possible? Same comment for the remainder. |
| `R-INSMAT-W-01` | Approved | |
| `R-COAT-W-01` | Approved | |
| `R-INSCOND-W-01` | Approved | |
| `R-CLAD-W-01` | Approved | |
| `R-TRACE-W-01` | Approved | |
| `R-SWEAT-W-01` | Approved | |
| `R-METAL-W-01` | Approved | |
