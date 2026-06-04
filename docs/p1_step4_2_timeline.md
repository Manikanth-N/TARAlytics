# P1 Step 4.2 — TimelineCanvas + TimelineModule
## Status: implemented, wired as the primary navigation surface (nav ②), tested, benchmarked, captured on logs 02 / 11 / 12.

The Timeline is now the first cursor-driven UI surface. It renders the flight's
temporal structure as stacked lanes over one time axis and drives the shared
cursor (`AppState.set_cursor_time`) on every interaction, so Plotter / 3D / Map
follow it through the Step-4.1 backbone. All structure comes from the already-built
`TimelineModel`; the canvas is a thin renderer.

---

## 1. Widget Hierarchy

```
MainWindow
└── QStackedWidget (hidden-tab page stack)
    └── [index 1] TimelineModule                         ← NEW, nav ② "TIMELINE"
        ├── ModuleHeader("TIMELINE")
        │     └── actions: [◀ Flight] [Flight ▶] [◀ Event] [Event ▶] [⤢ Fit]
        └── TimelineCanvas (QWidget · QPainter)          ← NEW
              ├── cached static QPixmap  (lanes 1–7, rebuilt only on data/view/size)
              │     ├── FlightsLane      (dominant; one bar per FlightWindow)
              │     ├── SummaryLane      (mission narrative strip)
              │     ├── AltitudeLane     (AGL spine, decimated ≤2000 pts)
              │     ├── PhaseLane        (Phase bands, coloured by kind)
              │     ├── ModeLane         (ModeSegment bands)
              │     ├── EventLane        (density underlay + clustered pins)
              │     └── VerifyLane       (coverage band from VerifyResult)
              ├── CursorOverlay          (live: vertical line + playhead + readout)
              └── view/zoom state + hit-test caches (flight rects, pin hits, lanes)
```

`TimelineCanvas` connects to three AppState signals: `data_changed` (rebuild
derived structure + reset view), `verification_changed` (invalidate the verify
lane), and `cursor_time_changed` (registered by name via `connect_cursor` —
cheap overlay-only repaint). It is the only new wiring; everything else flows
through the Step-4.1 backbone.

Module order is now `DEBRIEF · TIMELINE · SIGNALS · REPLAY · VERIFY · MAP`
(Timeline inserted at index 1; the two Debrief nav constants shifted Signals→2,
Verify→4).

---

## 2. Rendering Strategy

**Two-layer paint.** Lanes 1–7 are static for a given (data, view window, size);
they are rendered **once** into a `QPixmap`. Every `paintEvent` blits that pixmap
and draws only the **cursor overlay** (line + playhead triangle + a time/phase/mode
readout box). The pixmap is invalidated (set to `None`) on data change, zoom, pan,
verification change, or resize — never on a cursor move. This makes scrubbing
**independent of log size**: a cursor move never re-walks the data.

**Render order (back → front)**, exactly as specified:
1. **Flight Windows** — `FlightWindow` bars; **visually dominant for multi-flight
   logs** (lane grows 40→58 px when >1 flight, bars carry `F# · duration · peak ·
   events`). The bar containing the cursor gets a bright border.
2. **Mission Phase Summary** — a narrative strip: `N FLIGHTS · ARMED m:ss · PEAK
   x m · N EVENTS · N MODES` from `TimelineModel.summary()`.
3. **Altitude Profile** — `AltitudeProfile` polyline (decimated ≤2000 pts) with a
   faint fill; the visual spine. NaN-safe; min/max ticks.
4. **Phase Bands** — `phases()`, coloured per kind (TAKEOFF/CLIMB/HOVER/DESCENT/
   RTL/LAND/PRE_ARM/POST), labelled when the band is wide enough (>34 px).
5. **Mode Bands** — `mode_segments()`, palette keyed by `mode_num`.
6. **Event Pins** — density underlay + clustered pins (see §4).
7. **Verification Coverage** — band from `VerifyResult.state`: green *verified*,
   amber *partial / truncated* with a red hatched uncovered tail (e.g. log 11),
   grey *unsigned*. Coverage extent is state-driven (approximate; precise byte↔time
   mapping is a later step — called out honestly in the lane).
8. **Cursor** — the live overlay, drawn over the blitted pixmap.

Lane geometry is computed from a single `_lane_layout()` table, so heights/order
live in one place. Bands and the altitude path are clipped to the visible window,
so cost tracks *visible segments*, not total rows.

---

## 3. Interaction Model

Timeline is the **primary navigation surface**. All of:

| Gesture | Behaviour |
|---------|-----------|
| **Click** (lanes area) | jump the shared cursor to that time (`set_cursor_time`) |
| **Drag** (left) | scrub the cursor continuously |
| **Click a flight bar** | zoom X to that flight + cursor to its start |
| **Click an event pin** | single → `jump_to_event` (highlights Events); cluster → zoom into the cluster span |
| **Wheel** | zoom in/out around the pointer (1/2/5-clamped, ≤1e-4 of span) |
| **Right-drag** | pan the view window (clamped to log span) |
| **⤢ Fit** | reset to whole-log view |
| **◀/▶ Flight** | `step_flight(±1)` — jump to prev/next `FlightWindow`, zoom to it |
| **◀/▶ Event** | `step_event(±1)` — move cursor to prev/next raw event time, keep visible |

**Loop-free.** Every gesture calls `set_cursor_time`/`jump_to_event`; the canvas's
own `cursor_time_changed` handler only updates `_cursor` and repaints the overlay
(no re-emit) — the Step-4.1 `_broadcasting` guard absorbs any echo. The cursor the
Timeline shows is the *same* cursor the Plotter/3D/Map show.

Pure helpers `time_to_x` / `x_to_time` / `cluster_events` / `event_density` are
module-level (no Qt) so the transform and scalability logic are unit-tested directly.

---

## 4. Event Scalability (no assumption of small counts)

- **Clustering.** `cluster_events()` greedily merges visible events whose pixel
  positions fall within `CLUSTER_MIN_PX` (11 px). Each cluster keeps its member
  count and the **highest** severity (colour). 500 events in a 1000 px plot collapse
  to <120 pins with **zero loss** (`Σ count == 500`); a count badge marks clusters.
- **Density aggregation.** `event_density()` histograms event times into ~3 px bins
  and draws a faint underlay, so the *distribution* stays visible even where pins
  merge.
- **Zoom-aware.** Both are recomputed against the current view window, so zooming in
  splits clusters and reveals individual pins; zooming out re-aggregates. Cost is a
  single sorted pass over visible events (21–85 µs on logs 02/11/12).

---

## 5. Cursor Debugging Support

`AppState.cursor_debug_info()` — lightweight, **for synchronization debugging only**:

```python
{
  'cursor_time':      152.30,         # live shared-cursor position
  'broadcasting':     False,          # the re-entrancy guard state
  'subscriber_count': 4,              # Qt receiver count on cursor_time_changed
  'named_count':      4,
  'subscribers': ['TimelineCanvas', 'View3D', 'MapTab', 'Plotter'],
}
```

Surfaces register through the new `AppState.connect_cursor(slot, name)` (used by the
Timeline canvas and the migrated Plotter/3D/Map wiring), so the report lists exactly
who follows the cursor. `broadcasting` reads `True` if sampled *during* a broadcast
(verified by a test that samples from inside a subscriber) and `False` once it
clears — making a stuck guard or a missing subscriber immediately visible.

---

## 6. Performance Measurements (logs 02 / 11 / 12)

Measured offscreen via `scripts/timeline_capture.py` (best-of-N, 1320×340 canvas):

| log | rows | flights | phases | events | static render | **cursor move** | clustering |
|-----|-----:|--------:|-------:|-------:|--------------:|----------------:|-----------:|
| 02 | 106,296 | 1 | 5 | 29 | 2.50 ms | **329.6 µs** | 39.1 µs |
| 11 | 5,815,764 | 3 | 32 | 73 | 6.74 ms | **585.2 µs** | 84.9 µs |
| 12 | 13,229,085 | 1 | 29 | 25 | 7.79 ms | **845.3 µs** | 21.1 µs |

- **Static render** (one-time, on load/zoom/pan/resize): 2.5–7.8 ms. Grows ~3× while
  rows grow 124× → it tracks *segment/event counts*, not row count (altitude is
  decimated to ≤2000 pts; bands are tens of segments). Imperceptible as a one-off.
- **Cursor move** (the interactive hot path = full pixmap blit + overlay + phase/mode
  lookup): **0.33–0.85 ms**, i.e. **~20–50× inside** the 16.7 ms / 60 fps frame
  budget, on logs up to 440 MB / 13.2 M rows. Scrubbing is smooth on all three.
- **Clustering/density** (only on view change): 21–85 µs.

The hot path is dominated by the Qt blit, not the data — exactly the goal of the
cached-pixmap design, and consistent with the Step-1–3 finding that the data layer
is flat in log size.

---

## 7. Screenshots (`docs/screenshots/sprint_p1_step4_2/`)

- **`timeline_log02.png`** — single flight (`F1 0:44`), full altitude arc (climb→
  hover→land), phase/mode bands, 29 events with one tail cluster, cursor readout
  `144.42 s · HOVER · GUIDED`.
- **`timeline_log11.png`** — **the multi-flight / truncated showcase**: three
  dominant flight bars (`F1 0:25`, `F2 2:36 · 5 m · 16 ev`, `F3 1:56 · 3 m · 17 ev`),
  summary `3 FLIGHTS · ARMED 4:58`, severity-coloured event clusters (a red ERROR pin
  ~1550 s), and the VERIFY lane showing **amber "partial / truncated" with a red
  hatched uncovered tail** exactly where the battery was pulled and the hash chain
  stops.
- **`timeline_log12.png`** — 13.2 M-row, 14:49 flight rendering identically smoothly;
  single dominant bar, peak ~14 m, dense phase bands, LOITER mode.

---

## 8. Tests (`tests/test_timeline_canvas.py`, +21; suite 233 → 254)

| Area | Tests |
|------|-------|
| time↔pixel transform | endpoints, round-trip, out-of-view clamp, zero-span safety, 1/2/5 axis steps |
| event clustering | dense collapse with no loss, zoom-in split, max-severity, visible-only, density bins/empty |
| cursor debug | reports state+named subscribers; `broadcasting` True mid-broadcast / False after |
| canvas | loads structure, fit resets view, x↔t mapping, event stepping ±, flight stepping, render doesn't crash |
| multi-flight | three flight windows; `step_flight` walks all three in order |

Full suite: **254 passed** (was 233; no regressions). `test_ui_main` updated for the
6-tab stack + Timeline page.

---

## 9. Conclusion / Next
TimelineCanvas + TimelineModule are implemented, wired as nav ②, scalable to large
event sets, loop-free on the shared cursor, sub-millisecond per move on every log
from 4 MB to 440 MB, tested, and captured on 02/11/12. Per the approved Step-4 build
order, next is **Step 4.3 — CursorDock**: `ValuesAtCursorTable` first, then the
`CursorContextPanel` (Pilot/Controller/Aircraft matrix via `RCModel` + `SampleService`).
Awaiting approval before starting.
