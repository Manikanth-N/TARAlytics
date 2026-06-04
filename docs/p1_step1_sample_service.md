# P1 Step 1 — SampleService (value-at-time engine)
## Status: implemented + tested + benchmarked. UI not started (as instructed).

`core/sample_service.py` is the foundation of every cursor-driven surface
(Situational Awareness panel, Values-at-Cursor table, Investigation Snapshot,
Timeline readouts, Map/Replay sync). One interpolation implementation, used by all.

---

## 1. Architecture Notes

- **One instance per parsed log**, held by `AppState`, rebuilt on `data_changed`.
  Views never interpolate themselves — they call `SampleService`. This is what makes
  the Values-at-Cursor table *authoritative*: the horizon, sticks, and readouts are
  visual renderings of the exact numbers the table shows, because all share one engine.
- **Lazy + cached.** Nothing is precomputed at construction. On first access to a
  message, its `TimeS` array is sorted once (stable argsort) and cached with the
  permutation; on first access to a column, its values are materialised in time order
  and cached. Arrays are numpy views over the existing DataFrames — no bulk copy.
  Result: init is effectively free even on 13 M-row logs (measured ≤ 4 ms).
- **Time domain = absolute seconds (`TimeS`).** The shared cursor is one absolute
  time; every lookup is `value_at(msg, col, t)`.
- **Never fabricates.** Out-of-range or missing message/column → `None` (surfaces
  render `—`). NaN-aware (see §3).
- **No Qt, pure Python/numpy** → fully unit-testable; lives in `core/`.

### Public API
```
value_at(msg, col, t)  -> float | None     # linear interp (continuous signals)
latest_at(msg, col, t) -> float | None     # zero-order hold (discrete, e.g. MODE)
index_at(msg, t)       -> int   | None     # row at/before t (MSG text, replay frame)
time_range(msg)        -> (t0, t1) | None
batch(t, specs, step=) -> { label: value } # many (msg,col) in one call (panel/table)
```
`specs` accept `(msg, col)` or `(label, msg, col)`.

---

## 2. Interpolation Strategy

- **Continuous** (`value_at`): binary search (`np.searchsorted`) for the bracketing
  samples, then **linear interpolation** `v0 + (v1−v0)·(t−t0)/(t1−t0)`. Exact-hit and
  equal-timestamp cases handled explicitly. O(log n) per lookup.
- **Discrete** (`latest_at`): **zero-order hold** — value of the most recent sample
  at or before `t`. Correct for flight mode, arm state, and any step signal where
  linear interpolation would invent meaningless in-between values.
- **Robustness:** timestamps are sorted on first access (stable argsort), so
  non-monotonic logs interpolate correctly; values are aligned to the sorted axis via
  the cached permutation.

### NaN policy (no silent fabrication)
- Both bracketing samples NaN → `None`.
- One NaN → return the finite neighbour (no interpolation across a gap).
- Exact hit on a NaN sample → fall back (never returns NaN).
This matches the project rule established in Sprint-1.2: flag/expose gaps, don't invent.

---

## 3. Test Coverage (`tests/test_sample_service.py`, 19 tests)

| Area | Cases |
|------|-------|
| Interpolation | exact sample, midpoint, quarter-point, endpoints |
| Range guards | below-range → None, above-range → None |
| Missing data | missing message, missing column, empty message |
| NaN policy | NaN neighbour uses other side; exact NaN sample never returns NaN |
| Unsorted input | out-of-order timestamps interpolate correctly |
| Discrete (`latest_at`) | step hold, holds last value, before-first → None |
| Batch | labelled specs, step mode |
| `time_range`, `index_at` | present/absent |
| **Real log (02)** | `value_at('ATT','Roll')` matches `np.interp` within 1e-6; DesRoll + Roll both resolvable |

Full suite after this step: **173 passed** (154 prior + 19).

---

## 4. Performance (logs 02 / 11 / 12)

Benchmark: 5,000 full **Situational-Awareness panel resolves** (13 signals each:
ATT actual+desired ×3 axes, RCIN ×4, RCOU ×2, + MODE step) over random cursor times.

| Log | Types | Rows | Parse | `SampleService` init | Per panel (13 signals) | Throughput |
|-----|-------|------|-------|----------------------|------------------------|-----------|
| 00000002 | 92 | 106,296 | 1.1 s | ~0.00 ms | **23.9 µs** | 41,760 panels/s |
| 00000011 | 102 | 5,815,764 | 52.1 s | 0.43 ms | **24.6 µs** | 40,700 panels/s |
| 00000012 | 100 | 13,229,085 | 125.8 s | 4.17 ms | **25.7 µs** | 38,973 panels/s |

### Reading the numbers
- **Flat with log size.** 13.2 M rows costs ~24 µs/panel vs ~24 µs for 106 K — the
  O(log n) search adds only microseconds; lazy caching keeps init ≤ 4 ms.
- **Far beyond interactive.** A 60 fps frame budget is 16,700 µs; a full panel resolve
  is ~24 µs (**~700× headroom**). Cursor dragging on a 440 MB log updates every
  synchronized surface with the frame budget essentially untouched.
- **Parse time** (52 s / 126 s) is the existing chunk-scan cost, *not* SampleService;
  already tracked as a separate parser-performance follow-up. SampleService itself adds
  negligible load time.

### Memory
Lazy: only queried columns are materialised. The panel touches ~13 columns; even on
log 12 that is a few hundred MB of column views at most, and only for what is shown.

---

## 5. Conclusion / Next
SampleService meets the bar to drive every cursor-synced surface at interactive rates
on the largest logs provided. The sampling foundation is in place; the shared-cursor
UI (Timeline, Events, Situational Awareness, Values-at-Cursor, Snapshot) can be built
on it. Next per the approved order: **step 2 — `core/timeline_model.py`** (pure,
+ tests), then **step 3 — `core/rc_model.py`**, before any UI.
