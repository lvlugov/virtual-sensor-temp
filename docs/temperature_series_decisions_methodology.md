# Temperature-series generator — methodology, assumptions & decisions

Concise spec for the per-asset process-temperature generator
([`temperature_series.py`](../lean_virtual_sensor/inputs_generation/temperature_series.py)).
Full explanation with worked examples:
[`temperature_series_explained.md`](temperature_series_explained.md).
Geometry sizing: [`component_geometry_sizing.md`](component_geometry_sizing.md).

---

## Methodology (brief)

For each asset, generate one hourly process-temperature series `T_process(t)`
over a 90-day window (2,160 hours) from the static asset row plus a supplied
per-asset ambient series. Nine steps:

1. **τ** — thermal time constant, from geometry + insulation + metallurgy.
2. **baseline** — flat at `operating_temperature`.
3. **placement** — `N = avg_cycles_per_quarter` cycle events, equally spaced.
4. **duration** — each cycle off for `(1 − f) × spacing`.
5. **target** — cooldown reference: `ambient`, or `min` for wide-swing.
6. **assemble** — blocky target array (baseline + cycle windows).
7. **lag** — exponential relaxation toward the target (the gradual slide).
8. **noise** — ±2 °C wiggle on running hours.
9. **clamp** — to `[min, max]`, then to global `[−100, +500] °C`.

---

## Assumptions

- Shutdowns occur at **equal intervals** across the window — one every `90/N`
  days, centred (a half-interval of running time at each end).
- Each cycle is **turned back on a fixed time after it shuts down**; every cycle
  of a given asset lasts the **same** duration.
- Total off-time `= (1 − operation_vs_shutdown_fraction) × 90 days`, split
  equally across the cycles. "Off" means **operationally idle** — a matter of
  time, not of how cold the metal gets.
- Every shutdown **aims fully at a cold target**; how deep it actually gets is
  set only by **duration vs τ**. A shutdown ended before ~3·τ never fully cools.
- Temperature changes are **gradual** (first-order thermal lag), never instant.
- **Recovery is faster than the excursion** — returning to operating temperature
  (active re-heating / re-cooling by the process) uses a shorter τ than the
  passive cooldown/warm-up.
- **Ambient is an input** — a per-hour, last-90-days series supplied per asset;
  weather is never modelled here.
- The **per-class table below is the source of truth**; each asset's values come
  from the static dataset (the current CSV is not relied upon).
- Carbon-steel-family metallurgies only; `NICKEL_ALLOY` and `OTHER` are out of
  scope and skipped.

---

## Profiles (detected from `operating` and `min`)

| condition | profile | aims at |
|---|---|---|
| `operating < 0` | cold-service | `ambient` (warms up, crosses −4 °C) |
| `operating > 0` and `min < 0` | wide-swing | `min` (driven sub-ambient) |
| otherwise | ordinary hot (incl. reactor) | `ambient` |

Reactors are ordinary hot — their partial dips emerge from large τ, not a
special case. Direction (down for hot, up for cold-service) follows from the
sign of `op − target`.

---

## Decisions

| area | decision |
|---|---|
| Insulation `k` | ASTM-cited table (config) |
| Metal ρ, c | per metallurgy (config): CARBON_STEEL, LOW_ALLOY_STEEL, AUSTENITIC_SS, DUPLEX_SS |
| τ | lumped-capacitance `C·R/3600`; geometry in mm |
| Placement | equally spaced, centred; deterministic |
| Duration | uniform within an asset; per-asset variety comes from the static `N`/`f` ranges |
| Depth | emergent from duration vs τ — no per-cycle full/partial choice, no held-warm level |
| Recovery | asymmetric — recovery legs (return to op) use `τ × recovery_tau_factor` (default 0.5, ~2× faster); cooldown unchanged |
| Noise | running hours only, uniform ±`running_noise_amplitude_c` |
| Clamp | asset `[min, max]`, then global `[−100, +500] °C` |
| Population | wide-swing = 5 % of all assets; cold-service ≈ 12 % of PIPE / PRESSURE_VESSEL / STORAGE_TANK |
| Randomness | only Step 8 (noise), seeded from `run.random_seed`; Steps 1–7, 9 are deterministic |
| Output | one file per asset, `<ASSET>_<start>_<end>.csv`, columns `datetime, process_temperature_c` |

---
