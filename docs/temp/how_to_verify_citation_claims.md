# How to verify citation claims (LLM workflow)

Instructions for **you + Claude/Gemini + PDFs**.

| Log | File | Job |
|-----|------|-----|
| **Citations** | `docs/citations_audit.md` | Check named standards / locators |
| **Provenance** | `docs/rules_provenance.md` | Record what owns each rule (dictionary, judgement, survey, …) |

LLM prompts in this folder apply mainly to the **citations** log. **Provenance** rows are filled from the data dictionary, SME review, and your conclusions after citation checks.

**Goal (citations):** Each cited table/section exists and is fairly described. Tier 2 **weights** stay engineering judgement unless a standard literally gives frequencies.

---

## What you need

1. **`docs/citations_audit.md`** — fill verdicts here (committed with the repo)
2. **`docs/temp/citation_verification_llm_prompts.md`** — copy-paste prompts
3. Standard PDFs + data dictionary (see [Documents to upload](#documents-to-upload))
4. Optional: PR reviewer / SME for rows marked `wrong_direction`

You do **not** need to validate Tier 2 **numeric weights** (0.40, 0.65, etc.) against standards.

---

## What you are verifying (four layers)

| Layer | Question | Typical outcome for Tier 2 weights |
|-------|----------|-----------------------------------|
| **1. Locator** | Does “Table 4.3” / “§5.4” exist in **that edition**? | `verified` or `wrong_locator` |
| **2. Content** | What does that section actually say? | Quote + short paraphrase |
| **3. Relevance** | Does it support **our written claim**? | `verified`, `wrong_direction`, or `not_in_standard` |
| **4. Sampling** | Does it give **probabilities** for synthetic data? | Almost always **`na_for_sampling`** |

---

## Documents to upload

| Priority | Document | Used for |
|----------|----------|----------|
| 1 | **Data dictionary** | CR-01, CR-02, CR-08; LOC-32 |
| 2 | **API 583** (edition on cover) | LOC/API sessions; most CR rows |
| 3 | **AMPP / NACE SP0198** | LOC-04, LOC-18, LOC-24, etc. |
| 4 | **API 581** | LOC-06 … LOC-26 (check: RBI doc vs our modifier **names** in schema) |
| 5 | **ISO 14224:2016** | LOC-01, LOC-05, LOC-11, LOC-15, LOC-27 |
| 6 | **ISO 9223:2012** | LOC-03 |
| 7 | **HOIS** report (if cited) | LOC-30 |
| 8 | **NPS PDF** (repo root) | CR-10 / LOC-31 |

If a document is missing, mark rows `cannot_verify` — do not guess.

---

## Workflow

### Citations log

1. Open **`docs/citations_audit.md`**.
2. Use **`docs/temp/citation_verification_llm_prompts.md`** with one PDF per chat.
3. Fill **Unique locators**, then **Log** rows.

### Provenance log

1. Open **`docs/rules_provenance.md`**.
2. For each P- row, set **Authority** and **Evidence** (dictionary section, SME note, survey report, or “see citations log #N if `standard`”).
3. Mark **SME OK?** when reviewed.

Update config/docs only when both logs are ready enough for the change you want (separate step, when you ask).

---

## Verdict glossary

| Verdict | Meaning |
|---------|---------|
| `pending` | Not yet checked |
| `verified` | Locator exists; supports the **specific** written claim |
| `wrong_locator` | Table/section wrong or missing |
| `wrong_direction` | Locator exists but contradicts our description |
| `not_in_standard` | Topic not in that document |
| `na_for_sampling` | Standard does not define generation weights |
| `superseded_by_data_dictionary` | Product data dictionary owns the rule |

**Authority (after audit):** `data_dictionary` | `standard` | `engineering_judgement` | `unclear`

---

## LLM rules of thumb

1. Require **page or table** in every answer.
2. **Existence before interpretation.**
3. Paste the **exact claim** from the register.
4. Do not justify **0.40 / 0.30** from standards.
5. For API 581, ask what the document **actually** contains — do not assume it matches schema modifier labels.

---

## After verification (when you request implementation)

Hygiene updates may touch `conditional_rules.yaml`, `schema.yaml`, and `docs/` — **only using filled rows in `docs/citations_audit.md`**, not before.

Separate from citation work: weight changes, scoring design, CSV regeneration.

---

## Related files

| File | Location |
|------|----------|
| Citations log | `docs/citations_audit.md` |
| Provenance log | `docs/rules_provenance.md` |
| This guide | `docs/temp/how_to_verify_citation_claims.md` |
| LLM prompts | `docs/temp/citation_verification_llm_prompts.md` |
