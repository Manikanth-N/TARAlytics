# UAVLogViewer Study — Feature Audit & Integration Plan
## Reference: the official ArduPilot UAV Log Viewer (plot.ardupilot.org), Vue.js

Goal: learn from the de-facto standard tool without copying its UI or importing its
debt. Evaluate every feature against TARAlytics' architecture (AppState hub, Qt
modules) and the question: *does it help an engineer answer what/when/why/which-signals faster?*

**Architectural lesson up front:** UAVLogViewer has **no separate timeline module**.
Its Plotly time-series plot *is* the timeline — a range-slider plus **flight-mode and
event annotations overlaid directly on the signal plot**, with the Cesium 3D map
synced through a shared cursor (`$eventHub`: `hoveredTime`, `cesium-time-changed`).
This shapes our plan: the Timeline must be tightly coupled to the Plotter via one
shared cursor (we already have `AppState.cursor_time_changed`), not a parallel island.

---

## A. Feature Audit (Adopt / Adapt / Reject)

| Feature | Description | Value | Complexity | Recommendation |
|---------|-------------|-------|-----------|----------------|
| **Message/field filter search** | Filter box matches message types *and* field names live | High — kills the #1 plotter pain (hunting 92 types) | Low | **ADOPT** → Plotter search (P2) |
| **Mode/event annotations on plot** | Flight-mode bands + event pins drawn on the time axis | High — context where the data is | Med | **ADAPT** → Timeline strip + plotter overlay (already partial) |
| **Shared cursor time-sync (eventHub)** | One cursor syncs plot ↔ 3D map ↔ widgets | High — the backbone of correlation | Low | **ADOPT** (we have `cursor_time_changed`; extend to Timeline) |
| **Range slider** | Drag a sub-range of the flight | High | Low | **ADAPT** → Timeline scrubber (we have a range selector already) |
| **Cesium 3D map + trajectory color-coding** | Path colored by mode / signal value / range | High — spatial+value correlation | High | **ADAPT** ideas into Replay (color encoding), not Cesium itself |
| **Multiple trajectory/attitude sources w/ selector** | Pick GPS vs SIM vs AHRS vs EKF for path/attitude | High — cross-check, exactly our altitude-source lesson | Med | **ADOPT** → source selector in Replay/Timeline |
| **Expression editor (derived signals)** | Custom math (mavextra) → new plottable channel | Med-High — power-user analysis | High | **ADAPT** later (P2+); simple derived-channel form |
| **Instant values at cursor (interpolated)** | Y values of all plotted signals at cursor time | High — "values that prove it" | Low | **ADOPT** → Plotter values-at-time table (P2) |
| **ParamSeeker (param value at time T)** | Params change in flight; query value at a time | Med | Low | **ADAPT** → param-at-cursor in Events/Plotter |
| **EkfHelperTool** | EKF innovations/variances analysis helper | High for nav investigations | Med | **ADAPT** → Health "Navigation" drill-down preset |
| **TxInputs (RC stick viz)** | Visual RC transmitter inputs | Med — pilot-input correlation | Med | **ADAPT** later; RCIN preset in plotter first |
| **Popup/external plots (multi-window)** | Tear a plot into a new window | Low-Med | Med | **REJECT** for now (Qt MDI debt; use dual-axis instead) |
| **URL-shareable view state** | Time/Y ranges encoded in URL | Low (web idiom) | Low | **REJECT** (desktop); ADAPT as "save view/preset" |
| **CSV export** | Export plotted data | — | — | already have it |
| **MagFit / DeviceID viewers** | Calibration-specific tools | Low for flight-test investigation | Med | **REJECT** (out of scope) |

---

## B. Gap Analysis — TARAlytics (today) vs UAVLogViewer

### Where UAVLogViewer is clearly better today
1. **Signal discovery** — live filter over types+fields. TARAlytics has a static
   tree, no search. (Biggest day-to-day productivity gap.)
2. **Mode/event context on the plot** — UAVLogViewer overlays mode bands + event
   pins on the time axis; TARAlytics scatters events across 4 disconnected views.
3. **Spatial correlation** — Cesium path colored by mode/signal lets you *see*
   "where did the anomaly happen." TARAlytics' 3D is a plain tube.
4. **Source transparency** — explicit trajectory/attitude source selectors;
   TARAlytics silently picks one (the altitude-source bug we just fixed).
5. **Values-at-cursor** — UAVLogViewer reads off all signal values at a time;
   TARAlytics only shows a hover tooltip, no table.
6. **Param-at-time** — UAVLogViewer resolves changing params at any moment.

### Where TARAlytics is already better / will be
1. **Signature verification + chain of custody** — UAVLogViewer has none. This is
   TARAlytics' certification moat.
2. **Trustworthy parser** — post Sprint-1.2, complete + sentinel-free; UAVLogViewer
   relies on pymavlink/JS parsing with its own quirks.
3. **Structured Debrief verdict** — a single post-flight health/verify summary;
   UAVLogViewer drops you straight into raw plots.
4. **Native desktop performance + offline** — no browser/Cesium-token dependency.
5. **Health model** (Nav/Power/Propulsion/Structural) — UAVLogViewer has helper
   widgets but no rolled-up health verdict.

### Investigation-time advantages to capture
- One **shared cursor** across Timeline ↔ Plotter ↔ Replay ↔ Events (we have the
  signal; wire all four).
- **Click an event → everything jumps** (plot zoom, replay seek, timeline cursor).
- **Mode/phase bands** so "what mode was it in when X happened" is instant.

---

## C. Integration Opportunities (mapped to TARAlytics modules)

**1. Mission Timeline (P1a)** — adopt: mode bands, event pins, range scrubber,
shared cursor; adapt: altitude profile as the spine (UAVLogViewer uses the active
plot; we make altitude the always-on context).

**2. Unified Event Investigation (P1b)** — adopt: single event source (we have
`EventExtractor`), filter box; adapt: event→jump (plot/replay/timeline) from the
eventHub pattern; new: notes + investigation status (neither tool has this — our
certification edge).

**3. Replay (P2/P3)** — adapt: trajectory color-coding by mode/signal/value; source
selector; shared-cursor seek. Reject Cesium itself (keep pyqtgraph.opengl).

**4. Plotter (P2)** — adopt: message/field search, instant values-at-cursor table,
multi-axis; adapt: derived-channel expression (later), health-card signal presets.

**5. Debrief** — adapt: source transparency (show which altitude/trajectory source
fed each number); link health CAUTION → preset plot.

**6. Certification (future)** — none from UAVLogViewer (it has no signing); our own
chain-of-custody + evidence export remains differentiator.

---

## D. Priority Ranking (engineering value × user impact ÷ effort, with risk)

| Rank | Integration | Eng value | User impact | Effort | Risk | Target |
|------|-------------|-----------|-------------|--------|------|--------|
| 1 | Shared cursor: Timeline↔Plotter↔Replay↔Events | High | High | Low | Low | P1 |
| 2 | Event→jump (plot/replay/timeline) | High | High | Low | Low | P1 |
| 3 | Mode + phase bands on Timeline | High | High | Med | Low | P1 |
| 4 | Event pins + altitude profile spine | High | High | Med | Low | P1 |
| 5 | Plotter message/field search | High | High | Low | Low | P2 |
| 6 | Values-at-cursor table | High | Med | Low | Low | P2 |
| 7 | Health-card → signal preset | High | High | Med | Low | P2 |
| 8 | Trajectory color-coding (Replay) | Med | High | Med | Med | P2/P3 |
| 9 | Trajectory/attitude source selector | Med | Med | Med | Low | P2 |
| 10 | Notes + investigation status (Events) | Med | High | Low | Low | P1 |
| 11 | Param-at-cursor | Med | Med | Low | Low | P2 |
| 12 | Derived-signal expression | Med | Med | High | Med | P3 |
| 13 | EKF helper preset | Med | Med | Med | Low | P3 |
| 14 | TxInputs (RC viz) | Low-Med | Med | Med | Low | later |
| — | Popup plots, URL state, MagFit, Cesium | Low | Low | — | debt | REJECT |

**Guiding filter:** ranks 1–7 all directly cut time-to-answer for *what / when /
why / which-signals*. They are the P1–P2 core. Everything below 10 is opportunistic.
