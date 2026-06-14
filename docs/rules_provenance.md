# Rules provenance log

What **actually justifies** each generation rule or design choice — not what we **cited** in a footnote. For standard names and PDF checks, use **`citations_audit.md`**.

Rule definitions live in **`conditional_rules.yaml`**. Downstream-only rules (e.g. `R-COAT-DEFER-01`) are in **`docs/synthetic_inputs_methodology.md`** §6 and the SME pack. This table references **rule IDs** only — not duplicated rule text.

**Authority (pick one per row):**

| Value | Meaning |
|-------|---------|
| `data_dictionary` | Product data dictionary |
| `engineering_judgement` | Assumption for synthetic data; SME may calibrate |
| `industry_survey` | Published survey (name + year in Evidence) |
| `product_logic` | Follows from field definitions / constraints in schema |
| `standard` | Grounded in a verified standard — see citations log row |
| `unclear` | Needs SME or dictionary decision |

**SME OK?** `pending` · `yes` · `no` · `n/a`

---

## Tier 1 — deterministic rules

| # | Rule ID | Claim | Authority | Evidence | Citations log | SME OK? |
|---|---------|-------|-----------|----------|---------------|---------|
| P-01 | `R-CHLORIDE-01` | MARINE + CALCIUM_SILICATE + insulation age > 5 yr → flag true | `data_dictionary` | Dictionary edge cases | 1, 36 | `yes` |

---

## Downstream / deferred (not in generator config)

| # | Rule ID | Claim | Authority | Evidence | Citations log | SME OK? |
|---|---------|-------|-----------|----------|---------------|---------|
| P-02 | `R-COAT-DEFER-01` | Epoxy types + coating age > 10 yr → degraded susceptibility downstream; generator stores `EPOXY_HT_*` as drawn | `data_dictionary` | `docs/synthetic_inputs_methodology.md` §6 | 2, 43 | `yes` |

Documented in **`docs/synthetic_inputs_methodology.md`** §6 and SME pack.

---

## Tier 2 — conditional weights

Weights are **`engineering_judgement`** unless you record otherwise. Directional story may reference standards — check citations log, not this table.

| # | Rule ID | Variable | Claim (direction, not numbers) | Authority | Evidence | Citations log | SME OK? |
|---|---------|----------|-------------------------------|-----------|----------|---------------|---------|
| P-03 | `R-INSMAT-W-01` | `insulation_material` | Material mix varies by exposure zone | `engineering_judgement` | SME pack `2026-05-29-sme-draft-6` | 3, 4, 24 | `yes` |
| P-04 | `R-COAT-W-01` | `coating_system` | Coating type mix varies by asset age and exposure | `engineering_judgement` | SME pack `2026-05-29-sme-draft-6` | 5, 28 | `yes` |
| P-05 | `R-INSCOND-W-01` | `insulation_condition` | Condition worsens with insulation age / marine exposure | `engineering_judgement` | SME pack `2026-05-29-sme-draft-6` | 6, 7, 37 | `yes` |
| P-06 | `R-CLAD-W-01` | `cladding_integrity` | Cladding worsens with asset age | `engineering_judgement` | SME pack `2026-05-29-sme-draft-6` | 8, 38 | `yes` |
| P-07 | `R-TRACE-W-01` | `tracing_system` | Tracing more likely on cold service; rare on hot | `engineering_judgement` | SME pack `2026-05-29-sme-draft-6` | 9, 21 | `yes` |
| P-08 | `R-SWEAT-W-01` | `sweating_asset` | Sweating more likely on cold service | `engineering_judgement` | SME pack `2026-05-29-sme-draft-6` | 10 | `yes` |
| P-09 | `R-METAL-W-01` | `metallurgy_family` | CS dominant; more SS in severe exposure | `engineering_judgement` | SME pack `2026-05-29-sme-draft-6` | 11, 15 | `yes` |

---

## Geometry (`conditional_rules.yaml`)

| # | Rule ID | Claim | Authority | Evidence | Citations log | SME OK? |
|---|---------|-------|-----------|----------|---------------|---------|
| P-10 | `R-PIPE-NPS-01` | PIPE diameter/wall from NPS catalog, not uniform min/max | `standard` | ASME B36.10M; `component_geometry_sizing.md` | 12 | `pending` |

---

## Schema constraints (no rule ID — product logic)

| # | Constraint | Claim | Authority | Evidence | Citations log | SME OK? |
|---|------------|-------|-----------|----------|---------------|---------|
| P-11 | Date chain | All dates within asset lifetime; install ≤ inspection | `product_logic` | `schema.yaml` layer 4 | — | `pending` |
| P-12 | Temperature triplet | min ≤ operating ≤ max | `product_logic` | `schema.yaml` layer 5 | — | `pending` |
| P-13 | Wall thickness | last_inspection_thickness ≤ furnished_thickness ≥ 1.0 | `product_logic` | `schema.yaml` | — | `pending` |
| P-14 | Age chain | Years since commissioning ≥ insulation and coating ages | `product_logic` | `schema.yaml`; `asset_commissioning_date` | — | `yes` |
| P-15 | `coating_system` notes | Numeric m_coat ladder (0.4 … 2.5) | | | 29 | `pending` |

---

## Generation config (`generation_config.yaml`)

| # | Parameter | Claim | Authority | Evidence | Citations log | SME OK? |
|---|-----------|-------|-----------|----------|---------------|---------|
| P-16 | `asset_class_proportions` | Class counts (PIPE 38%, etc.) for ML diversity | | | 41 | `pending` |
| P-17 | `exposure_zone_weights` | Zone mix for synthetic portfolio | `engineering_judgement` | Comment in YAML | — | `pending` |
| P-18 | `operating_temperature_ranges` | °C ranges by metallurgy | `engineering_judgement` | Comment in YAML | 31–33 | `pending` |
| P-19 | `date_generation` | Inspection / insulation / coating date draw bounds | `engineering_judgement` | Comment in YAML | — | `pending` |
| P-20 | Wall loss Beta | last_inspection_thickness from Beta(1.5, 8) | `engineering_judgement` | Methodology §9 | — | `pending` |
| P-21 | No nulls | Synthetic rows fully populated | `product_logic` | Methodology §7 | — | `pending` |

---

## Layer 2 draws (`asset_class_config.yaml`)

| # | Area | Claim | Authority | Evidence | Citations log | SME OK? |
|---|------|-------|-----------|----------|---------------|---------|
| P-22 | Per-class geometry, orientation, etc. | Allowed values and weights by asset class | `engineering_judgement` | `asset_class_config.yaml` | — | `pending` |
| P-23 | Diameter / wall (non-PIPE) | Triangular diameter at representative size; wall coupled via `t/D` | `engineering_judgement` | `component_geometry_sizing.md`; ASME VIII / API 650 informed | — | `pending` |

---

## Document consistency

| # | Topic | Claim | Authority | Evidence | Citations log | SME OK? |
|---|-------|-------|-----------|----------|---------------|---------|
| P-24 | Methodology §6 vs coating semantics | Generator stores coating as recorded; degradation downstream only | `product_logic` | `docs/synthetic_inputs_methodology.md` §6 | 43 | `yes` |
| P-25 | SME pack vs conditional rules | Same rule IDs and sources as YAML; synced 2026-06-14 | `product_logic` | `docs/conditional_rules_sme_review.md` | 45 | `yes` |
