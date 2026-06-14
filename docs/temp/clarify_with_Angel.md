# Clarify with Angel


**Created:** 2026-06-14

---

## `tracing_active`

**Context:** The 2026-06-14 data dictionary links `tracing_system` to a companion field `tracing_active` (bool) to capture whether tracing is functionally active. There is **no dictionary row** for `tracing_active` in the CSV export.

**Question for Angel:**

> Should `tracing_active` be added to the lean virtual sensor data dictionary as a defined variable (with definition, allowed values, defaults, and linkage to `tracing_system`)? If yes, what are the intended semantics — e.g. `tracing_system = NONE` implies `tracing_active = false`; for steam/electric/hot-oil traced assets, how is “active” vs “failed/leaking” distinguished from the integrity bands already in `tracing_system`?

**Repo impact when answered:** add to `schema.yaml`, layer 5 generation, conditional rules, tests, and CSV output.

**Current status:** deferred; not part of the dictionary alignment PR.
