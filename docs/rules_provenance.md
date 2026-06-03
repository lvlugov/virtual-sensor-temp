# Rules provenance log

What **actually justifies** each generation rule or design choice — not what we **cited** in a footnote. For standard names and PDF checks, use **`citations_audit.md`**.

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

## Tier 1 — deterministic rules (`conditional_rules.yaml`)

| # | Rule | Claim | Authority | Evidence | Citations log | SME OK? |
|---|------|-------|-----------|----------|---------------|---------|
| P-01 | `insulation_chloride_flag` | MARINE + CALCIUM_SILICATE + insulation age > 5 yr → flag true | | | 1, 36 | `pending` |
| P-02 | `coating_system_age_degradation` | Epoxy types + coating age > 10 yr → treat as degraded (`applies_at: scoring` in YAML) | | | 2, 43 | `pending` |

---

## Tier 2 — conditional weights (`conditional_rules.yaml`)

Weights are **`engineering_judgement`** unless you record otherwise. Directional story may reference standards — check citations log, not this table.

| # | Block | Claim (direction, not numbers) | Authority | Evidence | Citations log | SME OK? |
|---|-------|-------------------------------|-----------|----------|---------------|---------|
| P-03 | `insulation_material` | Material mix varies by exposure zone | | | 3, 4, 24 | `pending` |
| P-04 | `coating_system` | Coating type mix varies by asset age and exposure | | | 5, 28 | `pending` |
| P-05 | `insulation_condition` | Condition worsens with insulation age / marine exposure | | | 6, 7, 37 | `pending` |
| P-06 | `cladding_integrity` | Cladding worsens with asset age | | | 8, 38 | `pending` |
| P-07 | `tracing_system` | Tracing more likely on cold service; rare on hot | | | 9, 21 | `pending` |
| P-08 | `sweating_asset` | Sweating more likely on cold service | | | 10 | `pending` |
| P-09 | `metallurgy_family` | CS dominant; more SS in severe exposure | | | 11, 15 | `pending` |

---

## Geometry (`conditional_rules.yaml`)

| # | Block | Claim | Authority | Evidence | Citations log | SME OK? |
|---|-------|-------|-----------|----------|---------------|---------|
| P-10 | `geometry_standards.pipe_nps` | PIPE diameter/wall from NPS catalog, not uniform min/max | | | 12 | `pending` |

---

## Schema constraints (no `standards:` line — product logic)

| # | Constraint | Claim | Authority | Evidence | Citations log | SME OK? |
|---|------------|-------|-----------|----------|---------------|---------|
| P-11 | Date chain | All dates within asset lifetime; install ≤ inspection | `product_logic` | `schema.yaml` layer 4 | — | `pending` |
| P-12 | Temperature triplet | min ≤ operating ≤ max | `product_logic` | `schema.yaml` layer 5 | — | `pending` |
| P-13 | Wall thickness | last_inspection_thickness ≤ furnished_thickness ≥ 1.0 | `product_logic` | `schema.yaml` | — | `pending` |
| P-14 | Age chain | asset_age ≥ insulation and coating ages | `product_logic` | `schema.yaml` | — | `pending` |
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
| P-23 | Diameter / wall (non-PIPE) | Uniform in class min/max until NPS-style tables added | `engineering_judgement` | Methodology §12 limitation 2 | — | `pending` |

---

## Document consistency

| # | Topic | Claim | Authority | Evidence | Citations log | SME OK? |
|---|-------|-------|-----------|----------|---------------|---------|
| P-24 | Methodology §6 vs conditional rules | Tier 1 coating / EPOXY_AGED wording aligned | | | 43 | `pending` |
| P-25 | SME pack vs conditional rules | Same rules and sources as YAML | | | 45 | `pending` |
