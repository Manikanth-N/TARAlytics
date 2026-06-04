# P1.5 — Investigation Surfaces
## Unified Events · Artificial Horizon · RC Visualization · Map Synchronization
### Status: implemented, wired to the shared cursor, tested (286 passing), validated with the full one-click workflow on logs 02 / 11 / 12.

Goal of P1.5 was **investigation speed**, not new architecture: make the shared-cursor
backbone pay off by hanging four cursor-synced surfaces off it, so a single event
selection updates everything at once.

First, the Step-4.3 closeout that preceded this block:
- **Throttle row** added to the Pilot/Demand/Actual matrix (pilot stick / `CTUN.ThO`
  demand / `RCOU` servo output, 0..1).
- **Explicit divergence magnitude** — a **Δ** column showing `|demand − actual|`,
  colour-flagged (angles 8/20°, throttle 0.10/0.25), never fabricated.
- **★ Snapshot** placeholder action in the dock (records the cursor moment + count;
  evidence export is a later step).

---

## 1. Unified Events  ([ui/modules/mod_events.py](../ui/modules/mod_events.py))

- **Single authoritative source** — `EventExtractor.collect(data)`, the exact list
  the Timeline and Debrief use (test-asserted equal). No second event definition.
- **Search** — free-text over message + type, live row hiding.
- **Severity filter** + **Type filter** — combo boxes; type list is built from the
  log's actual event types. A `shown / total` counter tracks the filter.
- **Notes** — per-event, editable in-cell (double-click), stored by row.
- **Status** — per-event review state cycling `OPEN → REVIEWED → FLAGGED` (click the
  status cell), colour-coded.
- **Event stepping** — `◀ Prev / Next ▶` move to the event before/after the cursor.
- **Jump-to-cursor** — `⌖ At Cursor` selects the event nearest the current cursor.
- **Selecting any event drives the shared cursor** (`AppState.jump_to_event`) — this
  is the workflow trigger. Following the cursor highlights the nearest row **without
  re-emitting** (guarded), so there is no feedback loop (test-asserted: one move →
  one propagation).

## 2. Artificial Horizon  ([ui/widgets/horizon.py](../ui/widgets/horizon.py))

A classic attitude indicator: sky/ground card banked by `ATT.Roll`, pitched by
`ATT.Pitch`, with a pitch ladder, bank arc + pointer, and a fixed aircraft reference.
The controller's **desired attitude** (`ATT.DesRoll/DesPitch`) is overlaid as a
translucent **magenta ghost horizon**, so demand-vs-response shows up as a visible gap
between the white actual horizon and the dashed ghost. Cursor-synced; `NO ATTITUDE
DATA` when absent.

## 3. RC Visualization  ([ui/widgets/rc_viz.py](../ui/widgets/rc_viz.py))

Two Mode-2 stick boxes — **left** Yaw/Throttle, **right** Roll/Pitch. The **filled
dot** is pilot input (`RCIN`, made semantic by `RCModel`); the **hollow ring** is the
servo/motor output (`RCOU`) for the same axis, so pilot-vs-output is visible at a
glance. Four labelled value rows (Roll/Pitch/Yaw/Throttle, pilot + output) back the
sticks. Cursor-synced.

## 4. Map Synchronization  ([ui/tab_map_view.py](../ui/tab_map_view.py))

The 2-D track gains, on top of the existing altitude-coloured flight path and the
live position-at-cursor marker:
- **Event markers** — CRITICAL/ERROR/WARNING events placed on the track, coloured by
  severity.
- **Jumped-event highlight ring** — driven by `event_jumped`, rings the track position
  of the selected event, so you see *where on the path* it happened (flight-path
  context).

Both **Horizon** and **RC** live in a new **Situation** module
([ui/modules/mod_situation.py](../ui/modules/mod_situation.py)); **Events** is its own
module. Nav order is now `Debrief · Timeline · Events · Situation · Signals · Replay ·
Verify · Map`.

---

## 5. Full-Workflow Validation (one cursor movement updates every surface)

The required chain, driven by a **single event selection**:

```
Select Event (Events table / Timeline pin / stepping)
   └─ AppState.jump_to_event(t)  →  set_cursor_time(t)  [+ event_jumped]
        ├─▶ Timeline        cursor line + readout
        ├─▶ Cursor Context  flight/time/phase/mode/alt/speed/gps/sats/verify
        ├─▶ Attitude Matrix pilot/demand/actual/Δ (R/P/Y/T)
        ├─▶ Artificial Horizon  actual card + desired ghost
        ├─▶ RC Visualization    pilot sticks + servo output
        ├─▶ Map             position marker + event highlight ring
        ├─▶ Plotter / Replay crosshair / vehicle seek
        └─▶ Events          nearest row highlighted (no re-emit)
```

Verified live: selecting an event on log 02 moved the cursor to **148.08 s** and the
Timeline, Context, Matrix, Horizon, RC, and Map all read that instant — **8 named
cursor subscribers**: `TimelineCanvas, EventsModule, ArtificialHorizon,
RCVisualization, CursorDock, View3D, MapTab, Plotter` (from
`AppState.cursor_debug_info()`).

### Screenshots (`docs/screenshots/sprint_p1_5/`)
- **`window_situation_log02.png`** — the complete investigation station: Situation
  module (Horizon + RC) with the persistent dock (Snapshot · Context · Matrix+Δ ·
  Values) all at the event-selected cursor.
- **`window_situation_divergence_log12.png`** — a real divergence at 997 s: matrix
  **yaw Δ 45° (red)**, the RC box showing the pilot's hard-left yaw stick (−0.96), and
  the magenta ghost horizon offset from the actual horizon.
- **`window_events_log11.png`** — Unified Events on the truncated log: filterable
  table, severity badges, a selected event driving the cursor (1554 s), dock showing
  `STRUCTURE ERROR`.
- **`window_events_log02.png`**, **`window_map_log02.png`**,
  **`window_map_divergence_log12.png`** — Events + Map surfaces following the same
  cursor.

---

## 6. Tests (`tests/test_p1_5_surfaces.py`, +17; suite 269 → 286)

| Surface | Tests |
|---------|-------|
| Unified Events | single authoritative source, search/severity/type filters, notes persist, status cycles, **selecting row drives cursor**, event stepping ±, jump-to-cursor nearest, **following cursor does not loop** |
| Artificial Horizon | reads roll/pitch/desired at cursor, no-data flag + paints safely |
| RC Visualization | pilot + servo populate at cursor |
| Map sync | trajectory + events loaded, set_time moves position, highlight_event rings nearest |
| **Full workflow** | one `selectRow` → Timeline + Context + Horizon + RC + Map all reflect the same cursor |

Plus the Step-4.3 closeout tests (Δ magnitude, throttle row, snapshot). Full suite:
**286 passed**, no regressions. `test_ui_main` updated for the 8-tab stack.

---

## 7. Conclusion / Next
The shared cursor now drives eight surfaces; a single event selection updates the
entire investigation view, which was the goal. Held for your direction on what
follows (e.g. Investigation Snapshot export to replace the placeholder, the usability
additions flagged in Step 4.3 — vertical-speed, EKF/position divergence — or Step 4.4
formal wire-all sign-off).
