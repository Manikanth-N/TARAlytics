# P1 Step 4 — Timeline UI: Design Package (pre-implementation)
## Timeline as the primary investigation surface; shared cursor as primary navigation

Design only — no UI code yet, per instruction. Grounded in the completed core:
`SampleService` (24 µs/batch, +provenance), `TimelineModel` (build ~1 ms,
FlightWindows), `RCModel` (20 µs pilot+output). Validation cases: logs 02 / 11 / 12.

---

## A. Screen Mockup

Timeline is a module in the stack; the **Cursor Context Panel + Values-at-Cursor**
live in a **persistent right dock** (always visible across every module, so numeric
context never requires switching screens — directly serving "minimize context
switching").

```
┌ ✦ TARAlytics · MISSION DEBRIEF STATION ──────────────────────────────────────────────┐
│ SN-01 · QUAD/PLUS · ArduCopter 4.6.3 · #002 · 0:43 · 10.0m · [◉ VERIFIED]   (flight bar)│
├────┬──────────────────────────────────────────────────────────────┬───────────────────┤
│ N  │ TIMELINE                                       [⤢][◀ev][ev▶]   │ CURSOR CONTEXT    │
│ A  │ ┌ FLIGHTS ─────────────────────────────────────────────────┐  │  T   152.30 s     │
│ V  │ │ [■ #0 ───────────────── armed 0:43 ─────────────────────] │  │  Mode  LOITER     │
│    │ ├ ALTITUDE (AGL m) ───────────────────── cursor▮ ─────────┤  │  Phase HOVER      │
│ D  │ │ 10┤        ╭──────────────────╮                          │  │  Alt   9.8 m AGL  │
│ T← │ │  5┤     ╭──╯              ┊   ╰──╮                        │  │  Spd   0.4 m/s    │
│ S  │ │  0┤─────╯                 ┊      ╰─────                   │  │ ───────────────── │
│ E  │ ├ PHASE  [TAKEOFF][  HOVER  ┊][ LAND ]────────────────────┤  │  PILOT   CTRL  A/C │
│ R  │ ├ MODE   [STAB][ GUIDED     ┊][ LAND ]────────────────────┤  │ R ▏0.00  ▎-2°  ▍-2°│
│ V  │ ├ EVENTS    ▲arm  ▲ekf    ⚠hit┊       ▲disarm              │  │ P ▏0.00  ▎ 1°  ▍ 1°│
│ R  │ ├ VERIFY [██████████ verified █████████]─────────────────┤  │ Y ▏0.00  ▎ 0°  ▍ 0°│
│ M  │ │  ◀═══════════ playhead ▮ (drag / click to scrub) ══════▶ │  │ T ▏0.48  ───── ▍0.59│
│    │ └──────────────────────────────────────────────────────────┘  │ ───────────────── │
│    │                                                              │  HDG 352°  GPS RTK │
│    │                                                              │  10 sat  HDOP 1.2  │
│    │                                                              ├───────────────────┤
│    │                                                              │ VALUES @ 152.30 s ★+│
│    │                                                              │ ATT.Roll    -2.1 ° │
│    │                                                              │ ATT.DesRoll -2.0 ° │
│    │                                                              │ RCIN.Roll(C1) 1490 │
│    │                                                              │ BARO.Alt     9.8 m │
│    │                                                              │ … (— if no data)   │
└────┴──────────────────────────────────────────────────────────────┴───────────────────┘
```

**Timeline lanes (top→bottom), all sharing one X (time) axis + one cursor line:**
1. **Flights** — one bar per `FlightWindow`. Multi-flight logs show several
   (log 11 → 3 bars; log 02/12 → 1). Click a bar = zoom X to that flight.
2. **Altitude** — `AltitudeProfile` (decimated ≤2000 pts), the visual spine.
3. **Phase** — colored `Phase` bands (TAKEOFF/HOVER/CLIMB/DESCENT/RTL/LAND…).
4. **Mode** — `ModeSegment` bands.
5. **Events** — `event_regions()` pins, colored by severity; hover = tooltip.
6. **Verify** — verified coverage band from `signature_verifier` chunk ranges
   (green = covered/intact; gap/red = uncovered/structure-error, e.g. log 11).
7. **Cursor + playhead** — one vertical line across all lanes; drag/click to scrub.

**Right dock (persistent, ~320 px, collapsible):**
- **Cursor Context Panel** — time, mode, phase, altitude, speed, heading, GPS, and a
  compact **Pilot / Controller / Aircraft** matrix per axis (R/P/Y/T). Answers
  "what was happening" without opening a plot.
- **Values-at-Cursor** — authoritative numeric table; pinned + active signals via
  `SampleService`; `—` when out of range (never fabricated).

---

## B. Widget Hierarchy

```
MainWindow
├── AppHeader + FlightIdentityBar                 (exists)
├── body (QHBoxLayout)
│   ├── NavigationRail                            (exists; + TIMELINE/EVENTS items)
│   ├── QStackedWidget (modules)                  (exists)
│   │   ├── DebriefModule … VerifyModule … MapTab (exist)
│   │   └── TimelineModule                        ← NEW (nav ②)
│   │       ├── ModuleHeader("TIMELINE")  [fit][◀ev][ev▶]
│   │       └── TimelineCanvas (QWidget, QPainter)
│   │            ├── lanes: FlightsLane, AltitudeLane, PhaseLane,
│   │            │          ModeLane, EventLane, VerifyLane   (paint only)
│   │            ├── CursorOverlay (vertical line + playhead)
│   │            └── x-transform (time↔px), zoom/pan state
│   └── CursorDock (QWidget, persistent right)    ← NEW
│        ├── CursorContextPanel                   ← NEW
│        │    ├── AttitudeMatrix (Pilot|Ctrl|A/C per axis)   (uses RCModel + SampleService)
│        │    └── readouts: time/mode/phase/alt/spd/hdg/gps  (SampleService/TimelineModel)
│        └── ValuesAtCursorTable                  ← NEW (SampleService)
└── MissionTimelineStrip (optional persistent bottom, Phase 2)  (deferred)
```

Shared **core** (already built, no Qt): `SampleService`, `TimelineModel`, `RCModel`,
`EventExtractor`. Step-4 widgets are thin renderers over these.

### AppState additions (shared-cursor infrastructure — small, additive)
```
# re-entrancy guard so one broadcast can't loop
def set_cursor_time(t):
    if self._broadcasting: return
    self._broadcasting = True
    try: self.cursor_time_changed.emit(t)
    finally: self._broadcasting = False

# lazy services rebuilt on data_changed (held once, shared by all surfaces)
@property sample_service  -> SampleService(self._data)
@property timeline_model   -> TimelineModel(self._data)
@property rc_model         -> RCModel.from_data(self._data)
cursor_time: float                      # last cursor (for late subscribers)
```
Existing legacy wiring (`crosshair_moved → tab_3d.set_time / tab_map.set_time`) is
**migrated** to go through `set_cursor_time`, so Plotter/Replay/Map join the one cursor.

---

## C. Update Flow (one operation updates everything)

```
 user selects event (Events list or a Timeline pin)
        │  AppState.jump_to_event(t)  →  set_cursor_time(t)  [+ request_module if needed]
        ▼
 AppState.set_cursor_time(t):  guard set → emit cursor_time_changed(t) → guard clear
        │
        ├──────────────┬──────────────┬───────────────┬──────────────┬───────────────┐
        ▼              ▼              ▼               ▼              ▼               ▼
   TimelineCanvas   Plotter       Replay           MapTab       CursorContext   ValuesTable
   move cursor line move          seek vehicle     move marker  batch(t,specs)  batch(t,active)
   + readout        crosshair     to t             to t         +RCModel pilot/  → text rows
                    (set_crosshair)                              output+ATT/GPS
        ▲                                                            │
        └─ Events list highlights current event ─────────────────────┘
```

**Loop-free contract:** any surface, on *user* interaction (drag Timeline, move plot
crosshair, scrub replay), calls `set_cursor_time(t)`. Handlers triggered by
`cursor_time_changed` move their own cursor **without** re-emitting; if one does, the
`_broadcasting` guard drops the echo. One source of truth, no feedback.

**Event → single operation** satisfies the success criteria: selecting an event emits
exactly one `set_cursor_time`, which fans out to Timeline, Events (highlight), Plotter,
Replay, Map, Horizon, RC viz, Values-at-Cursor, and Cursor Context Panel together.

**Data each surface pulls per cursor move** (all via the shared services):
- Context panel: ~9 readouts + `RCModel.pilot_input`+`servo_output` (8) + ATT Des/act
  (6) ≈ ~23 `SampleService` lookups.
- Values table: one lookup per visible/pinned signal (N, typically ≤ 20).
- Timeline: zero data lookups — just moves the cursor line + reads context from the
  panel’s values (lanes are pre-rendered on load).

---

## D. Performance Expectations (validated against 02 / 11 / 12)

### One-time, on log load (rebuild services + render lanes)
| | 02 (106K rows) | 11 (5.8M) | 12 (13.2M) |
|---|---|---|---|
| `TimelineModel.build()` | 0.6 ms | 0.9 ms | 1.5 ms |
| `SampleService` init | ~0 ms | 0.43 ms | 4.2 ms |
| `RCModel.from_data` | 0.35 ms | 0.37 ms | 0.41 ms |
| Altitude points rendered | ≤2000 (decimated) | ≤2000 | ≤2000 |

Lane rendering is independent of row count — the altitude profile is decimated to
≤2000 points and phase/mode/event/flight bands are tens–hundreds of segments
(log 11: 3 flights, 33 phases, 73 events). So the Timeline paints the same regardless
of 106 K vs 13 M rows.

### Per cursor move (the interactive hot path)
| Component | Cost | Basis |
|-----------|------|-------|
| Context panel data (~23 lookups) | ~0.5 µs × 23 ≈ **12 µs** | SampleService 24 µs/13-batch measured |
| Values table data (N≤20 lookups) | **~10–25 µs** | same |
| RCModel pilot+output | **~20 µs** | measured |
| **Total data resolution** | **< 100 µs** | flat across 02/11/12 (O(log n)) |
| Qt repaints (cursor line + ~30 small labels/bars) | **sub-millisecond** | small widgets |

**Budget:** 60 fps = 16,700 µs/frame. Data is < 100 µs (~0.6 % of budget); the
remainder is widget repaint, comfortably sub-ms for these small surfaces. **Cursor
dragging will be smooth on all three logs**, including the 440 MB / 13.2 M-row log,
because the per-move cost is dominated by tiny repaints, not data — and the data layer
is already proven flat with log size.

### Interaction policy
- Cursor scrubbing throttled to ≤ 60 Hz; each tick well inside budget.
- Out-of-range reads return `—` (no exceptions, no fabricated values).
- Truncated log 11: Verify lane shows the uncovered/`STRUCTURE_ERROR` region; the
  three flight bars + per-flight phases render from the existing `FlightWindow`s.

---

## E. Build Order Within Step 4 (each independently shippable)
1. **AppState shared-cursor infra** — guard + `sample_service`/`timeline_model`/
   `rc_model` accessors + `cursor_time`; migrate legacy crosshair wiring to it.
2. **TimelineCanvas + TimelineModule** — lanes + cursor; click/drag → `set_cursor_time`;
   `[◀ev][ev▶]` event stepping. Add TIMELINE nav item.
3. **CursorDock**: **ValuesAtCursorTable**, then **CursorContextPanel** (with the
   Pilot/Controller/Aircraft matrix via RCModel).
4. **Wire all surfaces** to `cursor_time_changed` (Plotter/Replay/Map/Events highlight)
   and verify the single-operation success criteria with a timed walkthrough on log 11.

Tests: an AppState cursor-broadcast/guard test (no-loop), a TimelineCanvas
time↔pixel transform test, and a CursorContextPanel data-binding test (values match
`SampleService` at T). Aesthetics frozen.

---

## F. Success-Criteria Trace
Selecting an event → one `set_cursor_time(t)` → updates Timeline · Events · Plotter ·
Replay · Map · Horizon · RC visualization · Values-at-Cursor · Cursor Context Panel.
All driven by the shared cursor + shared services; no per-surface recomputation;
loop-free; < 100 µs data cost on every log from 4 MB to 440 MB.
