# TARAlytics — Operational Roadmap (P0–P3)
## Goal: turn the demo into a real engineering workstation. Aesthetics frozen.

This is the planning package requested before any code is written:
(1) roadmap, (2) architecture impact, (3) screens affected, (4) mockups,
(5) risk. Root-cause evidence for P0 is in
[sprint1_2_findings.md](sprint1_2_findings.md).

---

## 1. Updated Roadmap

| Pri | Work item | Outcome | Depends on |
|-----|-----------|---------|-----------|
| **P0** | Data Accuracy (Sprint-1.2) | Debrief shows real values; impossible values gone; suspect data flagged | — |
| **P1a** | Mission Timeline module | Primary investigation surface; click-to-jump | P0 (trustworthy time/alt) |
| **P1b** | Unified Event Investigation module | One authoritative event view; replaces 4 fragments | P1a (jump-to-timeline) |
| **P2a** | Signal Plotter workflow | Search, presets, favorites, dual-axis, values-at-T, health preload | P0 |
| **P2b** | Unified Health model | One health system w/ evidence + drill-down; fix EKF | P2a (preload), P0 |
| **P3** | Evidence Export | Certificate + PDF + JSON + hash manifest + chain of custody | P0 (trustworthy data) |

### Sequencing rationale
- **P0 first, non-negotiable.** Every downstream screen renders the same data; fixing
  it once at the parser fixes Timeline, Plotter, Health, and Export simultaneously.
- **P1a before P1b** — events jump *to* the timeline, so the timeline must exist.
- **P2a before P2b** — health drill-down "preloads signals" needs the plotter preset
  mechanism to exist first.
- **P3 last** — exporting evidence built on untrustworthy data would be worse than
  no export.

### Milestones
- **M1 (P0):** parser chunk-exclusion + duration metric + suspect-flagging. Debrief trustworthy.
- **M2 (P1):** Timeline + Unified Events. Crash investigation < 2 min achievable.
- **M3 (P2):** Plotter productivity + Health unification. Vibration investigation w/o manual hunting.
- **M4 (P3):** Evidence export. DGCA workflow self-contained.

---

## 2. Architecture Impact Assessment

The Sprint-1 architecture (AppState hub + module pages + core extractors) absorbs
all of P0–P3 without structural change. Specifics:

### Core layer (`core/`)
| Component | Impact |
|-----------|--------|
| `log_parser.py` | **P0 change.** Add chunk-region exclusion in the data pass (reuse `signature_verifier` chunk scan). Isolated to `parse()` / `_pass2_parse_all`. Highest-blast-radius change; covered by parity tests. |
| `flight_metrics.py` | **P0 change.** `duration()` → armed-window definition; add `log_span()`. Add robust/flagged variants returning `(value, str, suspect: bool)`. |
| `signature_verifier.py` | **No change** (P0 reuses its chunk scan read-only). P3 reads its outputs for the certificate. |
| `event_extractor.py` | **No change** — already the single event source; P1b consumes it directly. |
| `health_analyzer.py` | **P2b change.** Fix EKF (use XKF1/3/4/5 + innovations, not only XKF4.FS). Add `power()`, `propulsion()`, `structural()`, `navigation()` returning a uniform `HealthResult{state, metrics, evidence_signals[]}`. |
| `core/timeline_model.py` (new) | **P1a.** Pure phase/segment detection from MODE/ARM/ALT — no Qt. |
| `core/evidence/` (new) | **P3.** PDF/JSON/manifest builders (pure, testable). |

### State layer (`ui/app_state.py`)
- Already exposes `cursor_time_changed`, `event_jumped`, `module_requested`. **P1
  reuses these** for Timeline↔Plotter↔Replay sync. Add `signals_preload_requested(list)`
  for P2 health-card preload. Minimal additive change; no breaking edits.

### UI layer (`ui/`)
| Module | Impact |
|--------|--------|
| `modules/mod_timeline.py` (new) | **P1a.** New nav item. |
| `modules/mod_events.py` (new) | **P1b.** New nav item; deletes 3 fragment displays. |
| `modules/mod_debrief.py` | **P0** value display + suspect flags; **P2b** health cards bind to unified model. |
| `tab_plotter.py` | **P2a.** Add search/preset/dual-axis/values-at-T; subscribe to `signals_preload_requested`. |
| `tab_verification.py` | **P1b**: remove EventTable + EventTimeline (moved to Events). **P2b**: remove duplicate health cards. **P3**: add "Export Evidence". Net **shrinks**. |
| `widgets/` | New: `timeline_strip.py`, `event_table_unified.py`, `values_at_time.py`, `signal_search.py`. |
| Navigation Rail | Grows from 5 → up to 7 items (add TIMELINE, EVENTS). MAP may fold under Replay/Timeline. |

### Data-flow after P0–P3 (unchanged shape)
```
parse → AppState.set_parsed_data → data_changed →
  {Debrief, Timeline, Events, Plotter, Replay, Health} all re-render
cursor_time_changed / event_jumped ←→ Timeline ↔ Plotter ↔ Replay (already wired)
signals_preload_requested → Plotter (new, P2)
```

**Conclusion:** all changes are additive modules + targeted edits to 3 existing
files. No rewrite of AppState, parser scan structure, or verifier. Low architectural risk.

---

## 3. Screens Affected

| Screen | P0 | P1 | P2 | P3 |
|--------|----|----|----|----|
| Debrief | values fixed + flags | — | health cards → unified model | "needs attention" rollup |
| Plotter | correct data | jump targets | search/preset/dual-axis/values-at-T | — |
| Replay | correct trajectory | timeline sync | — | — |
| Verification | — | loses EventTable/Timeline | loses dup health | gains Export |
| **Timeline (new)** | — | built | sync targets | — |
| **Events (new)** | — | built | — | flag-for-evidence |
| Flight Identity Bar | duration→armed | — | — | — |

---

## 4. Mockups (ASCII — structure only, not visual design)

### 4.1 Mission Timeline (P1a) — primary investigation surface
```
┌ TIMELINE ─ SN-01 · FLIGHT #002 · armed 0:43 ─────────────────────────┐
│ ALTITUDE (m, clean)                                                   │
│ 10┤            ╭────────────────╮                                     │
│  5┤         ╭──╯                ╰──╮                                  │
│  0┤─────────╯                      ╰───────                          │
│   └┬─────────┬─────────┬─────────┬─────────┬────────────┬─           │
│  PHASE  [PRE-ARM][ TAKEOFF ][   HOVER/MISSION   ][ LAND ][POST]       │
│  MODE   [STABILIZE][   GUIDED            ][ LAND ][STABILIZE]         │
│  EVENTS  ▲arm   ▲ekf ▲ekf            ▲hit-gnd  ▲disarm                │
│         126.99 135.5                  168.5    170.57                 │
│         [◀ prev event]  [playhead ▮]  [next event ▶]                  │
└───────────────────────────────────────────────────────────────────────┘
 click altitude / event / band → moves Plotter crosshair + Replay playhead
```

### 4.2 Unified Event Investigation (P1b)
```
┌ EVENTS ─ 29 total ───────────────────────────────────────────────────┐
│ Severity [✓CRIT ✓ERR ✓WARN ✓INFO]  Type [MSG EV ERR ARM MODE]        │
│ Search [ groun________ ]                              12 shown / 29    │
│ ─────────────────────────────────────────────────────────────────── │
│  TIME      SEV   TYPE  MESSAGE                          ACTIONS        │
│  126.993   INFO  ARM   Armed                            [plot][3D][⏱]  │
│  168.483   WARN  MSG   SIM Hit ground at 0.4999 m/s     [plot][3D][⏱]  │
│  170.569   INFO  ARM   Disarmed (method=...)            [plot][3D][⏱]  │
│ ─────────────────────────────────────────────────────────────────── │
│  SELECTED: 168.483 "Hit ground"   Note:[__________________] [save]    │
│  Correlated ±2s: RATE.ADes↓, BARO.Alt→0, ESCX out↓     [flag DGCA]    │
└───────────────────────────────────────────────────────────────────────┘
 [plot]=jump Plotter+crosshair  [3D]=jump Replay  [⏱]=jump Timeline
```

### 4.3 Plotter productivity (P2a)
```
┌ SIGNALS ──────────────────────────────────────────────────────────────┐
│ 🔎[ accz________ ]  ★Favorites  �seRecent  ▦Presets▾  ⧉Dual-axis        │
│ search hits: IMU[0].AccZ  IMU[1].AccZ  SIM2(...)                       │
│ ┌── tree ──┐ ┌── plot ───────────────────────────┐ ┌ VALUES @ 152.3s ┐│
│ │ IMU[0]   │ │   (curves)            ┊cursor      │ │ AccZ   -9.81    ││
│ │  ✓AccZ   │ │                       ┊            │ │ Volt   12.6     ││
│ │ BAT      │ │                       ┊            │ │ Curr   18.2     ││
│ └──────────┘ └───────────────────────────────────┘ └─────────────────┘│
│ Presets: [Standard Review][EKF Lanes][Motor Balance][Power]  [+ save]  │
└───────────────────────────────────────────────────────────────────────┘
 Health card "POWER CAUTION" → preloads BAT.Volt,BAT.Curr,BAT.RemPct,CURR.Cons
```

### 4.4 Unified Health (P2b)
```
┌ HEALTH (one model; every CAUTION has evidence) ───────────────────────┐
│ NAVIGATION ◉NOMINAL   POWER ◉NOMINAL   PROPULSION ⚠CAUTION             │
│  EKF lanes 2 ok        Vmin 12.6V       motor spread 14% > 10%         │
│  [view evidence →]     [view evidence →] [view evidence → preloads ESCX]│
│ GPS ◉SITL             STRUCTURAL ◉NOMINAL                              │
└───────────────────────────────────────────────────────────────────────┘
```

### 4.5 Evidence Export (P3)
```
┌ EXPORT EVIDENCE ─ SN-01 · #002 ──────────────────────────────────────┐
│ [✓] Verification Certificate   state VERIFIED · Ed25519-Blake2b        │
│ [✓] Hash Manifest              SHA-256 signed+full · key 66 33 06 04   │
│ [✓] Chain of Custody Summary   1098 chunks · device 0x3366 · log #002 │
│ [✓] Flagged anomalies (2)      from Events module                     │
│ Format: (•)PDF  ( )JSON  ( )Both        [ GENERATE PACKAGE ]          │
│ Output: TUA-FDR-2026-06-04-SN01-002.pdf  + .json + .sha256            │
└───────────────────────────────────────────────────────────────────────┘
```

---

## 5. Risk Assessment

| Risk | P | Likelihood | Impact | Mitigation |
|------|---|-----------|--------|------------|
| Parser chunk-exclusion drops *valid* records | P0 | Med | High | Reuse verifier's exact chunk offsets; assert row counts for non-leaked types stay within ±0; gate on full parity suite |
| Parser fix interacts with `e62a2e4` `3e11`/`FIELD_BOUNDS`/`1e9` filters | P0 | Med | Med | Keep filters; chunk-exclusion is upstream of them; regression test asserts both present |
| Duration redefinition breaks a consumer expecting log-span | P0 | Low | Low | Provide both `duration()`=armed and `log_span()`; grep consumers first |
| "Suspect flag" hides a real anomaly as "garbage" | P0 | Low | High | Flag (not drop) on display; keep raw in plotter; threshold from physics, documented |
| Nav rail grows to 7 → crowding | P1 | Low | Low | Fold MAP under Replay/Timeline; cap at 6 visible |
| Event fragment removal breaks Verification tab layout/tests | P1b | Med | Med | Move, don't delete logic; update `test_ui_main`/verification tests in same commit |
| Plotter dual-axis/search adds perf cost on 23k-row SIM2 | P2a | Med | Med | Decimate for display; lazy search index; benchmark on 00000002 |
| Health unification changes Debrief states users saw in Sprint-1 | P2b | Low | Med | Document mapping; EKF "NO DATA"→"NOMINAL" is a *fix*, announce it |
| PDF generation adds a heavy dependency / Windows build bloat | P3 | Med | Med | Prefer pure-Python (reportlab) or HTML→print; measure PyInstaller size delta |
| Evidence built before P0 lands | P3 | Low | High | Hard-sequence: P3 blocked until P0 validation green |
| Scope creep back into aesthetics | all | Med | Med | Freeze visual work per directive; reviews check "does this serve a workflow test" |

### Workflow success gates (acceptance per milestone)
- **M1:** Post-flight review < 30 s — Debrief gives verdict + real numbers + auth + attention.
- **M2:** Crash investigation < 2 min — Timeline→Events→Plotter/Replay, click-to-jump, no screen hunting.
- **M3:** Vibration investigation — Health "Structural/Propulsion" → preloads VIBE/ESCX; zero manual tree hunting.
- **M4:** Evidence generation — certificate+PDF+JSON+manifest produced in-tool, no external software.

---

## 6. What happens next (on approval)
1. P0 implementation on a `sprint-1.2-data-accuracy` branch: parser chunk-exclusion +
   duration metric + suspect-flagging + ground-truth test. Validate against §
   findings (0 sentinels, alt≈10/586 m, dur≈0:43).
2. Report: what was fixed / remains / test results / before-after Debrief values.
3. Proceed to P1 only after M1 gate passes.

No parser or metric code is changed until this plan is approved.
