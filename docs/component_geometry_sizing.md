# Component geometry sizing — diameter & wall thickness

How `component_diameter` and `furnished_thickness` are drawn per asset class, so
the generated geometry is **physically realistic and class-appropriate**.

Geometry is the dominant driver of the thermal time constant `τ`(synthetic_inputs_methodology.md) and
[`temperature_series.py`](../lean_virtual_sensor/inputs_generation/temperature_series.py):
`τ ∝ A_metal ∝ Do · wall`. Oversized or mis-coupled geometry inflates `τ`,
which in turn makes every generated cooldown unrealistically slow. So the
sizing rules here are load-bearing for the temperature-series module, not just
cosmetic.

> **Status: PROPOSED — pending implementation.** This documents the agreed
> sizing scheme. It is not yet wired into `asset_class_config.yaml` /
> `generate_wall_insulation`; see [What this changes](#what-this-changes).

---

## The problem with the previous approach

`generate_wall_insulation` drew diameter and wall **independently and
uniformly** over wide per-class ranges:

```python
component_diameter  = rng.uniform(diam_min,  diam_max)    # e.g. PIPE 25–1200 mm
furnished_thickness = rng.uniform(wall_min,  wall_max)    # e.g. PIPE  3–50  mm
```

Two faults:

1. **Wrong distribution shape.** A uniform draw over 25–1200 mm makes the
   *median* "pipe" ≈ 610 mm (24″). Real piping populations are heavily skewed
   to small bore — most lines are 2″–8″.
2. **No diameter↔wall coupling.** Diameter and wall were independent, so a 1″
   pipe could be assigned a 50 mm wall. In reality wall thickness is tied to
   diameter through pipe schedules (NPS) and pressure design.

**Consequence (measured on `synthetic_v1.0_seed42.csv`):** computed `τ` ran
4–7× the methodology's representative values, and **76 % of assets would take
>3 days to fully cool, 45 % >1 week** — physically wrong for a process plant.

| class | τ median, old data | §5 representative |
|---|---|---|
| PIPE | 35 h | 5.5 h |
| PRESSURE_VESSEL | 106 h | 25 h |
| COLUMN | 133 h | 35 h |
| REACTOR | 148 h | 31 h |

---

## PIPE — NPS catalog (ASME B36.10M)

Strictly, **Nominal Pipe Size applies only to pipe.** PIPE is sized by sampling
discrete `(OD, wall)` pairs from the ASME B36.10M catalog — Schedule 40 up to
12″, STD above — with frequency weights skewed to small bore. Diameter and wall
are drawn **together** from the same row, so they are always a real, coupled
pipe size.

| NPS | OD (mm) | wall (mm) | schedule | weight |
|----:|--------:|----------:|----------|-------:|
| 1″   |  33.4 |  3.38 | Sch 40 |  8   |
| 1.5″ |  48.3 |  3.68 | Sch 40 | 10   |
| 2″   |  60.3 |  3.91 | Sch 40 | 15   |
| 3″   |  88.9 |  5.49 | Sch 40 | 15   |
| 4″   | 114.3 |  6.02 | Sch 40 | 15   |
| 6″   | 168.3 |  7.11 | Sch 40 | 12   |
| 8″   | 219.1 |  8.18 | Sch 40 |  9   |
| 10″  | 273.0 |  9.27 | Sch 40 |  6   |
| 12″  | 323.9 | 10.31 | Sch 40 |  5   |
| 16″  | 406.4 |  9.53 | STD    |  3   |
| 20″  | 508.0 |  9.53 | STD    |  1.5 |
| 24″  | 610.0 |  9.53 | STD    |  0.5 |

Weights are `[ENGINEERING_JUDGEMENT]` for a refinery line population (median
≈ 4″). Insulation thickness is drawn separately (≈ 40–90 mm).

---

## Non-pipe classes — realistic diameter + coupled wall

Vessels, columns, tanks, exchangers, and air-coolers are **not** NPS pipe, so
the catalog does not apply. They use the engineering analog:

- **Diameter** is drawn **triangular** `(min, mode, max)`, centered on the
  methodology's representative size — not uniform over a wide range, so the
  median stays near the representative value.
- **Wall** is **coupled to diameter**: `wall = (t/D) · diameter`, with `t/D`
  drawn within a per-class band reflecting pressure-design / API 650 practice,
  then clamped to `[6, 120] mm`.

| class | diameter min / **mode** / max (mm) | wall `t/D` band | basis |
|---|---|---|---|
| PRESSURE_VESSEL | 500 / **2000** / 4000 | 0.8–1.4 % | ASME VIII |
| HEAT_EXCHANGER | 200 / **800** / 1500 | 1.0–2.0 % | shell-and-tube shell |
| AIR_COOLER | 100 / **300** / 500 | fixed 3–10 mm | header boxes |
| COLUMN | 800 / **2500** / 5000 | 0.8–1.4 % | ASME VIII |
| STORAGE_TANK | 3000 / **15000** / 40000 | 0.04–0.10 % | API 650 (thin shell) |
| REACTOR | 1000 / **1800** / 4000 | 1.0–1.8 % | thick-walled (hydroprocessing) |

Storage tanks are deliberately **thin-walled relative to diameter** (a 15 m
tank ≈ 10 mm shell), which is why a huge tank still has a modest `τ`.



---

## What this changes

- **`asset_class_config.yaml`** — replace each class's
  `component_diameter` / `furnished_thickness` `{min, max}` with the NPS catalog
  (PIPE) and the triangular-diameter + `t/D`-band scheme (other classes).
- **`generate_wall_insulation`** ([`layer_generators.py`](../lean_virtual_sensor/inputs_generation/layer_generators.py))
  — for PIPE, sample one `(OD, wall)` row from the weighted NPS catalog; for the
  rest, draw diameter triangular then set wall from the coupled `t/D` band,
  replacing the two independent `rng.uniform` calls.
- **Knock-on** — the static CSV is regenerated; `test_distributions` /
  `test_schema_compliance` geometry expectations may need updating; `schema.yaml`
  `component_diameter` / `furnished_thickness` min/max must still bound these
  (tank diameter up to 40 m).

---

## Provenance

| Rule | Claim | Authority | Status |
|---|---|---|---|
| `R-PIPE-NPS-01` | PIPE diameter/wall from the NPS catalog, not uniform min/max | `standard` — ASME B36.10M (OD, Sch 40/STD walls); frequency weights `engineering_judgement` | implements [rules_provenance P-10](rules_provenance.md) |
| (non-pipe) | diameter triangular at representative size; wall coupled via `t/D` | `engineering_judgement` (ASME VIII / API 650 informed) | supersedes the "uniform in class min/max" note at [rules_provenance P-23](rules_provenance.md) |

Standards named here (ASME B36.10M, ASME VIII, API 650) should be carried into
[`citations_audit.md`](citations_audit.md) when this scheme is implemented.
