# P2.1 — Release Candidate Review
### TARAlytics Mission Investigation Workstation — pre-merge readiness review

Scope: snapshot provenance, user-workflow validation, Replay status, and a formal
release readiness assessment + merge recommendation + known limitations + risk
register. Test suite: **311 passing**. Validated on real logs 02 (4 MB) / 11 (193 MB,
truncated/multi-flight) / 12 (440 MB).

---

## 1. Snapshot Provenance (implemented)

Every snapshot value that originates from `SampleService` now carries full
provenance, captured at build time via `SampleService.sample_at` (continuous) /
`sample_time` (discrete) and stored on the snapshot under `provenance`:

| Captured | Field |
|----------|-------|
| source message | `msg` |
| source field | `col` |
| sample timestamp | `sample_timestamp` (the held sample when not interpolated) |
| interpolated state | `interpolated` (bool) |
| bracket samples | `bracket` = `[t_lower, t_upper]` when interpolated |

A snapshot records **25 provenance-tracked values**: the full control triple
(pilot RCIN channels, controller demand `ATT.Des*`/`CTUN.ThO`, response `ATT.*`,
servo `RCOU`), altitude, vertical speed, ground speed, GPS status/sats, position,
and the EKF / position-divergence source fields (`XKF4`/`XKF3`). Example (cursor at
an off-sample time → interpolation):

```
demand_roll   -> ATT.DesRoll  interp=True  bracket=[150.249, 150.350]
gps_status    -> GPS[0].Status interp=False sample_timestamp=150.189
```

Provenance is carried verbatim in the **JSON** export and as a per-snapshot
collapsible **Data provenance** table in the **Markdown/PDF** report — making every
exported number traceable to its source sample (certification-grade evidence).

---

## 2. User Workflow Validation (measured)

Driven through the real `MainWindow` by `scripts/p2_1_workflow_validation.py`
(actions = discrete user clicks/keystrokes; answer-reachability asserted):

| Workflow | Path | **Clicks to answer** | Time-to-answer* | Answer reachable |
|----------|------|:--------------------:|:---------------:|:----------------:|
| **Post-flight review** ("was this flight okay?") | Parse → Debrief landing (duration, max alt, events, 4-quadrant health, verification) | **1** | ~5–10 s (glance) | ✅ |
| **Anomaly investigation** | Events → select worst-severity event → ★ capture | **3** | ~15–30 s | ✅ |
| **Pilot vs controller** | Situation → scrub/step to moment (Horizon ghost + RC sticks + matrix Δ on one screen) | **2** | ~10–20 s | ✅ |

\* time-to-answer excludes initial parse (which is log-size bound — see §5); it is the
read/decide time once loaded.

**Why these are fast:** every workflow resolves on the shared cursor — selecting an
event moves one cursor and updates Timeline, Context, Matrix, Horizon, RC and Map
together, so the engineer never assembles the picture by hand or opens a plot. The
matrix Δ column answers "did the aircraft follow the controller?" at a glance; the
EKF / Pos-Div indicators answer "was the estimator healthy?" without a plot.

**Evidence quality:** a single ★ capture records a complete, provenance-bearing
snapshot — event, flight window, time, position, altitude, phase, mode,
pilot/demand/response + Δ, vertical speed, EKF, position divergence, verification
state, notes, status — plus 25 traceable sampled values. Exportable as JSON
(machine), Markdown (human), PDF (shareable). This is sufficient for a written
finding or a certification artifact.

---

## 3. Replay Status (documented; not a blocker)

The 3-D Replay surface (`ui/tab_3d_view.py`, `pyqtgraph.opengl`) requires an OpenGL
≥ 2.1 context. Under the **offscreen** Qt platform used by the test/CI/screenshot
harness it raises `RuntimeError: pyqtgraph.opengl: Requires >= OpenGL 2.1` during
`initializeGL`. Consequences and disposition:

- **On a normal desktop GPU session Replay renders and follows the shared cursor**
  (it is a registered cursor subscriber). The limitation is specific to headless /
  offscreen rendering.
- Replay is **not** yet wired into snapshot capture (a snapshot does not embed a
  rendered replay frame).
- **Disposition:** treat Replay-in-evidence as a **future enhancement, not a release
  blocker.** It does not affect any of the three validated workflows, the snapshot
  contents, or any export format. CI/headless runs must continue to avoid
  constructing the GL widget (already the case in tests).

---

## 4. Release Readiness Assessment

| Dimension | Status | Notes |
|-----------|:------:|-------|
| Functionality | ✅ | Full select → investigate → capture → export loop; 9 surfaces on one shared cursor |
| Correctness (parser/metrics) | ✅ | Validated on 02/11/12 incl. truncated multi-flight; signed-chunk + FMT-stride fixes in place |
| Tests | ✅ | 311 passing; pure-core + Qt surfaces + full-workflow integration |
| Performance | ✅ | Cursor move sub-ms (Timeline ≤0.85 ms, Dock ~0.49 ms); flat in row count to 13.2 M rows |
| Provenance / evidence | ✅ | 25 traceable values/snapshot; JSON/MD/PDF |
| Headless rendering (Replay) | ⚠️ | Documented limitation (§3); not a blocker |
| Verify-lane coverage extent | ⚠️ | State-driven approximation; precise byte↔time mapping pending |
| Packaging | ➖ | Windows installer workflow exists; RC build not yet produced |

**Verdict: GO for Release Candidate.** No release blockers. Two ⚠️ items are
documented, bounded, and non-blocking.

---

## 5. Known Limitations

1. **Replay not capturable headlessly / not embedded in snapshots** (§3) — future
   enhancement.
2. **Verify-lane coverage extent is approximate** — driven by verification *state*,
   not a byte↔time map; the verdict (VERIFIED / STRUCTURE_ERROR) is exact, the
   shaded *extent* is indicative.
3. **Large-log parse cost** — 440 MB / 13.2 M rows parses in ~220 s and is
   memory-heavy; this is a one-time load cost (interaction stays sub-ms after).
4. **Snapshots are in-session only** — held in memory, cleared on log reload;
   persistence is via explicit export (by design).
5. **Throttle demand depends on `CTUN.ThO`** and EKF/Pos-Div on `XKF3/XKF4`; absent
   messages degrade to `—` / `OK` (never fabricated).
6. **Deferred parser formats** — `E`, `g`, `e` format types (Sprint-1.3).
7. **Single-developer verification**; not yet exercised by an independent flight-test
   engineer on hardware logs end-to-end.

---

## 6. Risk Register

| # | Risk | Likelihood | Impact | Mitigation / Status |
|---|------|:----------:|:------:|---------------------|
| R1 | Replay unavailable in headless/CI; absent from evidence | High (headless only) | Low | Documented §3; desktop GL works; not in any validated workflow |
| R2 | Verify-lane extent misread as exact coverage | Med | Low | Lane labelled by state; verdict exact; byte↔time map planned |
| R3 | Large-log parse time/RAM on low-spec machines | Med | Med | One-time cost; consider streaming/index later; document min RAM |
| R4 | EKF / Pos-Div thresholds heuristic (0.5/1.0; 0.5/2.0 m) | Med | Med | Conservative, ArduPilot-aligned; value + source shown for expert override |
| R5 | Snapshot loss on accidental reload (in-memory) | Low | Med | Export early; reload clears intentionally; could add "unsaved snapshots" prompt |
| R6 | Pilot provenance records raw PWM (RCIN.Cn), not normalized intent | Low | Low | Documented; semantic value stored in snapshot, raw sample in provenance |
| R7 | PDF rendering via QTextDocument (table fidelity) | Low | Low | Content complete; JSON is the authoritative machine record |
| R8 | Branch `sprint-1.2-data-accuracy` diverged from master; merge conflicts | Low | Med | Single feature line; recommend merge commit + RC soak (§7) |

No High-likelihood **and** High/Med-impact risks remain open.

---

## 7. Merge Recommendation

**Recommend: promote to Release Candidate `v1.1.0-rc1` on the feature branch, soak,
then merge `sprint-1.2-data-accuracy → master` and tag `v1.1.0`.**

- This is a **feature release** (Mission Investigation Workstation + Evidence) on the
  existing `1.0.x` line — backward compatible (same logs, same verification), so a
  **minor** bump (`1.1.0`) is appropriate; `2.0.0` is defensible given the scope and
  is a product call.
- Suggested sequence:
  1. Tag the current head `v1.1.0-rc1` (prerelease; the Windows build workflow already
     treats a `-` version as prerelease). ← *prepared now*
  2. RC soak: an independent flight-test engineer runs the three workflows on hardware
     logs end-to-end and exercises an export → review the PDF/JSON evidence.
  3. On sign-off, merge to `master` (merge commit to preserve the staged history),
     set `VERSION` to `1.1.0`, tag `v1.1.0`, run the installer workflow.
- Do **not** block the merge on Replay-in-evidence (R1) or verify-extent precision
  (R2); track both as post-1.1 enhancements.

---

## 8. Conclusion
Provenance is complete and traceable, the three target workflows are fast (1–3
clicks) and answer-reachable, Replay's limitation is understood and non-blocking, and
the suite is green at 311. **The build is ready to be cut as Release Candidate 1.**
