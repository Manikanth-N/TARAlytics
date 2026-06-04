# P1 Step 2 — TimelineModel + SampleService provenance
## Status: implemented + tested + benchmarked. UI not started.

Also adds the **provenance** capability requested at the close of Step 1.

---

## 0. SampleService provenance (Step-1 addendum)

`SampleService.sample_at(msg, col, t) -> Sample` returns a value with its origin —
for Investigation Snapshots, Evidence Export, and certification.

```
@dataclass(frozen=True) Sample:
    value: float | None
    msg: str            # source message
    col: str            # source field
    t: float            # query (cursor) time
    interpolated: bool  # True if linearly interpolated between two samples
    sample_t: float|None   # exact sample time when NOT interpolated
    bracket: (t0,t1)|None  # bracketing sample times when interpolated
```
Same cost as `value_at` (one binary search). Use `value_at` on the per-frame hot
path; `sample_at` when capturing evidence. Covered by 5 added tests (24 total in
`test_sample_service.py`).

---

## 1. Architecture Notes (TimelineModel)

- **Pure core, no Qt.** Inputs: the parsed `data` dict. Outputs: plain frozen
  dataclasses any surface can consume.
- **Single authoritative sources:** events from `EventExtractor`, mode names from the
  shared `MODE_NAMES`, altitude from the documented AGL hierarchy (matches
  `FlightMetrics`). No duplicated domain logic.
- **Defensive:** missing ARM, sparse MODE, truncated logs, and missing altitude each
  degrade to a sensible partial timeline — never raises.
- **Consumer-shaped:** `build()` returns one `Timeline` bundle; helpers `phase_at(t)`
  / `mode_at(t)` serve Snapshot and Verification highlighting; `arm_regions` and
  `mode_segments` serve Replay; `events` serves Event Investigation.

---

## 2. Timeline Data Structures

```
Segment(t_start, t_end)              .duration  .contains(t)
Phase(Segment, kind)                 kind ∈ PRE_ARM/TAKEOFF/CLIMB/HOVER/
                                            DESCENT/RTL/LAND/POST/FLIGHT
ModeSegment(Segment, mode, mode_num)
ArmRegion(Segment, source)           source ∈ 'ARM' | 'EV'
AltitudeProfile(times, agl, source)  .empty
Timeline(t_start, t_end, arm_regions, modes, phases, altitude, events)
```

### Derivation
- **arm_regions** — ARM state transitions; fallback to EV armed(10/15)/disarmed(11);
  truncated (armed, never disarmed) → region extends to log end. Supports **multiple
  arm windows** (multi-flight logs).
- **mode_segments** — MODE changes, consecutive duplicates merged, last mode holds to
  log end.
- **altitude_profile** — AGL hierarchy `RelHomeAlt → BARO → SIM2(-PD) → POS.Alt`,
  decimated to ≤ `max_points`.
- **phases** — within each arm window, AGL is resampled (0.5 s) and a smoothed
  vertical-rate state machine yields CLIMB/HOVER/DESCENT; the first climb-from-ground
  → TAKEOFF, the final descent-to-ground → LAND; RTL/LAND **mode** segments override
  the label. PRE_ARM/POST bracket the armed time. Slivers (< 0.05 s) merged for clean
  bands. Falls back to a single FLIGHT phase when altitude is unavailable.

### Thresholds (documented, conservative)
`ground = 1.0 m · vrate = 0.3 m/s · resample = 0.5 s · smooth = 3 · min_phase = 0.05 s`

---

## 3. Test Coverage (`tests/test_timeline_model.py`, 16 tests)

| Scenario | Cases |
|----------|-------|
| Normal flight | span, single arm region, phase sequence (PRE_ARM…TAKEOFF/HOVER/LAND…POST), **contiguity + full-span coverage**, altitude source/peak, phase_at/mode_at |
| Mode transitions | duplicate merge, correct labels, no consecutive dup mode_nums |
| RTL | RTL mode segment relabels the overlapping phase |
| Truncated log | armed-never-disarmed region extends to log end; phases end at span |
| Missing events | no ARM/MODE → single FLIGHT; EV fallback derives arm region |
| Sparse mode | single mode → one segment; no altitude → FLIGHT fallback |
| Real log (02) | complete `build()`, armed window 126.99→170.57, 29 events, altitude source = AGL (peak < 60 m, not 594 m AMSL) |

Full suite after Step 2: **194 passed** (24 sample-service + 16 timeline + prior).

---

## 4. Performance + Example Outputs (logs 02 / 11 / 12)

| Log | Rows | `init` | `build()` |
|-----|------|--------|-----------|
| 00000002 | 106 K | 5.7 ms | 0.6 ms |
| 00000011 | 5.8 M | 23.5 ms | 0.9 ms |
| 00000012 | 13.2 M | 51.8 ms | 1.5 ms |

`init` cost is the one-time log-span scan (iterates each message's TimeS); `build()`
itself is ~1 ms because phase classification runs on the resampled altitude, not raw
rows. Well within interactive budget; computed once per log.

### Example outputs
**log 02** (complete, 0:58 span):
```
arm:    [127.0 → 170.6 (ARM)]
modes:  STABILIZE@127 · GUIDED@132.1 · LAND@148.1
phases: HOVER · CLIMB · HOVER · LAND · POST
alt:    POS.RelHomeAlt, 586 pts, peak 10.0 m
events: 29
```
**log 11** (truncated, 6:29) — **multi-flight log surfaced**:
```
arm:    [1355.2→1380.6] [1396.4→1552.3] [1613.1→1729.5]   (3 separate flights)
modes:  LOITER (sparse — single mode)
phases: 33 (per-window CLIMB/HOVER/DESCENT)
alt:    POS.RelHomeAlt, peak 4.8 m
events: 73
```
**log 12** (440 MB, 15:04):
```
arm:    [110.7 → 1000.2 (EV fallback)]
modes:  LOITER
phases: 29
alt:    POS.RelHomeAlt, 2000 pts (decimated), peak 14.0 m
events: 25
```

Notable: log 11's **three arm regions** (multiple flights in one file) were derived
automatically — exactly the kind of structure the Timeline view must show, and a
case the per-window phase logic already handles.

---

## 5. Conclusion / Next
TimelineModel produces clean, contiguous phase/mode/arm/altitude/event structures for
all three logs, handles truncated/sparse/missing/multi-arm cases, and builds in ~1 ms.
Together with SampleService (+provenance) the cursor's data foundation is complete.
Next per the approved order: **Step 3 — `core/rc_model.py`** (RCMAP/REV normalization,
pilot-input semantics), pure + tests, before any UI.
