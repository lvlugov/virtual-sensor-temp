# Asset surface temperature, dew point, and damage factor

Per-asset thermal and corrosion-driver calculations:

1. **Skin temperature** `T_skin` — 1-D radial heat balance for an insulated pipe.
2. **Damage factor** `f(T_skin)` — NACE SP0198-2010 Figure 1 curves.
3. **Surface dew point and wetness factor** `T_dew`, `w(T_skin, T_dew)` — Magnus formula plus piecewise wetness score.
4. **Hourly damage score** `hour_score = f(T_skin) · w(T_skin, T_dew)` — AND of "hot enough" and "wet enough".
5. **Active CUI Hours** `ACH_90d = Σ hour_score(t)` — raw aggregate over the last 90 days.

End-to-end entry point: `compute_ach_for_asset(...)` chains Steps 1-5 for one
asset and returns the raw ACH; see [Pipeline](#pipeline--compute_ach_for_asset) below.

Driver: [`lean_virtual_sensor/feature_engineering/asset_temperature.py`](../lean_virtual_sensor/feature_engineering/asset_temperature.py).
All calibration data lives under the `asset_temperature` block in
[`config.yaml`](../lean_virtual_sensor/config.yaml).

---

## Step 1 — Skin temperature `T_skin`

Three thermal resistances in series — internal film, insulation, external
film — give an attenuation factor `k ∈ (0, 1)`:

```
T_skin    = T_process − k · (T_process − T_ambient)
k         = R_inside / (R_inside + R_ins + R_ambient)
R_inside  = 1 / (2π · r_pipe_inner  · h_internal)
R_ins     = ln(r_outer_total / r_pipe_outer) / (2π · λ_insulation)
R_ambient = 1 / (2π · r_outer_total · h_external)
```

Low `k` → good insulation and/or good internal film, `T_skin ≈ T_process`.
High `k` → poor insulation and/or poor internal film, `T_skin` pulled toward
`T_ambient`.

`compute_k(...)` takes:

| Argument | Meaning |
|---|---|
| `insulation_type` | material key into the `insulation_lambda_w_per_mk` config table |
| `insulation_thickness_mm` | insulation jacket thickness |
| `pipe_diameter_mm` | recorded component OD (also inner surface of insulation) |
| `wall_thickness_mm` | original (furnished) metal wall thickness — used only to derive the bore radius via `bore = pipe_diameter − 2·wall_thickness` |
| `h_internal` *(optional)* | internal film coefficient; defaults to `default_h_internal_w_per_m2k` (≈ 1000 liquid, ≈ 50 gas) |
| `h_external` *(optional)* | external film coefficient; defaults to `default_h_external_w_per_m2k` (10 still air, 15 light wind, 25 windy) |

The metal wall itself is not modelled as its own series resistance — steel
conducts roughly 1000× better than the insulation, so its thermal
contribution is negligible. `wall_thickness_mm` enters the calculation
only via the bore radius for the internal film term.

`compute_k` raises `ValueError` if any of the four geometry inputs is
non-positive, or if `wall_thickness_mm ≥ pipe_diameter_mm / 2` (would
leave no bore and divide by zero in the internal film term). The bore
check is the substantive one — without it a unit-swap in the historian
(inches vs mm) would crash deep in `_film_resistance` instead of at the
entry point.

`compute_t_skin(t_process, t_ambient, k)` then applies the attenuation to
give the skin temperature.

## Step 2 — Damage factor `f(T_skin)`

Scores how aggressive corrosion would be at this temperature, *assuming
water is present on the surface*. Two NACE-derived curves; which one
applies depends on the asset's open/closed flag, derived via
[`is_open_system`](#openclosed-flag--is_open_system) from the insulation
and cladding condition strings on `AssetSpec`. Both curves return 0
outside the active band `[nace_t_low_c, nace_t_high_c]` (default
`[−4, 175]` °C).

### Closed system (default for most assets)

`compute_f_closed(t_skin)` — linear fit through the digitised "Closed
System" line in NACE SP0198-2010 Figure 1 (after Speller 1935),
constrained to pass through (`nace_t_low_c`, 0):

```
f_closed(T_skin) = nace_slope_closed · (T_skin − nace_t_low_c)
                   for nace_t_low_c ≤ T_skin ≤ nace_t_high_c
                 = 0  otherwise
```

With the config defaults (`nace_slope_closed = 0.00525` (mm/y)/°C) the
curve climbs monotonically across the whole active band, reaching ≈ 0.94
at 175 °C — the dryness boundary. Physically: in a closed environment the
water film traps oxygen, so the oxygen-cell mechanism keeps strengthening
with temperature; peak damage sits at the upper bound rather than in the
middle.

A linear fit is used rather than a power law because the digitised NACE
closed-system line is essentially straight; adding curvature would
over-fit a one-figure source.

### Open system (insulation Average or Poor)

`compute_f_open(t_skin)` — smooth monotonic-cubic (PCHIP) interpolation
through six digitised points from the "Open System" dashed line in the
same figure, held in `nace_open_t_points_c` and `nace_open_r_points`:

| T_skin (°C) | 40   | 60   | 70   | 80   | 90   | 100  |
|-------------|------|------|------|------|------|------|
| f_open      | 0.27 | 0.35 | 0.40 | 0.42 | 0.40 | 0.35 |

PCHIP is chosen over a natural cubic spline because it preserves the
monotone-rise-then-monotone-fall shape of the source data without
spurious overshoot between knots. With the config defaults the peak sits
at 80 °C with f ≈ 0.42, matching the NACE-cited open-system peak.

Outside the fitted range `[40, 100]` °C — but still inside the global
active band — the function extrapolates linearly using the slope of the
nearest boundary segment, clipped at zero. This keeps behaviour
predictable near the edges without inventing data the figure does not
contain.

The asymmetric rise-peak-fall shape comes from chemistry: corrosion rate
rises with temperature, but dissolved oxygen escapes as water heats up.
Their product peaks in the middle.

## Step 3 — Surface dew point and wetness factor

### Step 3a — Surface dew point `T_dew`

Magnus formula applied to ambient air:

```
T_dew  = b · γ / (a − γ)
γ      = ln(RH / 100) + a · T_ambient / (b + T_ambient)
```

`a` and `b` come from `asset_temperature.magnus_a` / `magnus_b` (defaults
17.62 and 243.12 — the WMO-recommended Magnus-Tetens form).

The dew point is set by the absolute water content of the air, which is
conserved as air migrates through the insulation, so the surface dew
point equals the external dew point. `T_skin` does not enter here — it
governs whether condensation *occurs*, not where the dew point sits.
Driven by `compute_t_dew(...)`.

`compute_t_dew` raises `ValueError` if `rh_percent` is outside `(0, 100]`.
Below 0 the Magnus log term is undefined; above 100 is physically
impossible and a likely bad-data sentinel from upstream sensors.

### Step 3b — Wetness factor `w(T_skin, T_dew)`

Piecewise-linear score for whether water is likely on the steel surface
from atmospheric condensation:

```
w = 1.0                              if T_skin ≤ T_dew
    (T_dew + band − T_skin) / band   if T_dew < T_skin ≤ T_dew + band
    0                                if T_skin > T_dew + band
```

`band = wetness_transition_band_c` from config (default 10 °C).

At or below the dew point, the surface is condensing (`w = 1`). Well
above it, the surface is dry (`w = 0`). Within `band` °C immediately
above `T_dew`, partial condensation is possible and `w` falls smoothly
from 1 to 0 across the transition. The function is continuous at both
boundaries by construction. Driven by `compute_wetness(...)`.

## Step 4 — Hourly damage score `hour_score`

`compute_hour_score(f_t_skin, wetness)` multiplies the two factors:

```
hour_score = f(T_skin) · w(T_skin, T_dew)
```

Multiplication is AND logic: damage accumulates only when both conditions
hold. Hot but dry (`w = 0`) → 0. Wet but cold/too-hot (`f = 0`) → 0. Hot
and wet → positive. The product preserves the units of `f` (mm/y), scaled
by the dimensionless `w`.

Which `f` to use — `compute_f_closed` or `compute_f_open` — is an
asset-level decision (open/closed insulation system) and is the caller's
responsibility; this step takes whichever scalar `f` value the caller
chose.

## Step 5 — Active CUI Hours `ACH_90d`

`compute_ach(hour_scores)` sums the per-hour scores across the window:

```
ACH_90d = Σ hour_score(t)   over hours t in last 90 days
        = Σ f(T_skin(t)) · w(T_skin(t), T_dew(t))
```

One number per asset per cycle. The theoretical ceiling is `2160` (90 d ·
24 h, every hour scoring 1.0 on both factors); real assets sit well
below it because being simultaneously at peak `f` and `w = 1` is rare.

The function takes a pre-built iterable of hourly scores — windowing
(slicing the hourly series to the trailing 90 days) lives in the caller
because it depends on the caller's timestamp format. Output is raw, not
normalised; any 0-1 scaling for regression-readiness is the modelling
step's call.

### Cadence note

The current implementation assumes hourly historian data. When 15-minute
resolution becomes available, the calculation drops in unchanged — the
time index just becomes finer, the sum runs over 8 640 quarter-hour
scores instead of 2 160 hourly ones. Planned future improvement.

## Pipeline — `compute_ach_for_asset`

### `AssetSpec`

Static asset configuration: bundles the seven parameters that describe one
insulated pipe. Frozen and keyword-only at construction, so a single
instance can be passed across a pipeline without risk of mid-flight
mutation. Validation lives in the consuming functions (`compute_k`,
`compute_t_dew`), not `__post_init__`, so a bad field surfaces from the
code that actually depends on the constraint rather than at construction.

| Field | Meaning |
|---|---|
| `insulation_type` | material key into the `insulation_lambda_w_per_mk` config table (case-insensitive) |
| `insulation_thickness_mm` | insulation jacket thickness; must be `> 0` |
| `pipe_diameter_mm` | pipe outer diameter; must be `> 0` |
| `wall_thickness_mm` | metal wall thickness; must satisfy `0 < wall < pipe_diameter / 2` |
| `insulation_condition` | `"GOOD"`, `"AVERAGE"`, or `"POOR"` (case-insensitive); fed to `is_open_system` to choose the NACE curve |
| `cladding_integrity` | `"GOOD"`, `"AVERAGE"`, or `"POOR"` (case-insensitive); also fed to `is_open_system` |
| `h_internal`, `h_external` *(optional)* | film-coefficient overrides for `compute_k`; `None` falls back to the config defaults |

### Open/closed flag — `is_open_system`

Driver: [`lean_virtual_sensor/feature_engineering/system_flag_feature.py`](../lean_virtual_sensor/feature_engineering/system_flag_feature.py).
Captures the NACE business rule that a *closed* system — water trapped
against the steel by intact barriers — requires BOTH insulation AND
cladding to be in `"GOOD"` condition. Any compromise to either lets
atmospheric moisture in (and oxygen-bearing water out), so the system is
effectively *open*:

```
is_open_system(insulation_condition, cladding_integrity)
    = False  if insulation_condition == cladding_integrity == "GOOD"
    = True   otherwise
```

Inputs are case-insensitive and must be one of `{"GOOD", "AVERAGE", "POOR"}`;
any other string raises `ValueError`. The pipeline calls this once per
ACH computation, so a typo in a fleet inventory surfaces at the boundary
rather than silently selecting the wrong NACE curve.

### Orchestration

`compute_ach_for_asset(asset, *, t_process_series, t_ambient_series, rh_series)`
takes one `AssetSpec` plus three keyword-only hourly time series and
returns a single raw ACH value:

```
k = compute_k(asset)                                                       # once per asset
open_system = is_open_system(asset.insulation_condition, asset.cladding_integrity)
f = compute_f_open if open_system else compute_f_closed
for (T_process, T_ambient, RH) in zip(series, strict=True):
    T_skin     = compute_t_skin(T_process, T_ambient, k)
    T_dew      = compute_t_dew(T_ambient, RH)
    hour_score = compute_hour_score(f(T_skin), compute_wetness(T_skin, T_dew))
ACH = compute_ach(hour_scores)
```

`zip(..., strict=True)` on the three series makes length-mismatched
inputs raise `ValueError` immediately rather than silently truncating to
the shortest.

Windowing lives in the caller — the function does not read timestamps.
Slice your hourly series to the trailing 90-day window before calling.

---

## Config schema (`asset_temperature` block)

```yaml
asset_temperature:
  insulation_lambda_w_per_mk:        # name → λ (W/m·K) table
    FOAMGLASS: 0.045
    MINERAL_WOOL: 0.040
    FIBERGLASS: 0.035
    CALCIUM_SILICATE: 0.058
    PEARLITE: 0.052
    ASBESTOS: 0.070
    UNKNOWN: 0.040                   # conservative mid-range fallback
  default_h_external_w_per_m2k: 10.0
  default_h_internal_w_per_m2k: 1000.0
  magnus_a: 17.62
  magnus_b: 243.12
  nace_t_low_c: -4.0                 # active-band lower bound for f(T_skin)
  nace_t_high_c: 175.0               # active-band upper bound for f(T_skin)
  nace_slope_closed: 0.00525         # (mm/y)/°C, closed-system linear fit
  nace_open_t_points_c: [40, 60, 70, 80, 90, 100]
  nace_open_r_points:   [0.27, 0.35, 0.40, 0.42, 0.40, 0.35]
  wetness_transition_band_c: 10.0     # °C above T_dew over which w drops 1 → 0
```

Missing keys fail fast at load time via `load_section(..., REQUIRED_KEYS)`,
not at use, so a typo doesn't surface mid-pipeline.

---

## Design decisions

### NACE calibration data lives in config, not as module constants

The active band, closed-system slope and the open-system knot table sit
in `config.yaml` next to the Magnus coefficients and insulation
conductivities — single source of truth for all `asset_temperature`
calibration, adjustable per deployment without touching code.

### Linear fit for the closed system, PCHIP for the open system

The closed-system NACE line is essentially straight, so a single slope
captures it without over-fitting. The open-system curve is a peaked
function — a single power-law or polynomial would either miss the
asymmetry or wiggle. PCHIP through the digitised knots preserves the
monotone-rise-then-monotone-fall shape exactly and gives a smooth curve
without overshoot.

### Linear extrapolation outside the open-curve knots, clipped at zero

NACE Figure 1 does not draw the open-system curve below 40 °C or above
100 °C, so we have no shape to fit there. Linear extrapolation from the
boundary segment is the least opinionated choice that still gives a
defined value across the full active band; the `max(0, ·)` floor stops
the line from going negative if the extrapolation eventually crosses
zero.

### Zero outside the active band, not "clamp to nearest endpoint"

Below `nace_t_low_c` or above `nace_t_high_c`, both curves return 0
rather than the boundary value. The active band represents the
temperature window in which the corrosion mechanism applies at all — at
−10 °C nothing is corroding (frozen), and above 175 °C the surface is
above the boiling point of water at any practical pressure so the
"water present" precondition is moot. Returning 0 makes that explicit.

### ACH is raw, not normalised

`compute_ach` returns the bare sum `Σ f·w`, not a 0-1 scaled value. The
calibration of an "empirical realistic maximum" depends on the downstream
modelling target (regression vs. classification, choice of label,
training population) and bolting one onto the feature producer would
lock every consumer into the same scaler. Normalisation is the
modelling layer's job; this layer's job is to deliver the integral.

### 90-day window length is hard-coded, not config-driven

The window size sits in code and prose, not in `config.yaml`. The
function does not slice — it sums whatever it is given — so a config
key for "window days" would be metadata the function never reads. If a
caller later needs to vary the window, the natural place is the slicing
call, not this aggregator. Avoiding dead config keeps the schema lean.

### Pipeline takes an `AssetSpec`; series are keyword-only

`compute_ach_for_asset` takes one positional `AssetSpec` and three
keyword-only hourly series. The asset bundle is a natural conceptual
unit — one row in a fleet inventory — so the positional slot reads
naturally; the three series are individually meaningless until paired
with one another, so kw-only at the call site stops a swap (ambient and
process are both floats and both plausible — a positional bug would
quietly produce a wrong ACH). `AssetSpec` is frozen so a single
instance can be shared across calls safely. The three series feed
`zip(..., strict=True)` so a length mismatch raises immediately rather
than silently truncating to the shortest.

### Validation lives in the consuming functions, not in `AssetSpec.__post_init__`

`compute_k` checks geometry; `compute_t_dew` checks RH range;
`is_open_system` checks the two condition strings. Putting the same
checks in `AssetSpec.__post_init__` would duplicate them and detach the
error from the math that needs the constraint. Constructing an
`AssetSpec` is cheap and side-effect-free; the boundary that matters is
"input fed to a calculation," and that is where the validation sits.

### Open/closed flag is derived, not stored

`AssetSpec` carries the raw `insulation_condition` and `cladding_integrity`
strings (the data an inspector actually records) rather than a
pre-computed `open_system` bool. The pipeline derives the flag via
`is_open_system` at call time. Storing both the inputs and the derived
flag would create a sync problem — an editor could update one
condition string and forget to refresh the bool, quietly producing the
wrong NACE curve. Storing only the raw conditions makes the flag a pure
function of the spec, recomputed on demand.
