# Citation verification — LLM prompt templates

Copy-paste these prompts into **Claude** or **Gemini** with the listed PDF attached. Replace `{EDITION}` with the year on your cover sheet (e.g. API 583:2014).

**Fill results in:** `docs/citations_audit.md` (citation log).

Use the **Unique locators** table first, then the numbered **Log** rows.

**Instructions for the model (prepend once per chat):**

```text
You are auditing standard citations for a synthetic dataset config. Use ONLY the attached PDF(s). For each question:
1) State whether the locator exists (yes/no).
2) Give the official table/section title.
3) Quote at most 2 sentences with page number.
4) Answer whether the quote supports OUR claim (yes/no/partial/not mentioned).
5) Do not invent table numbers. If not found, say "not found".
Do not justify probability weights (0.40, 0.65, etc.) from the standard unless the text literally gives frequencies.
```

---

## Session A — Data dictionary (LOC-32)

**Attach:** data dictionary PDF only.

```text
Audit IDs: CR-01, CR-02, CR-08; LOC-32.

CR-01: Does the data dictionary define insulation_chloride_flag with an auto-flag when exposure is marine, insulation is calcium silicate, and insulation age > 5 years? Quote Edge Cases / constraints.

CR-02: What does the data dictionary say about coating age > 10 years and EPOXY_HT_* types? Quote. (Do not assume a scorer exists — dictionary text only.)

CR-08: Is there a field sweating_asset (or equivalent)? Quote definition.

LOC-32: Summarise dictionary as authority for which CR rows.

Verdicts: verified / superseded_by_data_dictionary / not_in_standard.
```

---

## Session I — API 583 locator batch (LOC index) {EDITION}

**Attach:** API 583 PDF. **Goal:** Fill LOC-02, LOC-08, LOC-10, LOC-12, LOC-13, LOC-14, LOC-17, LOC-19, LOC-21, LOC-22, LOC-28, LOC-29 in one pass.

```text
Using only API 583, for EACH locator below: exists (y/n), official title, ≤2 sentence quote with page, suggested_verdict.

LOC-02: Table 4.2
LOC-08: Section 5.2
LOC-10: Section 5.4
LOC-12: Section 5.3
LOC-13: Section 4.4
LOC-14: Section 4.3 — include whether "20-30% traced piping" appears
LOC-17: Table 4.3
LOC-19: (document-level) what topics does API 583 cover — NOT a substitute for specific locators
LOC-21: Table 4.4 — coating types / susceptibility factors / numeric modifiers?
LOC-22: Section 5.5
LOC-28: Table 4.1 — equipment classes / CUI relevance?
LOC-29: any "coating age" / organic coating >10 yr rule (give section if found)

Return table: loc_id | exists | actual_topic | quote_page | suggested_verdict
Then map which CR/SC rows depend on each loc_id (from register).
```

---

## Session B — API 583 (CR detail, after Session I)

**Attach:** API 583 PDF.

```text
Using only API 583, answer CR-specific claims. If Session I already filled a LOC row, reference it and only answer "supports_claim" for the CR wording.

CR-01: Does combined evidence support deterministic chloride flag for MARINE + calcium silicate + age > 5 years? (Table 4.2 + any §5.x)

CR-03: Directional: FOAMGLASS/closed-cell preferred in wet marine? (Table 4.3) — NOT probabilities.

CR-04: Does Table 4.4 mention coating types and numeric factors? Do NOT assume our schema m_coat numbers come from this table unless quoted.

CR-05 / CR-06: §5.3 — insulation condition vs cladding — separate variables?

CR-07: §4.3 — 20–30% tracing statistic? steam integrity bands vs our enum labels?

CR-02: Does API 583 support coating age > 10 yr rule as written in conditional_rules.yaml? (Dictionary may own this — see Session A.)

Return: audit_id | supports_claim | na_for_sampling (y/n) | suggested_verdict | notes
```

---

## Session C — NACE / AMPP SP0198 {EDITION}

**Attach:** SP0198 PDF (note exact revision on cover).

```text
Using only SP0198:

CR-01: Does Section 5.4 exist? Subject matter? Support for chloride risk with calcium silicate insulation in wet/marine environments and time in service?

CR-03: Does Table 1 exist? What is its title? Does it list insulation materials with guidance that supports FOAMGLASS/closed-cell preference in wet environments? Any probabilities?

CR-07 (if cited in schema for tracing_system): Any section linking heat tracing prevalence to operating conditions? Quote.

Return table: audit_id | locator | exists | topic | supports_claim | suggested_verdict
```

---

## Session D — API 581 {EDITION}

**Attach:** API 581 PDF.

```text
Using only API 581:

CR-04: Is there a named "coating modifier" or coating-type susceptibility table matching TSA, IOZ, epoxy, bare? Or is API 581 about RBI planning rather than coating type frequencies?

CR-05: Is there a named "insulation age modifier" tied to GOOD/AVERAGE/POOR insulation condition? Quote locator or say not found.

Clarify for each: does API 581 actually define the named modifiers in our schema strings (m_age, m_geom, DF_insp, insulation age modifier, UT trend)? Or are those labels our paraphrase?

Return table: audit_id | claim | exists | quote/page | na_for_sampling (y/n) | suggested_verdict
```

---

## Session E — ISO 14224:2016

**Attach:** ISO 14224 PDF.

```text
CR-09: Does Table A.41 exist? What is its official title/subject? Does it provide metallurgy family fractions (carbon steel, austenitic SS, duplex) conditional on exposure environment MARINE/SEVERE/TEMPERATE? Quote or say not mentioned.

Return: exists, actual_subject, supports_metallurgy_weights (y/n), suggested_verdict (expect na_for_sampling if no probabilities).
```

---

## Session F — HOIS (if available)

**Attach:** HOIS survey report.

```text
CR-09: Find statistics on metallurgy or material of construction for insulated equipment in upstream O&G. Can we cite "carbon steel dominant" with a specific table/figure and year? Does HOIS break down by exposure zone matching our exposure_zone enum?

If document not available, state "cannot verify".
```

---

## Session G — NPS / ASME B36.10M (CR-10)

**Attach:** `NPS-nominal-pipe-size-chart-inches__1_.pdf` and/or ASME B36.10M.

```text
CR-10: Spot-check NPS 2, 4, 6, 12, 24 Schedule 40: compare od_mm and wall_mm in our YAML catalog (geometry_standards.pipe_nps.nps_catalog) to the standard/chart. List any mismatches > 0.1 mm.

Does ASME B36.10M support the document title on our repo PDF?

Verdict: verified / wrong_locator / partial (list sizes wrong).

Do not evaluate nps_sampling_weights — those are engineering judgement.
```

---

## Session J — ISO 9223 and ISO 14224 {EDITION}

**Attach:** ISO 9223:2012 and ISO 14224:2016.

```text
ISO 9223 (LOC-03): Do categories C1–C5 exist? What do they classify? Any link to our exposure_zone enum (MARINE, ARID_DRY, SEVERE, TEMPERATE)?

ISO 14224:
LOC-01 Table 5 — subject? UT / inspection / reliability data?
LOC-05 Table A.41 — equipment taxonomy or material fractions?
LOC-11 Table A.40 — orientation?
LOC-15 Table A.43 — process / operating parameters?
LOC-27 Table A.4 — equipment population guidance for asset mix?

Return: loc_id | exists | actual_topic | supports_our_use (y/n) | suggested_verdict
```

---

## Session K — Methodology doc (DOC)

**Attach:** `docs/synthetic_inputs_methodology.md` + audit results from CR/DOC so far.

```text
Read methodology §5 asset proportions and §6 Tier 1/2 tables.

DOC-01: Are cited HOIS / API 583 Table 4.1 / ISO A.4 valid for asset CLASS MIX narrative?
DOC-03: Compare §6 Tier 1 coating row to conditional_rules.yaml CR-02 text — same rule, consistent wording? Flag document drift only.
DOC-04: Does Tier 2 list imply standards justify numeric weights?

Return: doc_id | issue | action (update text / remove citation / add footnote)
```

---

## Session H — Cross-check (optional second model)

**Attach:** same PDF as the row you distrust.

```text
Another model previously said:
[PASTE PRIOR ANSWER]

Independently verify using only the PDF:
- Locator exists?
- Quote with page
- Same verdict?

Audit ID: CR-XX
```

---

## Batch table template (paste back into citations_audit.md)

```markdown
| id | locator | exists | actual_topic | supports_claim | authority | suggested_verdict | page_quote |
|----|---------|--------|--------------|----------------|-----------|-------------------|------------|
| LOC-02 | API 583 Table 4.2 | | | | | | |
| CR-01 | (logic) | — | — | | | | |
| SC-23 | schema field | — | — | inherit LOC-02 | | | |
```

---

## After the LLM sessions

1. Transfer `suggested_verdict` → **Verdict** in `docs/citations_audit.md`.
2. Set **Action** on each row.
3. Request citation hygiene PR when the register is complete.

---

## Changelog

| Date | Notes |
|------|-------|
| 2026-06-03 | Prompts created for CR-01–CR-10 |
| 2026-06-03 | Full scope: Sessions I, J, K; register in `docs/` |
| 2026-06-03 | Removed Session L; scoring implementation out of scope |
