# Sprint-1.2 — Data Accuracy Investigation (Work Item)
## Status: OPEN — investigation only, NO data-correction code until a proposal is approved

---

## 1. Problem Statement

On `logs/00000002.BIN`, several flight metrics report physically impossible
values that survive the current parser's filters:

| Metric | Reported | Plausible reality |
|--------|----------|-------------------|
| Max altitude | `199968.8 m` | a few metres (SITL hover) |
| Duration | `0:58` | ~`0:44` (arm→disarm) |
| Max speed | `199968.8 m/s` | a few m/s |
| Distance | `44133.13 km` | metres |

These are **not** addressed by Sprint-1.1 (which only fixed PID/MOTB/ordering)
and were made worse by the rejected stash filter. They are unchanged on the
current branch by design.

---

## 2. Investigation Goals

1. **Identify the exact source of the `199968.8 m` altitude.**
   - Which message + column produces it (`POS.Alt`? `BARO[n].Alt`? `GPS.Alt`?).
   - Is the offending value a genuine garbage record, a scaling error, or a
     misparsed field?
2. **Identify the exact source of the `0:58` duration.**
   - Which message's `TimeUS` extends `t_max` to ~58 s.
   - Whether those rows are uninitialised SITL records or a `TimeUS`
     scaling/format issue.
3. **Determine the responsible layer** for each: filtering, scaling, parsing,
   or source-log content.
4. **Produce a written proposal** of correction options with measured impact —
   before any data-correction code is written.

---

## 3. Investigation Method (read-only)

Use the same non-destructive comparison harness pattern as Sprint-1.1
(temporary parser copies in `/tmp`, no repo edits):

1. **Locate the bad rows.** For each metric, find the row index and source
   message: e.g. scan `data['POS']['Alt']`, `data['BARO[0]']['Alt']`,
   `data['SIM2']`, and the global `TimeS` max; print the offending raw records
   and their `TimeUS`.
2. **Trace to raw bytes.** For one offending record, dump the raw struct bytes
   and re-unpack with the FMT spec to determine whether the value is:
   - garbage already in the log (source content), or
   - a scaling/format bug (e.g. wrong multiplier, signedness), or
   - a parse offset/length error.
3. **Characterise distribution.** How many rows are affected per message? Are
   they clustered (startup) or scattered?
4. **Test candidate corrections** in isolation and measure all §… metrics, the
   same way Sprint-1.1 did. No candidate is adopted without a before/after
   table and a green regression run.

---

## 4. Candidate Hypotheses (to confirm or reject — not yet decisions)

| # | Hypothesis | How to test |
|---|------------|-------------|
| H1 | Uninitialised SITL records: genuine garbage in the source log, no scaling involved | Inspect raw bytes; confirm values are wild in the source |
| H2 | Altitude not range-guarded: `Alt` absent from `FIELD_BOUNDS`, and `199968 < 1e9` so no filter catches it | Check which df supplies `199968.8`; test adding physical caps |
| H3 | `TimeUS` garbage rows: `< 3e11` bound (≈83 h) is too loose, admitting bad timestamps that inflate duration | Inspect `TimeUS` of the rows defining `t_max` |
| H4 | Scaling/format error on a specific field (multiplier or signedness) | Re-unpack offending record against FMT spec |

---

## 5. Constraints

- **No data-correction code in this work item.** Deliverable is a written
  proposal with measured options.
- Any future correction must preserve the Sprint-1.1 success criteria for valid
  data and must be validated against `logs/00000002.BIN` plus the synthetic
  fixtures in `tests/`.
- Keep data-processing changes isolated from UI changes (separate branch /
  commits), consistent with the Sprint-1 / Sprint-1.1 separation.

---

## 6. Deliverables (when this work item is scheduled)

1. Source identification for the `199968.8 m` altitude (message, column, row,
   raw bytes).
2. Source identification for the `0:58` duration (message, `TimeUS`, row).
3. Layer attribution per metric: filtering / scaling / parsing / source content.
4. A correction proposal with before/after metric tables for each candidate.
5. A go/no-go recommendation — no code merged until the proposal is approved.

---

## 7. Acceptance to Close

- The exact source of both anomalies is identified and documented.
- Each anomaly is attributed to a specific layer.
- A reviewed proposal exists; correction implementation is a *separate* sprint.
