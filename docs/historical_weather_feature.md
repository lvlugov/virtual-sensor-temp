# Historical wetting load

Per-asset score complementing Active CUI Hours (ACH). Where ACH summarises
the trailing 90-day window from hourly weather, `wet_load` captures
damage accumulated *before* that window — the period from the last
inspection through to `today − 90 days`.

Driver: [`lean_virtual_sensor/feature_engineering/historical_weather_feature.py`](../lean_virtual_sensor/feature_engineering/historical_weather_feature.py).
Calibration lives under the `historical_weather` block in
[`config.yaml`](../lean_virtual_sensor/config.yaml).

End-to-end entry point: `compute_features_for_asset(...)` in
[`feature_pipeline.py`](../lean_virtual_sensor/feature_engineering/feature_pipeline.py)
chains the bulk-cache load, the open/closed flag, ACH, and this metric
into one call.

---

## Standards & provenance

Each step is tagged inline as **[Standard]** (we implement a published
method or use published threshold values) or **[CorrosionRadar]** (our
own method, not in any standard). The standards in this module mostly
anchor parameter *values*; the `wet_load` metric itself — a
recency-weighted ratio of wetting vs (wetting + drying) — is
CorrosionRadar's own. A reader auditing this code against the
literature should be able to trace every standard-tagged piece back to
its source; CorrosionRadar pieces are our refinements layered on top.

| Provenance | What we use it for |
|---|---|
| **ISO 9223:2012** atmospheric-corrosivity criteria | Drying thresholds (`drying_temp_threshold_c = 15`, `drying_humidity_threshold_percent = 60`) and the "wet" RH reference (~80 %) that anchors `vapor_humidity_threshold_percent = 60` |
| **ASHRAE Handbook of Fundamentals 2021, Ch. 25** | Calibration anchor for `drying_weight = 0.3` (insulation drying rates 2–5 mm/day) |
| **FAO Irrigation and Drainage Paper 56** (Penman-Monteith reference evapotranspiration) | Sanity check on the drying-rate order of magnitude (~40–60 % of reference ET) |
| **NACE SP0198-2017** | Calibration anchor for `half_life_days = 365` (insulation moisture-retention timescales) |
| **Textbook atmospheric meteorology** (vapor-pressure-deficit proxy) | The drying form `temp · (1 − humidity/100)` in Step 5 |
| **Standard meteorological aggregation** | Step 2 daily resampling (sum precip, mean humidity, mean temp) |
| **CorrosionRadar — ours** | The `wet_load` metric itself · exponential-decay recency weighting (Step 3) · hot-dry mask gating the drying term (Step 5) · linear-above-threshold vapor-ingress form (Step 4) · open-system short-circuit to 0 · 0/0 → 0 empty-case convention · inspection-date clamp in the orchestrator · decoupled drying / vapor humidity thresholds |

The standards pin parameter values and the daily-aggregation convention;
CorrosionRadar combines them into a single per-asset metric (`wet_load`)
that complements ACH and which neither ISO 9223 nor ASHRAE defines.

---

## The metric — a tug-of-war

Closed systems retain memory of historical wet exposure because water
stays trapped against the steel; open systems drain freely and have no
such memory, so the metric short-circuits to `0` for open systems.

For closed systems, the wet load is a recency-weighted ratio of wetting
inputs (rain + vapor ingress) against drying outputs (warm dry days):

```
weight(day)     = 0.5 ** (days_from_window_end / half_life_days)
vapor_per_day   = vapor_weight · max(humidity − vapor_threshold, 0)
weighted_wet    = Σ (precip + vapor_per_day) · weight
drying_per_day  = drying_weight · temp · (1 − humidity/100)
                  ON hot-dry days only:
                      temp > drying_temp_threshold_c
                      AND humidity < drying_humidity_threshold_percent
weighted_drying = Σ drying_per_day · weight
wet_load        = weighted_wet / (weighted_wet + weighted_drying)
```

Bounded in `[0, 1]` by construction (ratio of non-negative quantities).

---

## Step-by-step

### Step 1 — Slice the hourly cache to the pre-ACH window &nbsp;&nbsp;_[CorrosionRadar]_

Filter `weather_df` to rows with `last_inspection_date ≤ datetime < today − 90 d`.
The hourly weather is the same DataFrame
[`fetch_hourly_window`](./asset_temperature.md) wrote to the per-location
CSV cache, with columns `datetime`, `temp`, `humidity`, `precip`.

### Step 2 — Resample to daily aggregates &nbsp;&nbsp;_[Standard meteorological practice]_

```
daily.precip   = sum  of hourly precip       (mm/day)
daily.humidity = mean of hourly humidity     (% / day)
daily.temp     = mean of hourly temperature  (°C / day)
```

Daily is the natural cadence for the rest of the math — rainfall events
are summed (a 20-minute storm contributes mm to that day's total),
humidity and temperature are averaged (the day "feels" however its
average reads).

### Step 3 — Recency weight per day &nbsp;&nbsp;_[CorrosionRadar]_

```
age_days       = (window_end − day) in days, ≥ 0
weight(day)    = 0.5 ** (age_days / half_life_days)
```

`half_life_days = 365` by default: today's day counts 1.0, one-year-old
day counts 0.5, two-year-old day counts 0.25, etc. Smaller half-life =
more aggressive forgetting; larger = longer memory.

### Step 4 — Wet pathways: rain + vapor ingress &nbsp;&nbsp;_[CorrosionRadar; vapor threshold anchored to ISO 9223:2012]_

Two ways water enters the insulation:

```
weighted_wet = Σ (precip + vapor_per_day) · weight
vapor_per_day = vapor_weight · max(humidity − vapor_threshold, 0)
```

* **Rain** — always counts (in mm) when present.
* **Vapor ingress** — when daily RH exceeds `vapor_humidity_threshold_percent`
  (default 60 %), water-laden air drives moisture into the insulation
  even without precipitation. Linear in the excess humidity above the
  threshold.

### Step 5 — Drying pathway: warm dry days only &nbsp;&nbsp;_[CorrosionRadar mask + weighting; ISO 9223:2012 thresholds; textbook VPD form]_

```
drying_per_day = drying_weight · temp · (1 − humidity/100)        # if hot-dry
                 0                                                # otherwise
hot_dry        = (temp > drying_temp_threshold_c)
                 AND (humidity < drying_humidity_threshold_percent)
weighted_drying = Σ drying_per_day · weight
```

Hot air with low RH drives evaporation. Cool air, humid air, or both
contribute zero drying — multiplying by the hot-dry mask zeros out
those days. The formula `temp · (1 − humidity/100)` is a vapor-pressure-
deficit proxy: more deficit = more drying.

### Step 6 — The ratio &nbsp;&nbsp;_[CorrosionRadar]_

```
wet_load = weighted_wet / (weighted_wet + weighted_drying)
```

When `weighted_wet + weighted_drying > 0`, the result is bounded in
`[0, 1]` — `0.0` means every day was drying-dominant, `1.0` means every
day was wetting-dominant.

When both are zero (the "empty case", see below), return `0.0` by
convention.

---

## Why recency matters

Two assets with identical 10-year totals — same total rainfall, same
total drying-potential — but reversed timing produce **different**
scores:

| Asset | Old half (years 5-10 ago) | Recent half (last 5 years) | wet_load |
|---|---|---|---|
| A | wet | dry | **low** — recent dry dominates |
| B | dry | wet | **high** — recent wet dominates |

A flat (un-weighted) sum can't tell A and B apart. The exponential
recency weight makes them distinguishable — recent damage matters more
than ancient damage, which matches the physical intuition that the
asset has had time to dry out (or stay wet) since the early events.

This is verified by
`test_recent_rain_scores_higher_than_old_rain` in
[`test_historical_weather_feature.py`](../tests/test_feature_engineering/test_historical_weather_feature.py).

---

## Inspection-date clamping

`compute_wet_load` itself just filters `weather_df` by date — if the
caller passes a `last_inspection_date` older than anything in the
DataFrame, the `>= last_inspection_date` filter simply matches every
row. The pre-90-day window then runs from "earliest available data"
through `today − 90 d`.

The **orchestrator** ([`compute_features_for_asset`](../lean_virtual_sensor/feature_engineering/feature_pipeline.py))
makes this clamp explicit before calling `compute_wet_load`:

```python
cache_earliest = weather["datetime"].min()
effective_start = max(pd.Timestamp(last_inspection_date), cache_earliest)
```

Resulting behaviour:

| Inspection age | `effective_start` |
|---|---|
| **Within** the 10-year cache | `last_inspection_date` (no clamp) |
| **Before** the cache (e.g. 15 years ago) | `cache_earliest = today − 10 y` |

The clamp lives in the orchestrator, not in `compute_wet_load`, because
`compute_wet_load` is a pure transformation on whatever DataFrame it's
handed — it doesn't know about a "10-year cache" or any other
constraint on input range. The orchestrator is the right layer to
enforce that constraint, and a dedicated test
(`test_pipeline_inspection_before_cache_clamps_to_cache_start` in
[`test_feature_pipeline.py`](../tests/test_feature_engineering/test_feature_pipeline.py))
pins the behaviour.

---

## Short-circuit and edge cases

| Case | Behaviour |
|---|---|
| `open_system = True` | Returns `0.0` before touching weather. Open systems have no historical memory. |
| `last_inspection_date >= today − 90 d` | Returns `0.0`. No pre-ACH period exists to summarise. |
| `weather_df` is empty after the slice | Returns `0.0`. No rows means no signal. |
| **The "empty case"**: rows exist but `weighted_wet == weighted_drying == 0` | Returns `0.0`. See below. |

### The "empty case" — `0 / 0`

The ratio is undefined when *every* term in both the numerator and
denominator is zero. That happens when every day in the window:

* has no precipitation (`precip = 0`), AND
* has humidity below the vapor threshold (`humidity ≤ 60 %` → no vapor
  ingress), AND
* fails the hot-dry mask (`temp ≤ 15 °C OR humidity ≥ 60 %` → no
  drying).

Concretely: chilly, moderate-RH, no-rain days — e.g. `temp = 10 °C,
humidity = 50 %, precip = 0`. Nothing is putting water in, nothing is
taking it out.

The code guards the `0/0` with:

```python
return weighted_wet / total if total > 0 else 0.0
```

`0.0` is the physically honest answer: no detectable wet load over this
window.

---

## Default coefficients — literature anchors

The defaults are starting values pinned to published atmospheric-
corrosion and moisture-transport literature. All are tunable in
`config.yaml`; expect re-calibration against sensor-observed wetness
during pilot deployment.

| Parameter | Default | Source |
|---|---|---|
| `drying_weight` | `0.3` | At `T = 25 °C, RH = 30 %` the formula gives ≈ 5.25 mm-equivalent/day, consistent with ASHRAE Handbook of Fundamentals (2021, Ch. 25) insulation drying rates of 2-5 mm/day and ≈ 40-60 % of Penman-Monteith reference evapotranspiration (FAO Irrigation and Drainage Paper 56). |
| `drying_temp_threshold_c` | `15` | ISO 9223:2012 atmospheric corrosivity criteria — drying conditions start above ≈ 10-15 °C. |
| `drying_humidity_threshold_percent` | `60` | ISO 9223:2012 — surfaces are no longer "wet" once RH falls below ≈ 60 %. |
| `vapor_weight` | `0.1` | Starting value capturing vapor transport at RH between the drying threshold (60 %) and the ISO 9223 "wet" threshold (80 %). Calibration TBD with sensor data. |
| `vapor_humidity_threshold_percent` | `60` | Same physical tipping point as the drying RH threshold — kept as a separate key so future calibration can decouple the two regimes. |
| `half_life_days` | `365` | One-year memory matches insulation moisture-retention timescales referenced in NACE SP0198-2017. |
| `ach_window_days` | `90` | Shared with `compute_ach`; defines the boundary between the historical (this metric) and active (ACH) windows. |

---

## Config schema (`historical_weather` block)

```yaml
historical_weather:
  ach_window_days: 90
  half_life_days: 365
  drying_weight: 0.3
  drying_temp_threshold_c: 15
  drying_humidity_threshold_percent: 60
  vapor_weight: 0.1
  vapor_humidity_threshold_percent: 60
```

Missing keys fail fast at load time via `load_section(..., REQUIRED_KEYS)`,
not at use, so a typo doesn't surface mid-pipeline.

---

## Design decisions

### Ratio rather than fraction-of-wet-days

The previous formulation counted "is_wet" days (boolean) and returned
the wet fraction. That has two problems: it discards intensity (a
drizzle counts the same as a torrential storm) and is order-invariant
(a wet year five years ago counts the same as a wet year last month).
Switching to a ratio of weighted continuous quantities fixes both.

### Recency weighting via exponential decay

Linear weights (e.g. "last year counts double") have a hard cutoff that
makes the score discontinuous at the boundary. Exponential decay is
smooth — small timing shifts produce small score shifts. The
half-life is the only new parameter and has a defensible physical
interpretation ("how much does a 1-year-old day count").

### Drying only on hot-dry days

Multiplying the drying term by a hot-dry mask captures the physical
asymmetry: water always enters during wet events, but only leaves
when conditions actively support evaporation. Counting drying on cold
or humid days would over-credit assets that simply happened to be
in temperate climates.

### Two separate humidity thresholds (drying vs vapor)

The default values coincide at 60 %, but they describe opposite
physical regimes — drying happens *below* the threshold, vapor ingress
*above*. Keeping them as separate config keys means a future
calibration can introduce a "neither" band (e.g. drying < 50 %,
vapor > 70 %, between is dead) without restructuring the code.

### Clamping lives in the orchestrator

`compute_wet_load` is a pure transformation on `weather_df` and dates;
it doesn't carry knowledge of a "10-year cache". The
`max(last_inspection_date, cache_earliest)` clamp lives in
`compute_features_for_asset` where the cache concept is real. This
keeps each function's responsibility narrow and makes the constraint
visible at the layer that enforces it.

### Coefficients in config, not hardcoded

The literature anchors (ASHRAE, ISO 9223, FAO 56) give starting values,
not final values. Each coefficient is expected to be re-calibrated
against sensor-observed wetness on instrumented assets during pilot
deployment. Putting them in `config.yaml` next to the other tuning
parameters means re-calibration is a config edit, not a code change.
