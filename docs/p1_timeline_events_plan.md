# P1 Workflow Layer (REVISED) — Mission Investigation Workstation
## Timeline · Unified Events · Shared Cursor · Situational Awareness Panel

Supersedes the original two-module P1. Approved scope expansion: operational value
comes from **synchronized investigation**, not isolated widgets. Sprint-1.2 restored
the enabling data (`ATT` incl. `DesRoll/DesPitch/DesYaw`, `RCIN`, `RCOU`, `XKF`).

**Goal:** not a better log viewer — a **mission investigation workstation** for
post-flight review, crash investigation, pilot-behavior analysis, controller-behavior
analysis, and certification evidence review.

---

## 0. The Core Idea (one cursor moves every instrument)

Selecting an event, or scrubbing anywhere, emits **one** cursor time. Every surface
reads its own value at that time and updates. The investigator reads
*where + attitude + inputs + mode + signals + events* at a glance, then steps
event-to-event. This is the < 2-minute crash workflow made literal.

---

## A. Core Layer (pure, no Qt, fully testable)

```
core/timeline_model.py        flight structure from MODE/ARM/ALT
core/sample_service.py        value-at-time interpolation (the cursor's engine)
core/rc_model.py              RC channel -> axis normalization (RCMAP/REV/MIN/MAX)
core/event_extractor.py       (exists) single authoritative event source
```

### A1. `TimelineModel`
```
phases(data)           -> [Phase(name, t0, t1)]   PRE-ARM/TAKEOFF/CLIMB/
                                                   HOVER/CRUISE/RTL/DESCENT/LAND/POST
mode_segments(data)    -> [ModeSeg(mode, t0, t1)] from MODE changes
altitude_profile(data) -> (t[], agl[])            decimated for display (AGL hierarchy)
event_markers(data)    -> EventExtractor.collect(data)   (re-used, not duplicated)
```
Phase detection: ARM window + altitude derivative (climb/descend/hover) + MODE.

### A2. `SampleService` — the heart of the shared cursor
```
class SampleService:
    def __init__(self, data):           # precompute per (msg) sorted time arrays + column arrays
    def value_at(self, msg, col, t)     -> float | None    # binary search + linear interp; NaN-safe
    def latest_at(self, msg, col, t)    -> value | None     # step (for MODE/discrete)
    def batch(self, t, specs)           -> dict             # many (msg,col) in one call for the panel
```
- One instance built on `data_changed`, held by `AppState`. Every instrument calls
  `value_at`/`batch` — no per-widget interpolation code (kills the duplication risk).
- O(log n) per lookup; column arrays cached as numpy. Returns `None` outside range
  (panel shows `—`, never a fabricated value).

### A3. `RCModel` — pilot-input semantics
```
axis_channel(params)   -> {roll: C1, pitch: C2, throttle: C3, yaw: C4}  via RCMAP_*
normalize(pwm, ch, params) -> -1..+1 (roll/pitch/yaw) or 0..1 (throttle)
                              using RC{n}_MIN/TRIM/MAX and RC{n}_REV
```
Defaults RCMAP_ROLL/PITCH/THROTTLE/YAW = 1/2/3/4 when params absent. This makes
`RCIN.Roll` meaningful (= normalized C1), matching the differentiator examples.

---

## B. Shared Cursor System (AppState contract)

Reuses existing signals; adds the service + a re-entrancy guard.
```
AppState:
  # existing, reused:
  cursor_time_changed(float)      # the one cursor (absolute time)
  event_jumped(float)             # event selection -> also sets cursor
  signals_preload_requested(list) # event/health -> plotter preset
  data_changed(dict)
  # added:
  @property sample_service -> SampleService     # rebuilt on data_changed
  @property timeline_model  -> TimelineModel
  # guard: set_cursor_time() ignores echo within an in-flight broadcast
```
**Sync contract (prevents loops):** on user interaction a view calls
`AppState.set_cursor_time(t)`. AppState sets a `_broadcasting` flag, emits
`cursor_time_changed`, clears it. Every view's handler moves its cursor but, while
`_broadcasting`, does **not** re-emit. Single source of truth, no feedback loop.

Subscribers (all): Timeline, Plotter, Replay, Map, Situational Awareness Panel,
Events (highlights current), Verify (highlights covering chunk — read-only).

---

### A4. Investigation Snapshot system (cursor-powered)
Captures the full investigation context at the cursor (or a selected event) into a
structured, exportable record. Built entirely from `SampleService` + `TimelineModel`
+ `EventExtractor` — no new data.
```
core/snapshot.py
  build_snapshot(app_state, t) -> Snapshot{
    timestamp, event(nearest/selected), mode(latest_at MODE),
    location(POS/GPS lat/lng/alt AGL), altitude,
    pilot_inputs(RCModel: roll/pitch/yaw/throttle),
    controller_demand(ATT.DesRoll/DesPitch/DesYaw, RATE.*Des),
    aircraft_response(ATT.Roll/Pitch/Yaw, RATE.*),
    notes(from Events store) }
```
A snapshot is what an investigator attaches to a finding and what feeds future
certification evidence export (one row = one defensible "at T, the aircraft was…").

### C0. Persistent Values-at-Cursor table (authoritative numeric view)
The single source of truth for every cursor-synced surface. Always-available dock
listing the resolved value (via `SampleService`) of all active/pinned signals at the
current cursor time. The horizon, sticks, map readouts are *visual* renderings of the
same numbers this table shows — they cannot disagree, because all call `SampleService`.
```
[ VALUES @ 152.30 s ]                  pin ★  add +
  ATT.Roll      -2.1 °     ATT.DesRoll  -2.0 °
  RCIN.Roll(C1)  1490      RCOU.C1       1502
  BARO.Alt       9.8 m     MODE          LOITER
  ...                       (— when out of range; never fabricated)
```

## C. UI Layer

### C1. Mission Timeline (nav ②, primary surface)
Altitude profile (spine) + mode bands + phase bands + event pins + scrubber.
Click anywhere → `set_cursor_time`. `[◀ev][ev▶]` step events; double-click phase →
Plotter zooms to it. (Mockup unchanged from prior plan §C1.) Embeddable as a 64px
persistent bottom strip so temporal context is never lost.

### C2. Unified Events (nav ④, replaces 4 fragments)
Single source (`EventExtractor`). Severity + type filters, search, per-event Notes +
Status (open/reviewed/flagged), jump actions `[~plot][3D][⏱][map]`. Correlated ±2s
readout. (Mockup §C2 prior plan.) Persisted to
`data/investigations/<device_id>_<log_ctr>.json`.

### C3. Situational Awareness Panel — the instrument cluster
Embeddable in Timeline (bottom) and Replay (HUD). Every field via `SampleService`
at the cursor. **No new parsing — all fields exist post Sprint-1.2.**

```
┌ SITUATIONAL AWARENESS @ T = 152.30 s ─────────────────────────────────────────┐
│  ┌── ATTITUDE ──┐   HEADING       ┌ PILOT vs CONTROLLER vs AIRCRAFT ┐ POSITION │
│  │     ___      │    ◄ 352° ►      │ ROLL   pilot ▏  des ▎  act ▍   │ -35.3631 │
│  │    /   \  ●  │   (compass)      │ PITCH  pilot ▏  des ▎  act ▍   │ 149.1652 │
│  │   ‾‾‾‾‾‾     │                  │ YAW    pilot ▏  des ▎  act ▍   │ 9.8m AGL │
│  │ roll  -2°    │   MODE  LOITER   │ THR    pilot ▏        out ▍    │ 0.4 m/s  │
│  │ ghost = des  │   ARMED ✓        └────────────────────────────────┘ GPS RTK  │
│  └──────────────┘   GPS 10 sat                                        10 sat   │
│   actual ─── desired ┄┄┄                                                       │
└────────────────────────────────────────────────────────────────────────────────┘
```

Components (all QPainter, cursor-synced):
- **AttitudeIndicator** — artificial horizon: actual `ATT.Roll/Pitch` solid +
  **desired `ATT.DesRoll/DesPitch` ghost** overlay. Differentiator #1.
- **HeadingTape** — `ATT.Yaw` (compass arc); `DesYaw` tick for commanded heading.
- **PilotControllerStrip** — per axis three bars: **pilot** (`RCModel(RCIN.Cx)`),
  **desired** (`ATT.DesRoll/Pitch` or `RATE.{R,P,Y}Des`), **actual** (`ATT.Roll/Pitch`
  or `RATE.{R,P,Y}`); throttle shows pilot (`RCIN.C3`) vs **output** (`RCOU` mean).
  Differentiator #2.
- **Readouts** — Mode (`MODE` step), Armed, GPS fix/sats (`GPS.Status/NSats`),
  Speed, Altitude (AGL), Position.

### C4. Differentiators (explicit, what UAVLogViewer lacks)
- **Actual vs Desired attitude** — `ATT.Roll` vs `ATT.DesRoll` (+Pitch/Yaw). Shows
  whether the airframe tracked the command → **aircraft fault** vs healthy tracking.
- **Pilot vs Controller** — `RCIN.Roll(C1)` vs `ATT.DesRoll` vs `ATT.Roll`:
  - stick moved + des followed + act followed → **pilot action**, healthy.
  - des moved with no stick → **controller/autopilot behavior**.
  - des followed stick but act diverged → **aircraft/actuator fault**.
  Answers fault / controller / pilot **without opening a single plot.**

---

## D. Map Strategy
MAP stays a **separate module** (nav last). It **subscribes to the shared cursor**:
vehicle marker + event pins move with `cursor_time_changed`; clicking the path emits
`set_cursor_time`. Trajectory color-coding (mode/altitude/HDOP) deferred to P2.
Offline-capable (existing pyqtgraph map); no Cesium/Ion dependency.

**Nav order:** `DEBRIEF · TIMELINE · SIGNALS · EVENTS · REPLAY · VERIFY · MAP` (7).
Hidden-tab-bar pattern unchanged; existing references preserved.

---

## E. Data Flow

```
 parse ─ data_changed ─▶ AppState builds: SampleService(data), TimelineModel(data),
                                          events = EventExtractor(data)
                         │
        select event / scrub any surface ──▶ AppState.set_cursor_time(t)  [guarded]
                         │  cursor_time_changed(t)   (single broadcast)
   ┌─────────┬──────────┼───────────┬───────────┬───────────────┬──────────┐
   ▼         ▼          ▼           ▼           ▼               ▼          ▼
TIMELINE  PLOTTER    REPLAY        MAP      SITUATIONAL       EVENTS     VERIFY
cursor→   crosshair  vehicle@t   marker@t   AWARENESS @t     highlight  chunk@t
pin/phase +preload                pin       (horizon+sticks  current    (read-only)
                     via SampleService.batch(t, panel_specs)  +readouts)
```

---

## F. Migration (from fragmented event displays)
Unchanged from prior plan §D: remove `EventTable`/`EventTimeline` from Verification;
delete `ui/widgets/event_timeline.py`; Debrief "Notable Events" → read-only deep-link
into Events; Plotter keeps event overlay lines (shared source), drops duplicate
category panel.

---

## G. Implementation Order (approved, revised)
The sampling layer is the foundation of every cursor-driven workflow, so it goes
first.
1. **`core/sample_service.py`** + tests — value-at-time engine. ✅ DONE (step-1 report below).
2. `core/timeline_model.py` + tests (pure).
3. `core/rc_model.py` + tests (pure).
4. **Mission Timeline** (`mod_timeline.py`, `timeline_strip.py`) — shared cursor to
   Plotter + Replay.
5. **Unified Events** (`mod_events.py`, `event_table_unified.py`) — filters/search/
   notes/status/jump; switch Debrief Notable Events to deep-link; remove fragments.
6. **Situational Awareness Panel** (`attitude_indicator.py`, `rc_stick.py`,
   `situational_panel.py`) + **Values-at-Cursor table** + **Investigation Snapshot**
   (`core/snapshot.py`) — actual-vs-desired + pilot-vs-controller.
7. **Map synchronization** — MapTab subscribes to cursor; event pins.
8. **Replay synchronization enhancements** — embed panel as HUD; bidirectional seek.

Each step ships independently; tests updated alongside; Verification-tab tests
adjusted in the Unified Events commit.

---

## H. Workflow Validation (time-to-answer)

| Workflow | Path | Target |
|----------|------|--------|
| Post-flight review | Debrief verdict + Timeline shape | < 30 s ✓ |
| Crash investigation | Timeline anomaly → event → all surfaces @T (horizon shows attitude, sticks show inputs, map shows where) → step events | < 2 min ✓ |
| Pilot-behavior analysis | Situational panel: RCIN vs Des vs ATT per axis at T | no plots needed |
| Controller-behavior analysis | Des moved w/o stick; ATT tracks Des? RATE Des/Out | one panel |
| Certification evidence | Event → panel snapshot (attitude+inputs+mode) + note/flag → export | in-tool |

---

## I. Acceptance Criteria
**Selecting any event updates — via one cursor movement — all of:**
Timeline · Plotter · Replay · Map · Artificial Horizon · RC Visualization.

- One `set_cursor_time` broadcast; no feedback loops (guard verified by test).
- `SampleService.value_at` returns interpolated values matching a manual interp
  within tolerance; `None` outside range (no fabricated values).
- `RCModel` maps RCIN.C1→roll via RCMAP and normalizes with REV/MIN/MAX.
- Zero remaining duplicate event displays (single source proven by test).
- Crash walkthrough on log 11 timed < 2 min.

## J. Out of Scope for P1 (deferred → P2/P3)
Trajectory color-coding, derived-signal expressions, EKF/param-at-cursor widgets,
satellite-imagery layer. Aesthetics frozen.
