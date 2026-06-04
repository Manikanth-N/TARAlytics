# Parser Correctness Release (Sprint-1.2)
## Reference document for future contributors

This is the authoritative summary of the TARAlytics parser correctness work.
Read this before changing `core/log_parser.py` or `core/signature_verifier.py`.

---

## Root Causes (two independent defects)

### 1. Signature chunk leakage
Secure (signed) logs interleave hash-chain **CHUNK records** — magic `0x48434831`
("HCH1"), 44 bytes each — into the data stream every 4096 bytes. The parser read
the whole signed region, so chunk bytes were decoded as telemetry. The float32 of
`1HCH` is **199968.765625**, which surfaced as impossible altitudes/speeds. It also
appeared as `121.27°` when the same bytes landed in an `L`-format (lat/lng) field.

### 2. FMT stride off-by-one
`struct log_Format` is `sizeof = 89` bytes (`AP_Logger/LogStructure.h`:
header 3 + type 1 + length 1 + name 4 + format 16 + labels 64). The parser strided
**90** (`3 + 87`), landing 1 byte past each back-to-back FMT record and **skipping
~half the FMT catalog**. Real message types (notably `ATT`, `VER`, `XKF4`) were
silently dropped on **every** log, signed or not.

Both are **parsing-layer** bugs. The source logs are valid; verification was never
affected (it operates on raw bytes).

---

## Fixes

| Area | Change | File |
|------|--------|------|
| Chunk exclusion | `parse()` reads only the data ranges referenced by the hash chain, via shared `extract_signed_data()` | `core/log_parser.py`, `core/signature_verifier.py` |
| FMT stride | `FMT_RECORD_SIZE = 89` (was 90), used in both passes | `core/log_parser.py` |
| Duration | `duration()` = armed window (ARM events); `log_span()` = full span | `core/flight_metrics.py` |
| Altitude | source hierarchy `RelHomeAlt→BARO→SIM2→POS.Alt`; `GPS.Alt` excluded; suspect values flagged | `core/flight_metrics.py` |

Design rules honored: reuse the verifier's chunk detection (no duplicate magics);
no silent clamping (suspect values are flagged); signed/unsigned/truncated all
supported.

---

## Before / After Metrics (reference log `00000002.BIN`)

| Metric | Before | After |
|--------|--------|-------|
| Message types | 59 | **92** |
| Duration | 0:58 | **0:43** (armed; span 0:58 secondary) |
| Max altitude | 199968.8 m | **10.0 m** (AGL) |
| Max speed | 199968.8 m/s | **2.5 m/s** |
| Distance | 44133 km | **0 m** |
| `1HCH` sentinels | 40 | **0** |
| `ATT` / `VER` / `XKF4` | absent | **restored** |
| Verification | VERIFIED / 1098 | VERIFIED / 1098 (unchanged) |

---

## Validation Logs

| Log | Size | Class | Outcome |
|-----|------|-------|---------|
| `00000002` | 4.3 MB | complete signed | 92 types, 0 sentinels, VERIFIED/1098, metrics plausible |
| `00000011` | 193 MB | **truncated** (battery cut before END) | 102 types, 0 sentinels, duration 6:14 plausible; verification → `STRUCTURE_ERROR` (no crash / no false verify) |
| `00000012` | 440 MB | large complete | 0 sentinels |

Full regression suite: **154 passed**. Lock-in tests live in
`tests/test_parser_quality.py`.

---

## Blast-Radius Assessment

| Subsystem | Effect |
|-----------|--------|
| Verification | unchanged (raw-byte based) |
| Event extraction | unchanged (29 events) |
| Health | **improved**: EKF `NO DATA→OK` (XKF4 now parses); GPS `SITL→RTK_FIXED` |
| Replay | **improved**: clean trajectory; `ATT` attitude available |
| Plotter | works; 92 types; PID grouped correctly |
| Exports | unchanged |
| Debrief | corrected values (see `docs/screenshots/sprint1_2/debrief_corrected.png`) |

No subsystem regressed; all changes are corrections.

---

## Known Follow-ups (do not re-investigate; already scoped)
- **Sprint-1.3 — Parser Format Completeness:** `FORMAT_MAP` lacks `E` (uint32×100)
  and `g` (float16); `e` mapping (float vs int32×100) needs evidence. Not hit by
  logs 02/11/12. See `docs/ap_logger_format_study.md` §5.
- **Performance:** chunk-exclusion scan is pure-Python O(n) (~22 s/193 MB). Candidate
  for vectorization if large-log UX requires it.

---

## Provenance
Branch `sprint-1.2-data-accuracy`, commits `1132391` (fixes) and `4b307b2`
(deliverables). Cross-validated against `AP_Logger/` (reference, not vendored).
Detailed analyses: `docs/sprint1_2_findings.md`, `docs/ap_logger_format_study.md`,
`docs/sprint1_2_report.md`.
