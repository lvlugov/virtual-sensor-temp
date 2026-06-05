# Citations audit log

Named **standard and data-dictionary references** in config and docs: are they real, and do they say what we imply?

For **why a rule exists** (authority behind the rule), use **`rules_provenance.md`**.

**Verdict:** `pending` · `verified` · `wrong_locator` · `wrong_direction` · `not_in_standard` · `na_for_sampling` · `data_dictionary`

If the same table or section appears on several rows, verify it once and reuse the verdict.

---

## Log

| # | File | Where | Cited as | Exists? | What it actually says | Verdict | Action |
|---|------|-------|----------|---------|----------------------|---------|--------|
| 1 | `conditional_rules.yaml` | `R-CHLORIDE-01` source | Data dictionary; NACE SP0198 §5.4; API 583 Table 4.2 | | | `pending` | |
| 2 | `docs/downstream_product_semantics.md` | `R-COAT-DEFER-01` source | Data dictionary; API 583 coating age rule | | | `pending` | |
| 3 | `conditional_rules.yaml` | `R-INSMAT-W-01` source | API 583 Table 4.3; NACE SP0198 Table 1 | | | `pending` | |
| 4 | `conditional_rules.yaml` | `R-INSMAT-W-01` description | FOAMGLASS preferred in MARINE (closed cell) | | | `pending` | |
| 5 | `conditional_rules.yaml` | `R-COAT-W-01` source | API 583 Table 4.4; API 581 coating modifier | | | `pending` | |
| 6 | `conditional_rules.yaml` | `R-INSCOND-W-01` source | API 583 §5.3; API 581 insulation age modifier | | | `pending` | |
| 7 | `conditional_rules.yaml` | `R-INSCOND-W-01` description | Consistent with API 583 age bands | | | `pending` | |
| 8 | `conditional_rules.yaml` | `R-CLAD-W-01` source | API 583 §5.3 | | | `pending` | |
| 9 | `conditional_rules.yaml` | `R-TRACE-W-01` source | API 583 §4.3 (~20–30% traced piping) | | | `pending` | |
| 10 | `conditional_rules.yaml` | `R-SWEAT-W-01` source | Data dictionary | | | `pending` | |
| 11 | `conditional_rules.yaml` | `R-METAL-W-01` source | ISO 14224 Table A.41; HOIS survey | | | `pending` | |
| 12 | `conditional_rules.yaml` | `R-PIPE-NPS-01` | ASME B36.10M; repo NPS PDF | | | `pending` | |
| 13 | `schema.yaml` | `asset_class` standards | ISO 14224 Table 5; API 583 Table 4.1 | | | `pending` | |
| 14 | `schema.yaml` | `exposure_zone` standards | ISO 9223 C1–C5; API 583 Table 4.2; NACE SP0198 | | | `pending` | |
| 15 | `schema.yaml` | `metallurgy_family` standards | ISO 14224 A.41; API 581; API 583 Table 4.1; NACE SP0198 | | | `pending` | |
| 16 | `schema.yaml` | `asset_age` standards | API 581 m_age; API 583 §5.2 | | | `pending` | |
| 17 | `schema.yaml` | `geometry_class` standards | API 581 m_geom; API 583 §5.4; NACE SP0198 | | | `pending` | |
| 18 | `schema.yaml` | `geometry_complexity` standards | API 583 §5.4 | | | `pending` | |
| 19 | `schema.yaml` | `orientation` standards | ISO 14224 A.40; API 583 §5.3 | | | `pending` | |
| 20 | `schema.yaml` | `shelter_flag` standards | API 583 §4.4 | | | `pending` | |
| 21 | `schema.yaml` | `tracing_system` standards | API 583 §4.3; NACE SP0198 | | | `pending` | |
| 22 | `schema.yaml` | `component_diameter` standards | ISO 14224 A.43 | | | `pending` | |
| 23 | `schema.yaml` | `furnished_thickness` standards | ISO 14224 A.43; API 581 DF calculation | | | `pending` | |
| 24 | `schema.yaml` | `insulation_material` standards | API 583 Table 4.3; NACE SP0198 Table 1 | | | `pending` | |
| 25 | `schema.yaml` | `insulation_thickness` standards | API 583; NACE SP0198 | | | `pending` | |
| 26 | `schema.yaml` | `insulation_install_date` standards | API 583 §5.2; API 581 | | | `pending` | |
| 27 | `schema.yaml` | `coating_application_date` standards | API 583; API 581 m_coat derivation | | | `pending` | |
| 28 | `schema.yaml` | `coating_system` standards | API 583 Table 4.4; NACE §5.5; API 581 | | | `pending` | |
| 29 | `schema.yaml` | `coating_system` notes | m_coat values TSA 0.4 … BARE 2.5 attributed to API 583 / NACE / API 581 | | | `pending` | |
| 30 | `schema.yaml` | `inspection_record_dates` standards | ISO 14224 Table 5; API 581 DF_insp; API 583 | | | `pending` | |
| 31 | `schema.yaml` | `operating_temperature` standards | ISO 14224 A.43; API 583; API 581; NACE SP0198 | | | `pending` | |
| 32 | `schema.yaml` | `min_operating_temperature` standards | API 583; NACE cycling grade thresholds | | | `pending` | |
| 33 | `schema.yaml` | `max_operating_temperature` standards | API 583; API 581; NACE SP0198 | | | `pending` | |
| 34 | `schema.yaml` | `avg_cycles_per_quarter` standards | API 583 §5.5; NACE SP0198 | | | `pending` | |
| 35 | `schema.yaml` | `operation_vs_shutdown_fraction` standards | API 581; ISO 9223; API 583 | | | `pending` | |
| 36 | `schema.yaml` | `insulation_chloride_flag` standards | NACE §5.4; API 583 Table 4.2 | | | `pending` | |
| 37 | `schema.yaml` | `insulation_condition` standards | NACE SP0198; API 583 §5.3; API 581 | | | `pending` | |
| 38 | `schema.yaml` | `cladding_integrity` standards | API 583 §5.3; NACE SP0198 | | | `pending` | |
| 39 | `schema.yaml` | `last_inspection_thickness` standards | ISO 14224 Table 5; API 581 UT trend slope | | | `pending` | |
| 40 | `schema.yaml` | `washdown_records` standards | API 583 §5.2 | | | `pending` | |
| 41 | `synthetic_inputs_methodology.md` | §5 asset proportions | HOIS surveys; API 583 Table 4.1; ISO 14224 Table A.4 | | | `pending` | |
| 42 | `synthetic_inputs_methodology.md` | §6 `R-CHLORIDE-01` | NACE §5.4; API 583 Table 4.2; data dictionary | | | `pending` | |
| 43 | `docs/downstream_product_semantics.md` | R-COAT-DEFER-01; methodology §6 coating defer | API 583 coating age; EPOXY_AGED generation debt | | | `pending` | |
| 44 | `synthetic_inputs_methodology.md` | §6 Tier 2 rule IDs | Directional effects — see R-INSMAT-W-01 … R-METAL-W-01 | | | `pending` | |
| 45 | `conditional_rules_sme_review.md` | Rule IDs R-CHLORIDE-01 … R-PIPE-NPS-01 | Same sources as rows 1–12 above | | | `pending` | |

---

## Unique locators (verify once, apply to all rows that cite them)

| Document | Locator | Rows using it | Exists? | Notes | Verdict |
|----------|---------|---------------|---------|-------|---------|
| API 583 | Table 4.1 | 13, 15, 41 | | | `pending` |
| API 583 | Table 4.2 | 1, 14, 36, 42 | | | `pending` |
| API 583 | Table 4.3 | 3, 24 | | | `pending` |
| API 583 | Table 4.4 | 5, 28 | | | `pending` |
| API 583 | §4.3 | 9, 21 | | | `pending` |
| API 583 | §4.4 | 20 | | | `pending` |
| API 583 | §5.2 | 16, 26, 40 | | | `pending` |
| API 583 | §5.3 | 6–8, 19, 37, 38 | | | `pending` |
| API 583 | §5.4 | 17, 18 | | | `pending` |
| API 583 | §5.5 | 28, 34 | | | `pending` |
| API 583 | Coating age rule (unspecified) | 2, 43 | | | `pending` |
| API 581 | (document / named modifiers) | 5, 6, 15–17, 23, 27–31, 33–35, 39 | | | `pending` |
| NACE SP0198 | §5.4 | 1, 36, 42 | | | `pending` |
| NACE SP0198 | Table 1 | 3, 24 | | | `pending` |
| NACE SP0198 | Cycling thresholds | 32 | | | `pending` |
| ISO 14224 | Table 5 | 13, 30, 39 | | | `pending` |
| ISO 14224 | Table A.4 | 41 | | | `pending` |
| ISO 14224 | Table A.40 | 19 | | | `pending` |
| ISO 14224 | Table A.41 | 11, 15 | | | `pending` |
| ISO 14224 | Table A.43 | 22, 23, 31 | | | `pending` |
| ISO 9223 | Categories C1–C5 | 14, 35 | | | `pending` |
| HOIS | Survey reports | 11, 41 | | | `pending` |
| ASME B36.10M | Pipe dimensions | 12 | | | `pending` |
| Data dictionary | Product field definitions | 1, 2, 10 | | | `pending` |
