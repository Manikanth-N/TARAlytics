# TARAlytics — Operational Review (brutally honest, real-usage)

Reviewed against the **implemented** UI and the captured screenshots, from six
operator roles. Not a code review. The design is **not** assumed correct.

The one-line verdict up front: **TARAlytics is an excellent instantaneous
state-at-the-cursor inspector, and a poor flight-analysis tool.** It tells you, with
real rigour, *what was happening at this exact moment*. It does almost nothing to tell
you *what is wrong with this flight* without you manually scrubbing and eyeballing.
Everything below follows from that single gap.

---

## A. Pilot Analysis Workflow — can the pilot answer in 60 s?

| Question | Answerable in 60 s? | Reality |
|----------|:---:|---------|
| Did I fly correctly? | ⚠️ Partly | Debrief health grid gives a coarse NOMINAL/CAUTION; no flight-quality score |
| Did I overcontrol? | ❌ No | No control-activity / stick-rate / reversal metric anywhere |
| Was the aircraft following my commands? | ⚠️ One instant only | Matrix Δ shows tracking error **at the cursor**, never over the flight |
| Was the autopilot fighting me? | ❌ No | No pilot-vs-autopilot conflict indicator; not mode-aware |
| Controller saturation? | ❌ No | RCOU shows raw PWM in the values table; no "at limit" / I-term windup flag |
| Oscillation? | ❌ No | No oscillation/ringing/FFT detection; requires manual plot eyeballing |
| Excessive yaw correction? | ❌ No | No yaw-activity or heading-error metric |
| Smooth landing? | ❌ No | No touchdown-rate metric; you must scrub to touchdown and read V.Speed yourself |

**Verdict: the pilot cannot answer 6 of 8 in 60 seconds.** Every "yes/partly" is a
*single-cursor* read, not a flight summary. What's missing is an entire class of
**derived, over-time metrics**: control activity, stick reversals, tracking-error RMS,
oscillation detection, output saturation, touchdown rate. The tool makes the pilot do
the analysis; a debrief tool should do the first pass for them.

---

## B. Horizon Analysis Workflow — instrument or decoration?

Findings from the code, not opinion:

| Capability | Implemented? |
|------------|:---:|
| Played over time | ❌ No — see below |
| Animates while scrubbing | ⚠️ Only on the Situation tab, and there's no scrub control there |
| Motion trail | ❌ No history buffer at all |
| Actual-vs-desired **history** | ❌ No — only the instantaneous ghost line |
| Last 10 seconds of movement | ❌ No |
| Usable **while** reading a plot | ❌ No — it lives in a separate tab; not co-visible with the Plotter |

Two hard facts:
1. **The Horizon holds zero history.** It reads `ATT.Roll/Pitch/DesRoll/DesPitch` at
   the cursor instant and paints. No trail, no last-N-seconds, no actual-vs-desired
   trend.
2. **The only "playback" in the app — the 3-D Replay timer — does not drive the
   shared cursor.** It pokes the 3-D vehicle and the Plotter crosshair directly and
   never calls `set_cursor_time`. So pressing play animates the 3-D tab **and nothing
   else** — the Horizon, RC, Timeline, and Dock stay frozen.

**Verdict: as shipped, the Artificial Horizon is decorative for real analysis.** It is
a pretty, correct, synchronized gauge that an engineer would glance at once and then
ignore, because (a) you can't see it next to the plot you're analysing, (b) it has no
time context, and (c) it doesn't move when you play the flight.

**Recommendations (specific):**
- Give it a **rolling history**: a 10-second attitude trail (actual = solid, desired =
  ghost) so a single glance shows tracking and oscillation, not a frozen pose.
- **Make playback drive the shared cursor.** Route `ReplayControls.time_changed →
  AppState.set_cursor_time`. Then play animates *every* surface, and the Horizon
  becomes a live instrument.
- **Co-locate it with the Plotter** (a dockable strip), or it will never be used
  during plot analysis — which is the only time an engineer wants it.
- Add a small **attitude-error mini-plot** (Roll−DesRoll over the last 10 s) under the
  ball; that is what actually answers "is it tracking?".

---

## C. Signal Plotter Workflow — manual hunting?

Implemented: a **checkbox tree grouped by message** (210 px), toolbar = Auto Fit /
Zoom / Reset / Clear / Export CSV / PNG. That is the entire signal-discovery story.

| Investigation | Supported path | Effort |
|---------------|----------------|--------|
| Roll oscillation | expand `ATT` → tick `Roll` (+ `DesRoll`) | manual, must know `ATT` |
| Pitch instability | same, `ATT.Pitch` | manual |
| Yaw divergence | `ATT.Yaw` vs `DesYaw` | manual |
| GPS anomalies | find `GPS[0]`, tick `Status`/`NSats`/`HDop` | manual, must know fields |
| EKF problems | find `XKF4`, tick `SV/SP/SH/SM` | **expert-only**, cryptic field names |
| Motor issues | find `RCOU`/`ESCX`, tick channels | manual |
| Vibration | find `VIBE`/`IMU`, tick axes | manual, must know which |

**There is no search box, no presets, no "investigate X" one-click views, and no
link from an event to the relevant signal.** Discoverability is zero — the engineer
must already know ArduPilot's message/field taxonomy. For EKF/vibration that is an
expert-only barrier.

**What still requires too much manual effort:** *everything*. The Plotter is a generic
checkbox plotter, unchanged by all the investigation work around it. It is the weakest
surface relative to its importance.

**Recommendations:** a **signal search box** (fuzzy over msg+field+description); a
row of **presets** ("Roll tracking", "Yaw", "GPS health", "EKF innovations", "Vibration",
"Motor balance", "Power") that add the right signal set in one click; and **event→plot
linking** (selecting an EKF event auto-loads the EKF innovations). Without these, the
Plotter is a barrier, not a tool.

---

## D. Evidence Report Quality — would a certification engineer accept it?

Reviewing the actual `sample_evidence.md/.pdf`:

| Cert question | Answered? |
|---------------|:---:|
| What happened? | ⚠️ State only — phase/mode/attitude/diagnostics at the instant |
| **Why** it happened? | ❌ No — there is no analysis, no causal narrative |
| Evidence supporting the conclusion? | ⚠️ Raw values + provenance, but **no plots, no trends, no chain** |
| Pilot actions | ✅ Matrix (pilot column) |
| Aircraft actions | ✅ Matrix (actual column) |
| Controller actions | ✅ Matrix (demand column) |

**Strength:** the per-value **provenance** (source field, sample time, interpolated,
bracket) is genuinely certification-grade — chain-of-custody for every number. That is
better than most tools.

**The fatal gap:** the report **exports data without explanation.** There is no
conclusion field, no narrative, no embedded signal plot, no time-history, no automatic
anomaly statement. A snapshot is a *point*, not a *story* — a cert engineer needs the
sequence ("at T−4 s the pilot commanded X; the controller demanded Y; the aircraft
diverged to Z; EKF SP exceeded 1.0 at T−2 s; impact at T0"). Today the only "why" is
whatever free-text the engineer types into Notes. **A certification engineer would
accept the data and provenance, but reject the report as an analysis** — it argues
nothing.

**Missing exactly:** (1) a findings/conclusion section; (2) embedded plots for the
captured window (e.g. ±10 s of attitude/innovations); (3) a multi-snapshot **timeline
of events** as the report spine; (4) auto-generated observations ("yaw divergence 45°",
"EKF position innovation CRITICAL").

---

## E. Accident Investigation Workflow — crash, answer in 5 minutes?

| Needed | Reachable? | How |
|--------|:---:|-----|
| Last valid aircraft state | ⚠️ | Scrub to end; but no auto "last-valid"/impact detection |
| Pilot input | ✅ | Matrix |
| Controller demand | ✅ | Matrix |
| Aircraft response | ✅ | Matrix |
| GPS quality | ✅ | Dock (fix/sats) |
| EKF condition | ✅ | Dock (EKF indicator) |
| Location | ✅ | Dock position / Map |
| Flight mode | ✅ | Dock |
| Timeline of events | ✅ | Events module + Timeline |

**Verdict: E is the strongest workflow — mostly achievable in 5 minutes by a trained
user**, and a single ★ snapshot captures all of it with provenance in one artifact.
This is where the shared cursor pays off.

**What slows it down / prevents it:** there is **no crash/impact detection and no
auto-jump to the last valid sample.** The investigator manually hunts for "where it
went wrong" — for a truncated log (battery pulled) the relevant moment is the end, but
nothing flags it. There is also no **"final state" auto-summary** and no replay of the
final seconds tied to the cursor (replay is disconnected — see B). So E works, but you
must know the tool and do the hunting; it is not yet "open log → here is the crash".

---

## F. What does TARAlytics feel like? (0–10)

| Identity | Score | Why |
|----------|:---:|-----|
| Log Viewer | **9** | Far exceeds a viewer; parses, verifies, navigates |
| Investigation Workstation | **7** | Genuine shared-cursor investigation; strong for point-in-time and accident work |
| Certification Tool | **4** | Verification + provenance + export are real; but no analysis/narrative |
| Pilot Debrief Tool | **3** | Debrief screen exists but answers almost none of the pilot's real questions |
| Engineering Analysis Tool | **3** | Plotter has no search/presets/derived analysis; no FFT, no metrics |

**"What would stop a real engineer using this every day?"**

> It only ever tells them the state **at one instant**. Daily flight analysis is about
> *trends and quality over the whole flight* — "is it oscillating, is it tracking, did
> it saturate, was the landing hard" — and TARAlytics computes **none** of that. The
> engineer would still drop into another tool (MAVExplorer / plot.ardupilot) to
> actually analyse the flight, and use TARAlytics only to pin a moment. A tool you
> leave to do the real work does not become a daily driver.

Add to that: the Plotter's lack of search/presets, the Horizon being decorative, and
playback not animating the investigation surfaces.

---

## Do the surfaces actually work together in a real investigation?

| Pair | Integrated? | Honest assessment |
|------|:---:|-------------------|
| Timeline ↔ Dock ↔ Events ↔ Map | ✅ Real | One cursor, instant fan-out. This is genuinely good. |
| Horizon / RC ↔ cursor | ⚠️ By signal only | They *follow* the cursor but are **siloed in their own tab**, have **no history**, and **don't animate during playback**. Connected, not usable-together. |
| Plotter ↔ everything | ⚠️ Crosshair only | Scrubbing the plot moves the cursor and vice-versa, but there is **no event→plot, no plot→snapshot, no preset**. Linked by a line, not by a workflow. |
| Evidence ↔ the rest | ⚠️ Point capture | Captures the cursor state superbly, but pulls in **no plot/time-history** — the report can't show the surrounding seconds it claims to investigate. |
| Replay ↔ everything | ❌ Broken | Playback drives only the 3-D tab + plotter crosshair; the shared cursor, Horizon, RC, Timeline, Dock stay frozen. |

**Conclusion:** the *state* surfaces (Timeline/Dock/Events/Map) are a real, integrated
investigation cluster. The *motion/time* surfaces (Horizon, RC, Plotter, Replay) are
each wired to the cursor but **do not yet form a workflow** — you cannot watch motion
while reading a plot, you cannot play the flight and see everything move, and you
cannot get from an event to its signal trace. The investigation is whole for "freeze a
moment" and broken for "watch it unfold".

---

## 1. Top 20 Workflow Problems
1. Everything is **instantaneous** — no whole-flight quality metrics.
2. No **oscillation/ringing detection** (the #1 tuning question).
3. No **controller-saturation / I-term-windup** indication.
4. No **control-activity / overcontrol / stick-reversal** metric.
5. No **tracking-error over time** (only Δ at the cursor).
6. No **landing/touchdown-rate** quality metric.
7. **Replay playback does not drive the shared cursor** — nothing animates.
8. **Horizon has no history/trail** — frozen pose only.
9. Horizon/RC are **siloed in their own tab**, not co-visible with the Plotter.
10. **Plotter has no signal search.**
11. **Plotter has no presets / one-click investigations.**
12. **No event→signal linking** (select an EKF event, no auto-plot).
13. **Evidence report has no narrative / conclusion / "why".**
14. **Evidence report embeds no plots or time-history.**
15. No **crash/impact detection** or auto-jump to last-valid state.
16. No **automatic anomaly summary** ("yaw diverged 45° at T").
17. Pilot Debrief answers almost none of the pilot's 8 real questions.
18. EKF/vibration signals require **expert knowledge of ArduPilot field names**.
19. **No mode-awareness in the matrix** (manual vs auto changes its meaning).
20. **Snapshots are session-only** — easy to lose work before export.

## 2. Top 20 Workflow Strengths
1. **Shared cursor** genuinely synchronizes Timeline/Dock/Events/Map.
2. **Pilot/Demand/Actual + Δ matrix** — the single best idea in the app.
3. **Per-value provenance** — certification-grade chain of custody.
4. **Investigation Snapshot** captures a complete moment in one click.
5. **Three export formats** (JSON/Markdown/PDF), dependency-free PDF.
6. **Timeline** flight-window/phase/mode lanes read the flight at a glance.
7. **Multi-flight & truncated logs** handled (3 flight windows, structure-error).
8. **Verification state** surfaced everywhere (operationally important for trust).
9. **EKF / position-divergence indicators** — real diagnostic value.
10. **Vertical-speed indicator** with source hierarchy.
11. **Events**: search + severity/type filters + notes + status.
12. **Event → one-click jump** updates the whole state view.
13. **Desired-attitude ghost** concept (just needs history).
14. **Map** event markers + jumped-event highlight (flight-path context).
15. **Accident-investigation** state is genuinely fast to assemble.
16. **Never fabricates** — "—" for missing data, honest throughout.
17. **Altitude AGL source hierarchy** (POS→BARO→…) is correct and shown.
18. **Cursor-debug introspection** (named subscribers) — strong foundation.
19. **Flight identity bar** + verification badge (trust at a glance).
20. **Performance** never gets in the way (sub-ms moves) — invisible, as it should be.

## 3. Features that should be **redesigned**
- **Artificial Horizon** → add a 10 s history trail + attitude-error mini-plot, and make it co-visible with the Plotter.
- **Signal Plotter** → add search + presets + event-linking; it is currently pre-investigation-era.
- **Evidence report** → from data dump to **narrative report** (conclusion + embedded plots + event timeline spine).
- **Replay** → re-wire to the shared cursor so "play" animates everything; demote the standalone 3-D tab.
- **Pilot Debrief** → rebuild around the 8 pilot questions with computed metrics, not a generic health grid.

## 4. Features that should be **removed (or demoted)**
- The **standalone 3-D Replay tab** as currently wired (OpenGL-only, off the shared cursor) — fold its playback into the shared cursor and keep 3-D as an optional view, not a primary nav item.
- **RC Visualization as a full tab panel** — it's a glance widget; move it into the dock/Situation strip rather than owning prime nav real estate.
- Redundant per-surface toolbars (Plotter zoom/fit vs global) that fragment the interaction model.

## 5. Features that should be **added**
- **Flight-quality scorecard** (oscillation, tracking RMS, control activity, saturation, vibration, landing rate) on the Debrief.
- **Oscillation / FFT** analysis and **saturation** detection.
- **Signal search + presets + event→plot linking** in the Plotter.
- **Time-history everywhere**: trails on Horizon/RC, error-vs-time mini-plots.
- **Crash/impact + last-valid-state** auto-detection and jump.
- **Narrative evidence report** with embedded plots and an auto anomaly summary.
- **Playback that drives the shared cursor.**
- **Snapshot persistence** (auto-save / project file).

## 6. The single most important missing capability

> **Automated, whole-flight quality analytics.** TARAlytics computes *state*, never
> *quality*. The one capability that would change everything is a layer that ingests
> the whole flight and produces the answers an operator actually asks — oscillation,
> tracking error, saturation, control activity, vibration, landing rate, and an
> anomaly summary — surfaced on the Debrief and embedded in the evidence report. With
> it, TARAlytics becomes a daily flight-analysis tool. Without it, it remains a superb
> way to *freeze and document a moment* that someone else's tool first told them to
> look at.
