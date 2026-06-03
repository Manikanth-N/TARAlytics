# Sprint-1.1 — Parser Quality Changelog
## Branch: `sprint-1.1-parser-quality` (off `ui`)
## Scope: SAFE structural fixes only — NO filter changes

---

## 1. Parser-Quality Changelog

Three structural corrections to `core/log_parser.py` (+15 / −6 lines). The row
filters (`TimeUS < 3e11`, `FIELD_BOUNDS` clamp, `|x| < 1e9`) are **deliberately
left untouched**. The regressive stash filter block was **not** adopted.

| ID | Change | File / location | Rationale |
|----|--------|-----------------|-----------|
| **S1** | Add `INTEGER_FMTS` set; `get_instance_col()` gains a `scales` arg and skips instance-like names whose format is a float | `log_parser.py` constants + `get_instance_col` | A float column named `I` (PID **integral** term) was being mistaken for an instance index, splitting PID tables and silently dropping the `I` data |
| **S2** | Pass `scales` at the call site: `get_instance_col(columns, scales)` | `_pass2_parse_all` | Enables S1 |
| **S3** | `_VALID_COL` regex; truncate the 64-byte column blob at the first NUL; keep only valid identifiers | `_pass1_collect_fmt` | `MOTB`'s column list contained trailing binary garbage decoded as a "column name" |
| **S4** | `return dict(sorted(result.items()))` | end of `parse()` | Deterministic, alphabetical message-type ordering |

**Explicitly NOT changed:** filter block (lines ~171–185). A regression-guard
test (`TestFiltersPreserved`) asserts `3e11`, `FIELD_BOUNDS[col]`, and `1e9`
remain present and that the stash's `1e15` is absent.

---

## 2. Before / After — Type Count

| | Before (ui) | After (S1–S4) |
|---|---|---|
| Total message types | **64** | **59** |

The −5 net is the PID consolidation: 8 spurious instanced PID keys collapse into
3 correct base keys (see §4). No real message type was lost; `CANF`, `ESCX[4]`,
`ESCX[6]` etc. are unchanged.

---

## 3. Before / After — MOTB Columns

**Before:**
```
['TimeUS', 'LiftMax', 'BatVolt', 'ThLimit', 'ThrAvM1HCH',
 '0\x00\x00\xef\x0f\x00\x00P!z\x...\x1clc\x...`T\x...9\xe5',  ← binary garbage
 'TimeS']
```

**After:**
```
['TimeUS', 'LiftMax', 'BatVolt', 'ThLimit', 'ThrAvM1HCH', 'TimeS']
```

The garbled 6th "column" (raw bytes past the FMT record's NUL terminator) is
gone. No valid column was removed.

---

## 4. Before / After — PID Fields

**Before** (8 keys; `I` integral term dropped, treated as instance index):
```
PIDR[0]
PIDY[0]
PIDE[0]  PIDE[1]  PIDE[2]  PIDE[3]  PIDE[4]  PIDE[5]
```

**After** (3 keys; `I` column restored as float data):
```
PIDR   — columns include 'I' (float)
PIDY   — columns include 'I' (float)
PIDE   — columns include 'I' (float)
```

Verified: `PIDR/PIDY/PIDE` each have an `I` column of float dtype. The plotter
groups these under ATTITUDE by base name and renders them correctly
(`MSG_GROUPS` references `'PIDR','PIDP','PIDY'`).

---

## 5. Regression Test Results

### Success criteria — all metrics UNCHANGED (`logs/00000002.BIN`)

| Metric | Before | After | Result |
|--------|--------|-------|--------|
| Duration | `0:58` | `0:58` | UNCHANGED ✓ |
| Altitude (max) | `199968.8 m` | `199968.8 m` | UNCHANGED ✓ |
| Speed (max) | `199968.8 m/s` | `199968.8 m/s` | UNCHANGED ✓ |
| Distance | `44133.13 km` | `44133.13 km` | UNCHANGED ✓ |
| Event count | `29` | `29` | UNCHANGED ✓ |
| Mode changes | `4` | `4` | UNCHANGED ✓ |
| ARM events | `2` | `2` | UNCHANGED ✓ |
| EKF health | `NO DATA` | `NO DATA` | UNCHANGED ✓ |
| GPS health | `SITL` | `SITL` | UNCHANGED ✓ |

### Cross-feature smoke (headless)

| Check | Result |
|-------|--------|
| Verification | `VERIFIED` / 1098 chunks — UNCHANGED ✓ |
| Plotter PID nodes | `PIDR / PIDY / PIDE` present, selectable ✓ |
| Replay trajectory | 586 points loaded ✓ |
| Debrief metrics | duration `0:58`, events `29` — UNCHANGED ✓ |

### Test suites

| Suite | Result |
|-------|--------|
| `tests/test_parser_quality.py` (new, 14 tests) | **14 passed** |
| Full suite `tests/` | **146 passed, 0 failed** (132 prior + 14 new) |

---

## 6. Deferred — tracked as Sprint-1.2

The garbage values (altitude `199968.8 m`, duration `0:58`, speed, distance) are
**not** addressed here and are unchanged by design. They are tracked in
[sprint1_2_data_accuracy.md](sprint1_2_data_accuracy.md).

---

## 7. Files Changed (Sprint-1.1 commit)

| File | Change |
|------|--------|
| `core/log_parser.py` | S1–S4 structural fixes (+15 / −6) |
| `tests/test_parser_quality.py` | new — 14 regression/lock-in tests |

UI / data-processing separation preserved: Sprint-1 (UI) is commit `b521097` on
`ui`; Sprint-1.1 (data-processing) is isolated on this branch.
