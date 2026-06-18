# Cooldown cycle counting

Per-asset count of significant `T_skin` cooldowns over the same
trailing window that drives [Active CUI Hours](asset_temperature.md).
A cycle is a trough in the metal-skin temperature whose **prominence**
— the depth of the dip relative to the surrounding baseline — exceeds
`cycle_min_swing_c` (default 20 °C). The threshold sits comfortably
above hourly sensor noise (~3 °C jitter) and well below typical
process cooldowns (50 °C+), so the count tracks real thermal cycling
and not measurement jitter.

Driver: [`lean_virtual_sensor/feature_engineering/cycle_features.py`](../lean_virtual_sensor/feature_engineering/cycle_features.py).
Calibration lives under the `asset_temperature` block in
[`config.yaml`](../lean_virtual_sensor/config.yaml) — the cycle keys
sit next to `ach_window_days` because both metrics consume the same
window.

---

## Standards & provenance

| Provenance | What we use it for |
|---|---|
| **scipy.signal.find_peaks** | Prominence-based peak detection on the negated T_skin series — turns troughs into peaks for the detector |
| **CorrosionRadar — ours** | The choice of prominence as the trough metric, the noise-vs-cooldown threshold (`cycle_min_swing_c = 20 °C`), the NaN-gap interpolation policy (`cycle_max_gap_hours`), and the convention of counting cycles over the same window ACH summarises |

`scipy.signal.find_peaks` is the standard primitive; everything around
it — what to count, when to interpolate, how to handle gaps, where to
draw the noise floor — is CorrosionRadar's call.

---

## The metric

```
cycles = | { trough in T_skin(t) : prominence(trough) ≥ cycle_min_swing_c } |
```

Detection: `scipy.signal.find_peaks(-T_skin, prominence=cycle_min_swing_c)`.
Negating the series turns troughs in T_skin into peaks that
`find_peaks` recognises. The `prominence` parameter then rejects any
trough whose depth-from-baseline is below the threshold.

---

## NaN handling

Real T_skin series have gaps (sensor outages, comms drops, scheduled
downtime). The counter:

- Linearly interpolates **short gaps** — at most `cycle_max_gap_hours`
  consecutive NaNs (default 6).
- **Drops longer gaps** rather than interpolating across them — a
  multi-day gap cannot be safely interpolated; a straight line through
  it would either invent troughs that did not exist or mask real ones.
- Returns `0` for an empty / all-NaN / sub-three-point cleaned series
  (peak detection needs at least three points to define a prominence).

Concrete example with `cycle_max_gap_hours = 6`:

```
input:   [80, 80, NaN, 30, NaN, NaN, NaN, NaN, NaN, NaN, NaN, NaN, 50, 80]
                  ▲────▲                                      ▲─────────▲
              1-hr gap                                    8-hr gap (>6)

   1-hr gap → interpolated to 55 (midway between 80 and 30)
   8-hr gap → stays NaN → those rows dropped from the cleaned series

cleaned: [80, 80, 55, 30, 50, 80]      ← 8-hr gap completely removed
```

---

## Why prominence, not a fixed temperature window

A naive "every time T_skin drops below X" check has two problems:

- **It fires every hour during a long cooldown** rather than once per
  event. A 12-hour cooldown to 20 °C would register as twelve cycles.
- **It is sensitive to baseline drift.** A process that runs at 100 °C
  for the first half of the window and 80 °C for the second half
  would shift across the threshold even with no cooldown event.

Prominence sidesteps both. It measures the trough relative to its
*local* baseline, so each cooldown counts once regardless of duration,
and the count is invariant to baseline drift between cycles.

---

## Public API

```python
compute_cycle_count(t_skin_series, min_swing_c, max_gap_hours) -> int
```

Pure aggregator. Takes a `pd.Series` of hourly T_skin values (typically
the `t_skin` column of the DataFrame returned by
`asset_temperature.prepare_hourly_window`), returns the integer count
of qualifying troughs. NaN-tolerant per the policy above.

```python
compute_cycles_for_asset(asset, weather_df, process_history_df, last_inspection_date, today) -> int
```

Per-asset orchestrator. Mirrors `compute_ach_for_asset` in signature
and window semantics:

1. Calls `asset_temperature.prepare_hourly_window` to build the
   trailing-window hourly DataFrame (shared with ACH so both metrics
   see exactly the same data).
2. Extracts the `t_skin` column as a `datetime`-indexed Series.
3. Reads `cycle_min_swing_c` and `cycle_max_gap_hours` from
   `asset_temperature` config.
4. Runs `compute_cycle_count` and returns the result.

Empty windows return `0`.

---

## Config schema (new keys in the `asset_temperature` block)

```yaml
asset_temperature:
  # ... existing T_skin / ACH calibration ...
  ach_window_days: 90                 # shared window length
  cycle_min_swing_c: 20.0             # min trough prominence (°C)
  cycle_max_gap_hours: 6              # consecutive-NaN gap (h) to interpolate
```

The cycle keys live in the `asset_temperature` block (not a separate
`cycle_features` block) because the window length is shared with ACH —
keeping all related calibration in one place avoids drift between the
two metrics. The cycle module reads only the three keys it needs via
`load_section`, so there is no coupling beyond the shared section
name.

---

## Design decisions

### Same window as ACH

Cycle counting and ACH summarise the same trailing 90-day period.
Splitting them into separate windows would muddy the per-asset
interpretation — "high ACH but no cycles in the last quarter" should
mean something coherent. Single window, two views.

### Pure counter + per-asset orchestrator split

Same shape as `asset_temperature.compute_ach` (pure sum) and
`asset_temperature.compute_ach_for_asset` (per-asset orchestrator).
The pure counter is unit-testable with hand-built Series; the
orchestrator owns the DataFrame plumbing.

### Constants in config, not hardcoded

The prominence threshold and the gap-interpolation limit are
pilot-deployment calibration knobs — expected to be tuned against
sensor-observed cycling on instrumented assets. Putting them in
`config.yaml` next to the other thermal-pipeline tunables means
re-calibration is a YAML edit, not a code change.

### NaN-gap policy is hand-coded, not config-driven beyond the limit

`max_gap_hours` is configurable; *whether* to interpolate vs drop is
not. We always interpolate short gaps and always drop long ones —
that policy is a feature of the metric definition, not a deployment
knob.
