# UAVLogViewer Audit — Second Pass (Operational Investigation Focus)
## Correcting the first pass: instruments that compose into an investigation workstation

The first audit (`uavlogviewer_audit.md`) judged the Artificial Horizon, RC stick
view, and time-synced map as **isolated widgets** and under-rated them
(Adapt-later / Low-Med). That was the wrong lens. Operationally, when all bound to
**one shared cursor**, they stop being widgets and become a **synchronized
instrument cluster** — the difference between "a plot tool" and "an accident-
investigation workstation." This pass re-evaluates them by *investigation workflow*.

**Critical enabler:** Sprint-1.2 just restored the data these need. Pre-fix,
`ATT` was missing entirely — an attitude horizon was impossible. Now available:
`ATT` (incl. **DesRoll/DesPitch/DesYaw — commanded vs actual**), `RCIN` (pilot
channels), `RCOU`, `XKQ` (quaternions). The instruments are now buildable.

---

## 1. Artificial Horizon (synchronized attitude instrument)

UAVLogViewer renders a live attitude indicator that reads roll/pitch **at the
cursor time** and updates as you scrub. It is the single fastest way a human reads
"what was the aircraft doing."

| Context | Usefulness | Why |
|---------|-----------|-----|
| **Crash investigation** | **Very High** | Instantly shows loss-of-control, inversion, unrecoverable attitude at the moment of the event — faster than reading 3 Euler plots |
| **Flight review** | High | Sanity-check attitude through phases; spot oscillation/PIO at a glance |
| **Certification evidence** | Medium-High | A screenshot of attitude at a flagged event is intuitive evidence for a non-expert reviewer (DGCA) |
| **Pilot-training analysis** | High | With **commanded vs actual** overlay, shows whether the airframe tracked the demand |

**Decisive advantage TARAlytics can exceed UAVLogViewer on:** our `ATT` has
**DesRoll/DesPitch/DesYaw**. Draw the *desired* attitude as a ghost on the same
horizon → instantly separates "aircraft did something" from "aircraft was commanded
to do something." UAVLogViewer's horizon shows actual only.

**Recommendations:**
- **Mini attitude widget** — **ADOPT.** Small, cursor-synced, embeddable.
- **Synchronized attitude replay** — **ADOPT.** It IS the mini widget driven by the
  shared cursor; near-zero extra cost.
- **Attitude panel in Timeline** — **ADOPT** (as part of the Situational Awareness
  strip, §5) — attitude is core context.
- **Attitude panel in Replay** — **ADOPT.** Corner HUD instrument next to the 3D view.
- **Differentiator:** commanded-vs-actual ghost overlay (ADOPT, unique to us).

---

## 2. RC Controller / Stick Visualization

UAVLogViewer's TxInputs interpolates `RCIN` channels at the cursor and renders two
sticks, mapping channels to axes via `RC1_REV..RC4_REV` params (respects reversing).

| Axis | Source | Investigation value |
|------|--------|---------------------|
| Roll stick | RCIN C1 (×RCx_REV) | pilot lateral demand |
| Pitch stick | RCIN C2 | pilot longitudinal demand |
| Throttle | RCIN C3 | power demand / collective |
| Yaw stick | RCIN C4 | heading demand |
| Mode switch | RCIN C5+ / MODE | commanded mode at time T |

**Questions answered:**
- *Was a maneuver pilot-induced?* **Yes, directly.** Stick deflection at T next to the
  attitude/rate response at T = pilot input vs vehicle reaction, side by side.
- *Pilot action vs controller behavior?* **Yes** — overlay **RCIN (pilot) vs RCOU
  (servo/motor output) vs Des* (controller demand)**. If attitude moved with no
  stick input but with RCOU change → autopilot/controller, not pilot. This triad is
  the crux of incident attribution.
- *Usable by certification teams in incident review?* **Yes.** "Pilot commanded full
  right roll 0.2 s before departure" is defensible, intuitive evidence.

**Recommendation: ADOPT (raise from first-pass "Adapt later").**
Justification: it is the *only* view that distinguishes human cause from machine
cause — the central question of most incident investigations. It was undervalued
because it was judged as a standalone widget; as a cursor-synced member of the
situational panel it is top-tier. Build it as a small stick-pair instrument + a
"pilot vs controller" overlay preset in the Plotter (RCIN/RCOU/Des*).

---

## 3. Time-Synchronized Maps

UAVLogViewer's Cesium map: satellite imagery (Ion), clock-driven playback, vehicle
animated by `SampledPositionProperty` + quaternion, trajectory **color-coded by
mode / signal value / range**. It is a time-synced spatial surface, not a static map.

| Capability | Investigation value | Note for TARAlytics |
|-----------|--------------------|---------------------|
| Satellite imagery | High — see terrain/obstacles at the crash point | Needs online tiles/token; offline is a constraint |
| Flight-path viz | High | We have 2D map + 3D replay already |
| Event location | **Very High** | Pin events on the path → "where did it happen" |
| GPS-anomaly investigation | High | Color path by HDOP/sats → see where GPS degraded spatially |
| Color-by-mode/value | **Very High** | "Show me the path colored by altitude/throttle/HDOP" |

**Questions:**
- *Should MAP stay a separate screen?* **No — demote it.** A standalone 2D map that
  doesn't share the cursor is low value (the gap the first pass missed).
- *Should MAP become part of Timeline?* **Partially.** The Timeline owns *time*; the
  Map owns *space*. Keep Map as a view, but make it a **cursor-synced peer** that the
  Timeline drives — not an island. Event pins appear on both.
- *Should Replay and MAP share a common cursor?* **Yes, mandatory.** Replay (3D),
  Map (2D), Timeline, Plotter, Attitude, RC all read the one `cursor_time_changed`.

**Recommendation:** **ADAPT** (not adopt-Cesium). Keep our pyqtgraph 2D map + GL 3D
replay; (a) bind both to the shared cursor, (b) add event pins, (c) add trajectory
**color-coding by mode/signal/HDOP** (the genuinely high-value idea), (d) treat
satellite imagery as an *optional online layer* so the tool stays offline-capable
for the field. Reject the Cesium dependency + hardcoded Ion token (debt, online-only).

---

## 4. Spatial Investigation Workflow (integrated)

How an engineer answers the six questions, in one flow, driven by one cursor:

| Question | Surface that answers it (at cursor T) |
|----------|----------------------------------------|
| **Where did it occur?** | Map pin / 3D vehicle position |
| **What was it doing?** | Artificial horizon (attitude) + speed/alt readout |
| **What were the pilot inputs?** | RC stick instrument (RCIN) |
| **What was the attitude?** | Horizon, with Des* ghost (commanded vs actual) |
| **What mode was active?** | Timeline mode band / mode readout |
| **What events occurred nearby?** | Timeline event pins ±window / Events list |

**Integrated workflow:** select an event (or scrub the Timeline) → the cursor moves
→ every surface above updates to time T simultaneously. The engineer reads
*where + attitude + inputs + mode + nearby events* in a single glance, then steps
prev/next event to reconstruct the sequence. No screen-hopping, no manual signal
hunting. This is the < 2-minute crash workflow made literal.

---

## 5. Situational Awareness Panel (proposal)

A compact, always-available **instrument cluster** bound to the shared cursor —
the cockpit-at-time-T. Embeddable in Timeline (bottom) and Replay (corner HUD).

```
┌ SITUATIONAL AWARENESS @ T = 152.30 s ───────────────────────────────────┐
│  ┌─ ATTITUDE ─┐   HEADING        PILOT INPUTS        POSITION            │
│  │   ___      │     ◄ 352° ►     ┌────┐  ┌────┐      Lat -35.36312       │
│  │  /   \  ●  │   (compass arc)  │ ·  │  │  · │      Lng 149.16524       │
│  │ ‾‾‾‾‾‾‾    │                  │left│  │righ│      Alt  9.8 m AGL      │
│  │ roll -2°   │   MODE  LOITER   └────┘  └────┘      Spd  0.4 m/s        │
│  │ ghost=des  │   ARMED  ✓       thr 48% yaw +3°     VSpd -0.3 m/s       │
│  └────────────┘                                                          │
│  actual ─── desired ┄┄┄   (RCIN solid · RCOU hollow)                     │
└──────────────────────────────────────────────────────────────────────────┘
```
Every field reads its value at the cursor via interpolation. The attitude shows
actual + desired; the sticks show RCIN (pilot) with optional RCOU (output) markers.
One panel = the answer to "what was happening" at any instant.

**Data:** all present post Sprint-1.2 — ATT (+Des*), XKQ, RCIN, RCOU, MODE, POS/GPS,
SIM2/derived speed. No new parsing required.

---

## 6. Mission Investigation Workspace (event → update everything)

Selecting an event (in Events or a Timeline pin) instantly drives **one cursor
broadcast** that updates all surfaces — the accident-investigation feel:

```
            select event "Hit ground @168.48s"
                          │  AppState.set_cursor_time(168.48)  +  jump_to_event
        ┌──────────┬──────┴─────┬───────────┬───────────┬───────────┐
        ▼          ▼            ▼           ▼           ▼           ▼
    TIMELINE    PLOTTER       REPLAY        MAP      ATTITUDE     RC INPUT
   cursor→pin  crosshair+   vehicle at   pin at    horizon at   sticks at
   phase=LAND  preload      168.48s      168.48s   168.48s      168.48s
   mode=LAND   correlated                          (+Des ghost) (pilot demand)
               signals
```

The engineer never assembles context manually; selecting *when* yields *where +
attitude + inputs + mode + signals* at once. Add Notes + Status on the event →
evidence capture in the same motion (our certification edge).

---

## 7. Re-Ranked Integrations (operational value first)

Re-ranked with the situational-awareness composition in mind. The instruments rise
sharply because their value is **multiplicative under the shared cursor**, not additive.

| Rank | Integration | Why it moved | Eff | Risk | Target |
|------|-------------|--------------|-----|------|--------|
| 1 | **Shared cursor** across all surfaces | The multiplier for everything below | Low | Low | P1 |
| 2 | **Event → update-everything** workspace | The core investigation motion | Low | Low | P1 |
| 3 | **Artificial horizon (synced, +Des ghost)** | ↑ from mid — fastest "what was it doing"; we beat UAVLogViewer w/ commanded-vs-actual | Med | Low | **P1/P2** |
| 4 | **RC stick + pilot-vs-controller overlay** | ↑ from "later" — only view that attributes human vs machine cause | Med | Low | **P1/P2** |
| 5 | Timeline: alt spine + mode/phase bands + event pins | Temporal context surface | Med | Low | P1 |
| 6 | **Situational Awareness panel** (composes 3,4 + readouts) | The workstation feel | Med | Low | **P2** |
| 7 | Map as cursor-synced peer + event pins | ↑ — spatial "where" bound to time | Med | Med | P2 |
| 8 | Trajectory color-coding (mode/signal/HDOP) | spatial anomaly localization | Med | Med | P2 |
| 9 | Plotter message/field search | discovery speed | Low | Low | P2 |
| 10 | Values-at-cursor table | "signals that prove it" | Low | Low | P2 |
| 11 | Health-card → signal preset | guided drill-down | Med | Low | P2 |
| 12 | Source selectors (attitude/trajectory) | cross-check honesty | Med | Low | P2 |
| 13 | Param-at-cursor / derived signals / EKF helper | power-user depth | High | Med | P3 |
| — | Cesium dependency, Ion token, popup plots, URL state | online-only / web debt | — | — | REJECT |

**First-pass corrections (explicit):**
- Artificial Horizon: *unlisted/mid* → **Rank 3** (P1/P2).
- RC stick viz: *"Adapt later", Low-Med* → **Rank 4** (P1/P2).
- Map: *"reject Cesium, low"* → **Rank 7** as a cursor-synced peer (ADAPT, not reject).

---

## 8. Bottom line
The investigation power is not in any one instrument — it is in **one cursor moving
every instrument at once**. That composition turns TARAlytics from a plot tool into
a professional flight-investigation workstation, and Sprint-1.2 already restored the
data (ATT/RCIN/XKQ) it requires. Recommend folding the **Artificial Horizon** and
**RC stick** instruments into the P1/P2 scope as first-class members of the
Situational Awareness panel, all driven by the shared cursor, with the
commanded-vs-actual and pilot-vs-controller overlays as differentiators UAVLogViewer
does not have.
