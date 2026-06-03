# Sprint-1.1 — Parser Quality (Plan & Validation)
## Status: PLAN ONLY — no parser code changed yet

---

## 0. Headline Finding (read this first)

The premise "merge the parser sanity-filter fix from master" does **not** hold as
stated. Investigation shows:

1. **The fix is not on master.** `master` and `ui` are the *same commit*
   (`0465fce`). Neither contains the sanity-filter logic.
2. **The fix lives in an uncommitted git stash** — `stash@{0}` — touching only
   `core/log_parser.py` (+22 / −17). The companion test (`test_log_00000002.py`)
   was never committed and is lost.
3. **The stash does not apply cleanly.** It was authored against parser blob
   `46de90e`; the current `ui` parser is `2e6d45e`, already evolved (commit
   `e62a2e4` widened the `TimeUS` bound `3e8 → 3e11` and kept `FIELD_BOUNDS`).
   `git apply` fails at line 144.
4. **Applying the stash as-is REGRESSES the current branch** (empirically measured):

   | Metric | Current (ui) | Stash applied | Verdict |
   |--------|--------------|---------------|---------|
   | duration | `0:58` | `237997799536:09` | catastrophic regression |
   | max_speed | `199968.8 m/s` | `2.2e12 m/s` | regression |
   | max_alt | `199968.8 m` | `199968.8 m` | unchanged (not fixed) |
   | distance | `44133.13 km` | `44133.13 km` | unchanged (not fixed) |

   Cause: the stash's gentle filter (`isfinite & |x| < 1e15`) is **weaker** than
   the current branch's combined `TimeUS < 3e11` + `FIELD_BOUNDS` + `|x| < 1e9`.
   Removing the current filters lets garbage `TimeUS`/velocity rows back in.

**Conclusion:** the stash mixes *good structural fixes* with a *regressive filter
change*. Sprint-1.1 must cherry-pick the structural fixes semantically and must
**not** adopt the stash's filter block. The garbage-value problem
(199968 m / 0:58) is a **separate, unsolved concern** — neither the stash nor the
current filters fix it.

---

## 1. Source Identification

| Item | Reality |
|------|---------|
| Claimed location | "commits on master" |
| Actual location | `stash@{0}: WIP on master: caf95d0` |
| Files touched | `core/log_parser.py` only (+22 / −17) |
| Stash base blob | `46de90e` |
| Current `ui` blob | `2e6d45e` (diverged) |
| Clean `git apply`? | **No** — fails at `core/log_parser.py:144` |
| Lost artifact | `test_log_00000002.py` (never committed) |

Retrieve the stash diff for reference with:
`git stash show -p stash@{0}`

---

## 2. Diff Analysis — 6 Changes, Split by Safety

The stash contains six distinct edits. Empirical testing on `logs/00000002.BIN`
classifies them:

### SAFE — structural correctness, zero metric regression (ADOPT)

| # | Change | Effect | Measured impact |
|---|--------|--------|-----------------|
| S1 | `INTEGER_FMTS` set + `get_instance_col(scales)` | A float column named `I` (PID integral term) is no longer mistaken for an instance discriminator | `PIDR[0]/PIDY[0]/PIDE[0..5]` (8 keys) → `PIDR/PIDY/PIDE` (3 keys); the dropped `I` integral column is restored |
| S2 | `get_instance_col(columns, scales)` call site | Passes format chars to S1 | (enables S1) |
| S3 | `_VALID_COL` regex + first-null column truncation | Stops parsing column names past the first NUL byte; rejects non-identifier names | `MOTB` columns: `[…'ThrAvM1HCH', '0\x00\x00…garbage']` → `[…'ThrAvM1HCH']` |
| S4 | `return dict(sorted(result.items()))` | Message types returned alphabetically | iteration order now sorted; no value change |

### REGRESSIVE — filter change, do NOT adopt as-is (REJECT)

| # | Change | Why reject |
|---|--------|-----------|
| R1 | Remove `TimeUS` bound + `FIELD_BOUNDS` clamp; replace `|x|<1e9` with `isfinite & |x|<1e15` | On the current branch this **widens** the magnitude gate (1e9→1e15) and **drops** the `TimeUS` and `FIELD_BOUNDS` guards, exploding duration/speed metrics |
| R2 | Always `reset_index` (vs only when non-empty) | Harmless, but bundled with R1; carry only if filter work is revisited |

### Net recommendation
Adopt **S1–S4**. Reject **R1–R2**. Keep the current branch's row filters intact.

---

## 3. Metric Change Table (empirical, SAFE subset only)

Measured: current `ui` parser vs. SAFE-only parser (S1–S4, filters preserved),
on `logs/00000002.BIN`:

| Metric | Current | SAFE-only | Changed? |
|--------|---------|-----------|----------|
| **Duration** | `0:58` | `0:58` | No |
| **Altitude (max)** | `199968.8 m` | `199968.8 m` | No |
| **Speed (max)** | `199968.8 m/s` | `199968.8 m/s` | No |
| **Distance** | `44133.13 km` | `44133.13 km` | No |
| **Events** | `29` | `29` | No |
| **Mode changes** | `4` | `4` | No |
| **ARM events** | `2` | `2` | No |
| **EKF health** | `NO DATA` | `NO DATA` | No |
| **GPS health** | `SITL` | `SITL` | No |
| **Message types** | `64` | `59` | **Yes** (PID consolidation) |
| **MOTB columns** | garbled | clean | **Yes** |
| **Ordering** | insertion | alphabetical | **Yes** |

**Key point:** the SAFE subset does not change any flight metric. It only
corrects data *structure* (PID tables, MOTB columns, ordering). The Debrief
values you approved for Sprint-1 therefore remain identical after S1–S4.

### What the SAFE subset does NOT fix
- Altitude still reads `199968.8 m` (garbage). `199968 < 1e9`, and `Alt` is not in
  `FIELD_BOUNDS`, so no current or stash filter removes it.
- Duration still `0:58`, distance `44133 km`, speed `199968 m/s` — all garbage,
  all unfixed. These require **new filter design**, tracked in §6 as a separate
  task, not part of the stash merge.

---

## 4. Risk Assessment

### 4.1 Verification — NO RISK
Signature verification operates on `raw_bytes`, never on the parsed DataFrame
dict (`core/signature_verifier.py` takes `raw`). Parser changes cannot affect
`full_verify`. Confirmed: VERIFIED / 1098 chunks is independent of parse output.

### 4.2 Replay (3D / 2D map) — LOW RISK
- Trajectory comes from `best_trajectory(data)` → `GPS` / `SIM2` / `SIM`. S1–S4
  do not rename or drop these keys (SIM2 stays `SIM2`; only PID keys change).
- ATT-based heading uses `data.get('ATT')` — unaffected.
- Risk only if a consumer referenced `PIDR[0]` etc. — **none do** (verified).

### 4.3 Plotter — LOW RISK
- `MSG_GROUPS` references PID by **base name** (`'PIDR','PIDP','PIDY'`), and the
  tree builder decomposes `name[inst]` via `_INST_RE`. It handles both `PIDR[0]`
  and `PIDR` correctly. The unified `PIDR` form groups identically.
- Alphabetical ordering only changes tree display order, not behavior.

### 4.4 Insertion-order dependence — NONE
No code uses `list(data.keys())[0]`, `next(iter(data))`, or positional access.
`dict(sorted(...))` is safe. (Verified by grep across `ui/` and `core/`.)

### 4.5 Tests — LOW RISK
No test references PID keys, MOTB columns, or dict ordering. Parser tests assert
parse correctness on synthetic logs; S1–S4 must be run against the suite to
confirm (see §5). Expected: green.

### 4.6 PID rename — LOW RISK, but a behavior change to announce
`PIDR[0] → PIDR` is the single user-visible key change. Anyone with saved plotter
selections referencing `PIDR[0]` would not auto-restore. Acceptable; note in
release notes.

---

## 5. Validation Checklist (run on the Sprint-1.1 branch)

Using `logs/00000002.BIN` (only test log on this branch) plus the synthetic
fixtures in `tests/`.

### Pre-merge baseline (current `ui`)
- [ ] Record: 64 types, duration `0:58`, alt `199968.8 m`, events `29`, MOTB cols (garbled), order (insertion)
- [ ] Full suite green: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 QT_QPA_PLATFORM=offscreen python3 -m pytest tests/ -q -p no:cacheprovider -p pytestqt.plugin` → 132 passed

### Post-merge (S1–S4 applied, filters preserved)
- [ ] Parser imports, valid syntax
- [ ] Message types: 64 → **59**
- [ ] PID keys: `PIDR/PIDY/PIDE` present; `PIDR[0]/PIDY[0]/PIDE[0..n]` absent
- [ ] `PIDR` has an `I` column of float dtype (integral term restored)
- [ ] `MOTB` columns = `['TimeUS','LiftMax','BatVolt','ThLimit','ThrAvM1HCH','TimeS']` (no garbage)
- [ ] `list(data.keys()) == sorted(data.keys())` (alphabetical)
- [ ] Flight metrics UNCHANGED vs baseline: duration `0:58`, alt `199968.8 m`, speed `199968.8 m/s`, distance `44133.13 km`, events `29`, modes `4`, arm `2`
- [ ] Full test suite still green (132 passed)

### Cross-feature smoke (headless, `QT_QPA_PLATFORM=offscreen`)
- [ ] App launches; parse `00000002.BIN`
- [ ] Debrief values identical to Sprint-1 (no metric drift)
- [ ] Verification still VERIFIED / 1098 chunks
- [ ] Plotter tree shows `PIDR/PIDY/PIDE` under ATTITUDE group; signals selectable
- [ ] 3D replay loads trajectory; 2D map loads; no crash
- [ ] Theme toggle, keyboard shortcuts unaffected

### Regression guard
- [ ] Confirm NO metric got worse (esp. duration/speed must stay `0:58`/`199968`, not explode) — this catches accidental adoption of R1

---

## 6. Out of Scope for the Stash Merge — Separate Task

The garbage values (alt `199968 m`, duration `0:58`, speed `199968 m/s`,
distance `44133 km`) are **not addressed** by S1–S4 and are **made worse** by
R1. Fixing them is a distinct piece of *new* filter design, to be specified and
validated on its own:

- Candidate approaches (for a later sprint, not now):
  - Add `Alt`, velocity, and position fields to `FIELD_BOUNDS` with physical caps.
  - Tighten the magnitude gate (e.g. `|x| < 1e6`) — but verify it doesn't clip
    valid large counters (e.g. `TimeUS`, energy totals).
  - Per-message physical validation instead of a blanket float gate.
- Each candidate must be measured the same way as §3 before adoption.

This task is explicitly **deferred** and kept separate so UI changes (Sprint-1)
and data-processing changes remain cleanly distinguishable, per the directive.

---

## 7. Proposed Execution (once this plan is approved)

1. `git checkout -b sprint-1.1-parser-quality` (off `ui`).
2. Apply **S1–S4 only** to `core/log_parser.py` as hand-written edits (the stash
   cannot be `git apply`-ed; do not use it directly).
3. Re-create a parser ground-truth test (`tests/test_parser_quality.py`) encoding
   the §5 post-merge expectations.
4. Run the §5 checklist; attach results.
5. Open PR isolating data-processing changes from Sprint-1 UI changes.
6. Leave §6 (garbage-value filtering) as a tracked follow-up.

No code is changed until this plan is approved.
