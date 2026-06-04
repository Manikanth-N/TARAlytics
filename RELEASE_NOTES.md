# TARAlytics — Release Notes

## v2.0.1

### Customizable navigation (new)
The navigation rail is now **configurable** — show only the modules you use. Open the
manager from the **gear (⚙) at the bottom of the nav rail**, the **⚙ Modules** toolbar
button, or **View → Customize Navigation…** (Ctrl+Shift+M). Pick a preset
(**Minimal / Flight Test / Full / Custom**), check modules to show/hide, and
**drag to reorder**. Hidden modules are never removed — they stay fully available
(including to Workspace panels) and re-enable instantly. Selections persist per user.

**Migration**
- **Existing users keep the Full layout** — no module disappears after upgrading.
- **New installs start on Minimal** (Debrief · Workspace · Verification · Replay · Map);
  everything else is one click away via the gear.
- Switch presets or build your own at any time; "Restore Defaults" returns to Full.

## v1.1.0-rc1 — Mission Investigation Workstation (Release Candidate 1)

First release candidate of the investigation workstation. TARAlytics moves from a
log viewer to a **mission investigation workstation**: a shared cursor drives every
surface, and findings can be captured and exported as evidence — entirely within the
application.

### Highlights
- **Shared-cursor workflow** — one cursor drives nine surfaces. Selecting an event
  updates Timeline, Cursor Context, the Pilot/Controller/Aircraft matrix, the
  Artificial Horizon, RC Visualization, and the Map together, with no plot-hopping.
- **Timeline** — primary navigation surface: flight-window / phase / mode / altitude
  / event / verification lanes, click-to-jump, drag-to-scrub, wheel zoom, event and
  flight-window stepping, zoom-aware event clustering.
- **Unified Events** — single authoritative source with search, severity/type
  filters, per-event notes and review status, stepping and jump-to-cursor.
- **Situational Awareness** — Artificial Horizon with a desired-attitude ghost, and
  RC Visualization (Mode-2 sticks, pilot vs servo output).
- **Cursor Context dock** — flight #, time, phase, mode, altitude, speed, GPS,
  satellites, verification, and the Pilot / Demand / Actual + **Δ** matrix, plus
  **vertical speed**, **EKF health**, and **position-divergence** indicators.
- **Evidence & Investigation Capture** — Investigation Snapshots capture the full
  cursor moment with **per-value provenance** (source field, sample timestamp,
  interpolated flag, bracket samples); manage them and export to **JSON / Markdown /
  PDF**.

### Investigation aids
- Vertical speed (`BARO.CRt` → `CTUN.CRt` → `−GPS.VZ` → altitude derivative).
- EKF health from `XKF4` normalised test ratios + fault flags.
- Position divergence from `XKF3` position innovations.

### Workflow performance (measured)
- Post-flight review: **1 click** to answer. Anomaly investigation: **3 clicks**
  (incl. evidence capture). Pilot-vs-controller: **2 clicks**. Cursor moves are
  sub-millisecond and flat in log size up to 13.2 M rows.

### Correctness
- Parser correctness fixes (signed-chunk exclusion, FMT stride), armed-window
  duration, and the altitude source hierarchy carried forward from the data-accuracy
  work. Validated on logs of 4 MB, 193 MB (truncated/multi-flight), and 440 MB.

### Known limitations
- 3-D Replay requires a desktop OpenGL context (unavailable headless) and is not yet
  embedded in snapshots — a future enhancement, not a blocker.
- Verify-lane coverage *extent* is state-driven (approximate); the verdict is exact.
- Large logs (440 MB) have a multi-minute one-time parse cost.
- Snapshots are in-session; persistence is via export.
See `docs/p2_1_rc_review.md` for the full readiness assessment and risk register.

### Tests
311 passing (pure-core, Qt surfaces, full select→investigate→capture→export workflow).

---

_Previous 1.0.x releases: signature verification, signal plotter, 3-D view, 2-D map._
