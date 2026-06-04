# P4 — Investigation Workspace: Results

Goal: reduce tab-switching by keeping the investigator inside one workspace. No new
analytics. Suite 360 passing.

---

## What shipped

**P4.1 — Persistent Timeline Transport** ([ui/widgets/timeline_transport.py](../ui/widgets/timeline_transport.py))
A thin, always-visible strip at the bottom of the window (below every module): a
compact whole-flight MiniTimeline (mode bands · event pins · altitude spine · cursor)
plus reset / play-pause / speed. It is the **single global time control** — scrubbing
or playing here drives the shared cursor, so every surface follows it without
switching to the Timeline tab. Playback animates every surface.

**P4.2 — Workspace mode** ([ui/modules/mod_workspace.py](../ui/modules/mod_workspace.py))
A `▦ Workspace` nav entry with a simple split (primary pane + stacked secondaries)
and three built-in layouts:
- **Pilot Analysis** — Signals + Horizon + RC (Signals auto-loads the Attitude preset)
- **Accident Investigation** — Signals + Map + Events
- **Certification** — Evidence + Verification + Timeline

Each surface is a fresh instance wired to the shared AppState (the parsed DataFrames
are shared by reference, so this is cheap), all driven by the one cursor.

**P4.3 — Pop-out panels.** Horizon / RC / Map / Replay open as floating windows that
stay cursor-synced; **closing a floating window auto-re-docks it** into the layout.

**P4.4 — Saved layouts.** Save current / rename / delete custom layouts, persisted via
QSettings.

The persistent **Context dock** (right) and the new **Timeline transport** (bottom)
frame every layout, so context and time are always present.

Screenshots: `docs/screenshots/sprint_p4/` — `ws_pilot_log02.png` (Signals + Horizon +
RC on one screen), `ws_accident_log02.png`, `ws_cert_log02.png`,
`transport_on_signals_log02.png`.

---

## Validation — navigation actions before vs after

Each investigation modeled as the ordered surfaces the investigator must view; a
"navigation action" is a nav-rail module switch (the Context dock and Timeline
transport are always visible and cost nothing). Computed by
`scripts/p4_navigation_validation.py`:

| Investigation | before | after | reduction | layout |
|---|---:|---:|---:|---|
| Pilot over-control | 7 | 2 | **71 %** | Pilot Analysis |
| Oscillation (4 Hz roll) | 9 | 2 | **78 %** | Pilot Analysis |
| GPS anomaly | 8 | 2 | **75 %** | Accident Investigation |
| Crash reconstruction | 13 | 4 | **69 %** | Accident Investigation |
| **Total** | **37** | **10** | **73 %** | |

**Target ≥ 50 % — achieved 73 % overall** (every scenario individually ≥ 69 %). These
are conservative: *before* counts only distinct-module transitions, while real
investigations involve far more back-and-forth between Signals and the
attitude/map/event surfaces. In the workspace, that back-and-forth is **zero** module
switches — you scrub the transport once and watch everything move.

---

## Notes / honest scope
- The workspace renders **2–3 panels per layout** (the primary big, secondaries
  stacked) — sized for one screen and readable; more surfaces go to pop-out / second
  monitor, as recommended in the workflow review (no six-tiles-on-a-laptop).
- It is a **simple split**, not a free-form dock manager (deliberately, per the brief).
- Replay's panel relies on a desktop OpenGL context (unchanged limitation); the other
  surfaces render headless.
- No analytics or reports were added in P4 — purely a layout/co-presence feature on
  top of the existing shared cursor.
