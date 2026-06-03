# Sprint-1.2 — Parser Correctness Release: Final Report
## Branch: `sprint-1.2-data-accuracy` · commit `1132391`

A parser **correctness** release (not a metric cleanup). Two independent parser
defects fixed, validated against the authoritative `AP_Logger/` source and across
three real logs.

---

## 1. Parser Correctness Report

### Defect 1 — Signature chunk leakage (PARSING)
Secure-log `CHUNK` records (`1HCH`, 44 B, inserted every 4096 B) were parsed as
telemetry, injecting the float32 of `1HCH` = **199968.766** into data fields.
**Fix:** `parse()` now reads only the data ranges referenced by the hash-chain,
via a shared helper `signature_verifier.extract_signed_data()` (no duplicated
magic constants). Header/trailer/chunk/END bytes never enter the parse.

### Defect 2 — FMT stride off-by-one (PARSING)
`log_Format` is `sizeof = 89 B` (confirmed in `AP_Logger/LogStructure.h` and by
the FMT record's self-reported `length=89`). The parser strided **90**, skipping
~half the FMT catalog — silently dropping real types like `ATT` on **every** log.
**Fix:** `FMT_RECORD_SIZE = 89` in both passes.

### Metric corrections (evidence-based, no parser workarounds)
- `duration()` = **armed window** (first→last `ARM`); `log_span()` keeps full span.
- `max_altitude()` source hierarchy (§5) prefers AGL; `GPS.Alt` excluded; suspect
  values **flagged, never clamped**.

---

## 2. Before / After Message Inventory (log 00000002)

| | Before | After |
|---|---|---|
| Total message types | 59 | **92** |
| `ATT` (attitude) | ❌ absent | ✅ present |
| `POS` | ✅ | ✅ |
| `RATE` | ✅ | ✅ |
| `XKF1/XKF3` (EKF) | partial | ✅ full lanes |
| `XKF4` (EKF innov.) | ❌ | ✅ (→ EKF health now works) |
| `VER` (firmware) | ❌ | ✅ |
| `GPS[0]` | garbled | ✅ RTK_FIXED, 10 sats |
| `MOTB` columns | `…ThrAvM1HCH`(garbled, 5) | `…ThrAvMx,ThrOut,FailFlags`(8) |
| `1HCH` sentinel cells | 40 | **0** |

Recovered core types previously dropped by the stride bug: `ATT, VER, AHR2,
ANG, XKF4/XKFS/XKT/XKV1/XKY0`, and the complete `MOTB`.

---

## 3. Before / After Metric Comparison (log 00000002)

| Metric | Before | After | Reality |
|--------|--------|-------|---------|
| Duration | `0:58` | **`0:43`** | armed window (log span `0:58` kept as secondary) |
| Max altitude | `199968.8 m` | **`10.0 m`** | AGL; cross-checked BARO 9.99 / SIM2 10.07 |
| Max speed | `199968.8 m/s` | **`2.5 m/s`** | SIM2 velocity |
| Distance | `44133.13 km` | **`0 m`** | stationary hover (traj ±0.04 m) |
| Event count | 29 | 29 | unchanged |
| Verification | VERIFIED/1098 | VERIFIED/1098 | **unchanged** (operates on raw bytes) |

Acceptance criteria — all met: 0 surviving `1HCH` sentinels; ATT/POS/RATE/XKF
restored; signed + truncated logs parse; verification unchanged; full suite green.

---

## 4. Blast Radius Review (every subsystem checked)

| Subsystem | Result | Note |
|-----------|--------|------|
| Signature verification | **unchanged** | VERIFIED/1098 on log 02; reads raw bytes, parser-independent |
| Event extraction | unchanged | 29 events |
| Health calculations | **improved** | EKF `NO DATA`→`OK` (XKF4 now parses); GPS `SITL`→`RTK_FIXED` |
| Replay | **improved** | trajectory clean; `ATT` attitude now available |
| Plotter | works | 92 types load; PID grouped correctly |
| Exports (CSV) | works | method intact |
| Debrief | corrected | see screenshot §6 |

Behavior changes are all corrections (more real data, plausible values). No
subsystem regressed. Full test suite: **154 passed**.

---

## 5. Altitude Source Hierarchy (evidence)

Engineers mean **height above takeoff (AGL)**, not AMSL. Evidence on log 02:

| Source | Value | Interpretation |
|--------|-------|----------------|
| `POS.RelHomeAlt` | 0–**10.01 m** | AGL — **preferred** |
| `BARO[0].Alt` | 0–9.99 m | relative (agrees) |
| `SIM2.-PD` | 0–10.07 m | SITL up (agrees) |
| `POS.Alt` | 584–594 m | AMSL (absolute) |
| `GPS[0].Alt` | 8.3e-41 | garbage in SITL — **excluded** |

Hierarchy: `RelHomeAlt → BARO → SIM2 → POS.Alt(AMSL)`. Three independent sources
agree on ~10 m AGL, justifying `RelHomeAlt` as authoritative. Values >60 km are
flagged `⚠ (suspect)`, never silently clamped.

---

## 6. Screenshots

`docs/screenshots/sprint1_2/debrief_corrected.png` — corrected Debrief:
FLIGHT TIME `0:43`, MAX ALTITUDE `10.0 m`, EVENTS `29`, VERIFIED/1098 chunks,
all four health systems NOMINAL (Navigation: EKF OK, GPS RTK_FIXED, 10 sats).
(3D Replay/Verification screenshots require a display; Replay uses QOpenGLWidget
which does not render under the headless offscreen platform.)

---

## 7. Multi-log Validation

| Log | Size | Type | Result |
|-----|------|------|--------|
| 00000002 | 4.3 MB | complete signed | 92 types, 0 sentinels, VERIFIED/1098, all metrics plausible |
| 00000011 | 193 MB | **truncated** (battery cut pre-END) | 102 types, 0 sentinels, duration 6:14 / alt 4.8 m plausible; verification correctly `STRUCTURE_ERROR` (no crash, no false verify); parse 54 s |
| 00000012 | 440 MB | large complete | chunk-exclusion 0 sentinels (50 s extract) |

---

## 8. Updated Roadmap — additional parser issue discovered

Cross-referencing `FORMAT_MAP` against `AP_Logger/README.md` found 3 format-type
gaps (documented in `ap_logger_format_study.md` §5): `E` (uint32×100) and `g`
(float16) **missing**; `e` mapped to float vs README's int32×100. They don't
affect logs 02/11/12 but will break logs using those chars.

**New work item — Sprint-1.3 (Parser Format Completeness):** add `E`/`g`, resolve
`e` semantics with evidence. Deferred to keep this correctness release focused.

### Performance note
The chunk-exclusion scan is pure-Python O(n): ~22 s (193 MB) / ~50 s (440 MB) for
extraction; full parse of 193 MB ≈ 54 s. Acceptable for one-time loads; a
vectorized scan is a candidate optimization if large-log UX needs it.

---

## 9. Status vs Original Goals
- ✅ Debrief values physically plausible (screenshot §6).
- ✅ No impossible values; suspect values flagged.
- ✅ Signed, truncated, and unsigned logs handled.
- ✅ Verification unchanged.
- ✅ Full suite passes (154).
- Data layer is now trustworthy → P1 (Timeline, Unified Events) unblocked.
