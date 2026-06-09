# Data dictionary alignment audit

**Dictionary source:** `lean_virtual_sensor/inputs_generation/data_dictionary_lvs_2026-06-09.csv`  
**Compared against:** `lean_virtual_sensor/inputs_generation/config/schema.yaml`, `asset_class_config.yaml`, `generation_config.yaml`, `conditional_rules.yaml`, generator code and tests  
**Created:** 2026-06-09  
**Status:** audit only — no repo changes applied yet

This document records differences between the product data dictionary (2026-06-09 export) and the synthetic inputs generator repo. Use it to plan incremental, testable alignment work.

---

## How to read this

The dictionary CSV has some **internal inconsistencies** (allowed-values column vs notes). Where that happens, both are noted and which side the repo currently follows is stated.

Synthetic generation **deliberately** fills all rows (no nulls) and adds `Asset` — those are scope choices, not necessarily defects.

---

## 1. Variable / column naming

| Data dictionary | Repo (`schema.yaml` / CSV) | Notes |
|-----------------|--------------------------|--------|
| `most_prevalent_geometry_class` | `geometry_class` | Same role; repo uses shorter name and `SNAKE_CASE` tokens |
| `latest_inspection_date` | `inspection_record_dates` | Same role; repo stores single most-recent date for synthetic rows |
| — | `Asset` | Synthetic ID only; not in dictionary (expected) |

---

## 2. Allowed values — repo has extra values (not in dictionary)

| Variable | In dictionary | Extra in repo | Where |
|----------|---------------|---------------|--------|
| `asset_class` | 7 classes (no `OTHER`) | **`OTHER`** | `schema.yaml`, `generation_config.yaml` (30 rows), `asset_class_config.yaml` |
| `metallurgy_family` | 4 families only | **`NICKEL_ALLOY`**, **`OTHER`** | `schema.yaml`, `generation_config.yaml` op-temp ranges |
| `geometry_class` | 9 types (incl. spherical) | **`SPHERICAL_SHELL`** in schema only | In `schema.yaml` `allowed_values` but **not** in any `geometry_class_allowed` — never generated |

**Generator behaviour today:** `R-METAL-W-01` only weights the four dictionary families, so `NICKEL_ALLOY` / `OTHER` metallurgy should not appear in output even though schema allows them. `OTHER` asset class **does** appear (30 rows).

---

## 3. Allowed values — repo is missing dictionary values

| Variable | In dictionary, not in repo | Notes |
|----------|---------------------------|--------|
| `insulation_material` | **`ASBESTOS`** | Dictionary allows it; `schema.yaml` explicitly excludes it from synthetic generation |

---

## 4. Allowed values — dictionary CSV is stale; repo matches notes, not allowed column

| Variable | Dictionary `Allowed Values` column | Dictionary notes (authoritative intent) | Repo |
|----------|-----------------------------------|----------------------------------------|------|
| `insulation_condition` | `BELOW_AVERAGE` / `AVERAGE` / `ABOVE_AVERAGE` | **“NAMING FIXED … GOOD / AVERAGE / POOR”** | `GOOD`, `AVERAGE`, `POOR` — aligned with notes |
| `cladding_integrity` | Same old three values | No “naming fixed” note; edge-case text still uses old framing | `GOOD`, `AVERAGE`, `POOR` — repo ahead of dictionary allowed column |

**Conclusion:** Repo matches the `insulation_condition` fix in dictionary notes. Cladding is likely intended to use the same NACE vocabulary but the dictionary allowed-values cell was not updated.

---

## 5. `PEARLITE` vs `PERLITE`

The data dictionary uses **`PEARLITE`** (same spelling as the repo). A PR comment preferring `PERLITE` does **not** match this dictionary export. If renamed, it would be a **joint** dictionary + repo change, not “fix repo to match dictionary” alone.

---

## 6. `coating_system` / `EPOXY_AGED`

| Aspect | Data dictionary | Repo |
|--------|-----------------|------|
| Allowed values | Includes `EPOXY_AGED` | Includes `EPOXY_AGED` in `schema.yaml` |
| Trailing note in CSV | **“remove EPOXY AGED”** | Still present in dictionary row |
| Auto-downgrade | “reclassify to `EPOXY_AGED` **in model calculation**” (edge cases / linked variables) | **Rewrites CSV** in `generate_dates` (interim Option B; `R-COAT-DEFER-01` deferred) |

The dictionary is moving toward **no `EPOXY_AGED` in stored data**; the repo still stores it and generates it.

---

## 7. Fields in dictionary but not in generator scope

Correctly excluded in `schema.yaml` `excluded_variables` (or not implemented):

| Dictionary variable | Repo status |
|--------------------|-------------|
| `T_ambient(t)`, `RH(t)`, `rainfall(t)`, `T_process(t)` | Excluded — time-series module |
| `tracing_active` (bool companion to `tracing_system`) | **Not in repo** — mentioned in dictionary linked variables only |

---

## 8. Metadata / grouping mismatches (non-blocking)

| Variable | Dictionary group | Repo `schema.yaml` group |
|----------|------------------|--------------------------|
| `sweating_asset` | Environment & Exposure | Process Conditions |
| `tracing_system` | Process Conditions | Process Conditions (layer 5) |
| `cladding_integrity` | Insulation | **Coating** (likely copy-paste error in schema) |
| `shelter_flag` | Environment & Exposure | Environment & Exposure (layer 2 in schema) |

---

## 9. `sweating_asset` definition in dictionary

Dictionary definition reads like the **opposite** of sweating:

> The asset's metal surface temperature **does not** drop below the local dew point, so atmospheric moisture **cannot** condense on it.

Repo notes describe sweating/condensation as a **moisture source for CUI**. Treat the dictionary **definition** as erroneous; bool semantics and generator rules are plausible.

---

## 10. Numeric ranges — aligned vs mismatched

### Aligned with dictionary

| Variable | Dictionary | Repo |
|----------|------------|------|
| `asset_age` | 0–80 | `[0, 80]` |
| `operating_temperature` | −100 to +500 °C | `[-100, 500]` |
| `avg_cycles_per_quarter` | 0–200 | `[0, 200]` |
| `operation_vs_shutdown_fraction` | 0.0–1.0 | `[0.0, 1.0]` |
| `insulation_thickness` | 20–300 mm | `[20, 300]` |
| `washdown_records` | 0–50 | `[0, 50]` |
| `last_inspection_thickness` | 1 mm – furnished | `>= 1.0` in constraints |
| `tracing_system` | Six integrity bands + electric/hot oil | Matches `schema.yaml` and `conditional_rules.yaml` |
| `PIPE` `component_diameter` | 25–1,200 mm | `25`–`1200` in `asset_class_config.yaml` |
| `PIPE` `furnished_thickness` | 3–50 mm (within 3–100) | `3`–`50` |

### Mismatched vs dictionary (`asset_class_config.yaml`)

| Asset class | Field | Dictionary | Repo |
|-------------|-------|------------|------|
| `HEAT_EXCHANGER` | `component_diameter` | 300–3,000 mm | **200–1,500** (min low, max low) |
| `STORAGE_TANK` | `component_diameter` | 600–50,000 mm | **1,000–30,000** (min high, max low) |
| `COLUMN` | `component_diameter` | (vessel band; not separate) | 300–5,000 — plausible |
| `AIR_COOLER` | `component_diameter` | (not split in dictionary row) | 25–200 — reasonable for fin-fan |

### Nullable / defaults (dictionary vs synthetic design)

Dictionary marks several fields as nullable (`operating_temperature`, `geometry_complexity`, `shelter_flag`, `washdown_records`, etc.). Repo sets `nullable: false` and fills every row — **intentional** for synthetic ML data (`docs/synthetic_inputs_methodology.md` §7).

---

## 11. Rules and semantics — aligned

| Rule | Dictionary | Repo |
|------|------------|------|
| Chloride auto-flag | MARINE + CALCIUM_SILICATE + insulation age > 5 yr | `R-CHLORIDE-01` in YAML + layer 6 |
| Coating age > 10 yr | Downgrade to degraded m_coat (model / notes) | Python rewrite to `EPOXY_AGED` in CSV |
| Inspection max lookback | 10 years default if never inspected | `inspection_age_max_years: 10` in `generation_config.yaml` |
| `insulation_chloride_flag` default | FALSE if empty | `default: false` |

---

## 12. Dictionary internal issues (fix in dictionary, not repo)

1. **`insulation_condition` / `cladding_integrity` allowed-values cells** — still `BELOW_AVERAGE` / `ABOVE_AVERAGE`; notes say GOOD/POOR for insulation.
2. **`coating_system` row** — stray “remove EPOXY AGED” text vs allowed list still containing `EPOXY_AGED`.
3. **`sweating_asset` definition** — inverted wording.
4. **`metallurgy_family` notes** — “use OTHER for rare alloys” but allowed list has only four values.

---

## 13. Suggested change batches (when implementing)

### Batch A — enum cleanup (matches dictionary 2026-06-09)

Remove `OTHER` asset class; remove `NICKEL_ALLOY` / `OTHER` metallurgy from schema + `generation_config`; decide on `SPHERICAL_SHELL` (add to a class or drop from schema).

### Batch B — dictionary stale cells

Confirm cladding uses GOOD/AVERAGE/POOR; update dictionary CSV allowed columns (product file, not necessarily repo).

### Batch C — `EPOXY_AGED`

Product decision: remove from stored enum + stop CSV rewrite (Option A) vs keep generator behaviour (Option B). See `docs/downstream_product_semantics.md` and `local_reference/code_restructuring.md` §7.

### Batch D — physical ranges

Align `HEAT_EXCHANGER` and `STORAGE_TANK` diameter bounds in `asset_class_config.yaml`.

### Batch E — naming (optional, cross-cutting)

`geometry_class` ↔ `most_prevalent_geometry_class`, `inspection_record_dates` ↔ `latest_inspection_date` — only if downstream consumers need exact dictionary names.

### Batch F — `ASBESTOS`

Keep excluded from synthetic data unless legacy rows are explicitly required.

---

## 14. Overall verdict

The repo is **broadly aligned** with the **intent** of the 2026-06-09 dictionary (tracing bands, coating types, GOOD/POOR insulation condition, chloride rule, temperature ranges).

Clear **gaps** remain:

- `OTHER` asset class
- Extra metallurgy enums in schema/config
- `EPOXY_AGED` in CSV vs dictionary direction to remove it
- Some diameter ranges (`HEAT_EXCHANGER`, `STORAGE_TANK`)
- `ASBESTOS` not in schema (by design)
- `tracing_active` missing
- Column renames (`geometry_class`, `inspection_record_dates`)

Pick one batch from §13 per PR; run `make test-dataset` after any semantic change that affects CSV output.

---

## Related references

- Dictionary file: `lean_virtual_sensor/inputs_generation/data_dictionary_lvs_2026-06-09.csv`
- Master variable registry (in-repo): `lean_virtual_sensor/inputs_generation/config/schema.yaml`
- Restructuring backlog: `local_reference/code_restructuring.md` §13
- Coating deferral: `docs/downstream_product_semantics.md`
