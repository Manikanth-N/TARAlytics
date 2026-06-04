# P3 — Flight Intelligence Layer
### Reorients TARAlytics from "what happened at 148 s?" to **"was this a good flight?"**

Directly answers the operational review's core finding (state-at-the-cursor strong,
whole-flight analysis absent). Built core-first; every UI surface now consumes the
analytics. Validated on real logs 02 / 11 / 12.

---

## P3.1 — Analytics engine ([core/flight_analytics.py](../core/flight_analytics.py))
Pure-core, computed over the armed window(s):
- **Tracking metrics** — attitude demand-vs-response RMS / max / %-in-tolerance per axis.
- **Control smoothness** — pilot stick activity + reversal rate per axis.
- **Yaw discipline** — heading-hold tracking + yaw restraint.
- **Landing quality** — touchdown vertical rate (first ground contact) + class.
- **Oscillation detection** — per-axis FFT (concentrated spectral peak, 0.4–20 Hz).
- **Saturation detection** — motors (vs `MOT_PWM_MIN/MAX`), controller output (`RATE.*Out`), throttle.
- **Automated findings** — oscillation / tracking / saturation / landing / yaw, plus the systems anomaly detector (EKF/GPS/VIBE/POWER/ERR), severity-sorted with evidence refs.
- **Pilot scorecard** (per-category 0-100 + grade) and **FlightQuality** verdict (GOOD / ACCEPTABLE / MARGINAL / POOR) with headline + drivers.

Real-log verdicts: **02 GOOD/96** (clean), **11 MARGINAL/60** (11 findings — tracking RMS 15°, saturation, yaw, vibration, ERR), **12 GOOD/90** (vibration + power). Robust to missing signals (None, never fabricated).

## P3.2 — Debrief rebuilt ([ui/modules/mod_debrief.py](../ui/modules/mod_debrief.py))
The landing screen now **leads with the verdict**: a "WAS THIS A GOOD FLIGHT?" banner (verdict + score + headline + drivers), the **Pilot Scorecard** (Overall + Attitude Tracking / Control Smoothness / Yaw Discipline / Landing, colour-graded), and the **Automated Findings** list. Clicking a finding jumps the cursor to it, plots its signals, and opens the Plotter. Flight profile + verification demoted to supporting context.

## P3.3a — Horizon history + Replay→cursor
- **Replay now drives the shared cursor** ([ui/tab_3d_view.py](../ui/tab_3d_view.py)): playback / scrub / step animate **every** surface (Horizon, RC, Timeline, Dock, Map, Plotter), not just the 3-D tab — fixing the review's "playback animates nothing else". Single update path, loop-free.
- **Artificial Horizon** ([ui/widgets/horizon.py](../ui/widgets/horizon.py)) gained a 10-second motion trail and an **actual-vs-desired history mini-plot** (Roll + Pitch lanes) read from the real `[t−10, t]` window — no longer a decorative frozen gauge; it shows tracking/oscillation over time and animates during playback.

## P3.3b — Plotter ([ui/tab_plotter.py](../ui/tab_plotter.py))
- **Signal search** (live substring filter over message.field).
- **Investigation presets** (one click): Attitude / Roll / Pitch / Yaw / EKF / GPS / Vibe / Motors / Power, resolving instances (EKF→`XKF4[0]`).
- **Event-to-signal linking**: a finding/anomaly category maps to its preset; clicking a Debrief finding plots the right signals. No more hunting by ArduPilot field name.

## P3.4 — Narrative evidence reports ([core/evidence_export.py](../core/evidence_export.py), [ui/evidence_plots.py](../ui/evidence_plots.py))
Reports now carry the analysis, not just data:
- **Conclusion** section — verdict, score, headline, and the scorecard table.
- **Findings** section — each finding with severity, time, detail, and **supporting-evidence references** (signals).
- **Embedded plots** — each finding's evidence signals rendered to PNG (QPainter, no new dependency) and embedded in Markdown (sidecar files) and PDF (Qt image resources).
- JSON gains `flight_assessment` (the full report). Exports work from the report alone (no snapshots required). Sample: `docs/screenshots/sprint_p3/sample_flight_report.md` / `.pdf`.

---

## Answering the review's questions
- **"Was this a good flight?"** is now the first thing the Debrief shows.
- **Overcontrol / oscillation / saturation / tracking / yaw / landing** are computed metrics and findings, not manual plot-hunts.
- **Horizon** is a live, history-bearing instrument that animates with playback.
- **Plotter** has search + presets + event-linking.
- **Evidence** is a narrative report (conclusion + findings + plots + evidence refs), not a data dump.

## Tests
`tests/test_flight_analytics.py` (+16, synthetic signals with known answers),
`tests/test_p3_surfaces.py` (+12, replay→cursor, horizon history, plotter
search/presets/linking), `tests/test_p2_evidence.py` (+6 narrative/plot). Full suite
moved from 311 → 345 across P3.

## Honest limitations
- Oscillation/saturation thresholds are heuristics (conservative, ArduPilot-aligned); the value + source are shown for expert override.
- Landing detection needs an altitude source reaching ground; truncated logs may report UNKNOWN.
- Embedded-plot signal selection uses the finding's evidence strings / category map (not arbitrary expressions).
- Scoring weights are a documented first cut; calibration against a labelled corpus is future work.
