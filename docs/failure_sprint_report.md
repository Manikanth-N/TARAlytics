# Failure Testing Sprint — Report (RC hardening)

Treated TARAlytics as release-candidate software. Adversarial tests across all ten
areas; defects found were fixed (fixing crashes/leaks is not adding features). No new
features added. Suite: **397 passing** (+ 1 slow huge-log test). Tests live in
`tests/test_failure_sprint.py`; long soak / huge in `scripts/soak_test.py`.

---

## Results by area

| # | Area | Result |
|---|------|--------|
| 1 | Corrupted logs (random bytes, bit-flips, garbage FMT) | ✅ no crash — parser returns `{}`/partial |
| 2 | Truncated logs (cut at many offsets, mid-record/FMT/chunk) | ✅ no crash; surviving frames have valid `TimeS` |
| 3 | Missing messages (ATT/GPS/MODE/ARM/POS absent, empty data) | ✅ analytics/timeline/snapshot/surfaces degrade gracefully |
| 4 | Invalid signatures (tampered body, wrong key, bad chunk offsets) | ✅ no crash; tamper never reported VERIFIED |
| 5 | Huge logs (440 MB parse + analyze) | ✅ 6.9 s / 1.46 GB, verdict produced |
| 6 | Workspace persistence (save/restore, corrupt QSettings) | ✅ survives reload; invalid JSON → `{}` (no crash) |
| 7 | Pop-out panels (repeated open/close/redock, relayout while floating) | ✅ no crash; **leak fixed** (below) |
| 8 | Replay state transitions (rapid play/pause/scrub/reset, reload mid-play) | ✅ no crash; cursor stays in range |
| 9 | Cancel / reload flows (different logs, error path, reload while floating) | ✅ cursor reset, snapshots cleared, **no subscriber leak** |
| 10 | Long-duration soak (80+ reload cycles) | ✅ **no object leak** (see analysis) |

---

## Defects found & fixed

**D1 — Workspace layout churn leaked memory (pop-out/redock & layout switch).**
Each `set_layout` created new `PanelFrame`s + `QSplitter`s and `deleteLater`'d the old
ones, churning C++ memory around the heavy pyqtgraph surfaces.
*Fix:* a **persistent split structure + cached PanelFrames** reused across layout
changes (move frames between the splitters and a hidden stash; never recreate).
Measured: pop-out/redock **+0.44 → +0.00 MB/iter**; layout-switch with plots
**+0.318 → +0.116 MB/iter**.

**D2 — Floating pop-out windows weren't destroyed on close.**
*Fix:* `WA_DeleteOnClose` on the floating panel; the surface is detached first so it
re-docks intact.

**D3 — Parser left large transient arenas resident.**
*Fix:* a guarded `malloc_trim(0)` in the parse worker after a parse completes (returns
freed memory to the OS on Linux/glibc; no-op on Windows).

---

## Memory-leak analysis — conclusion: **no leak**

Across 80+ reload cycles (reload + 30 cursor scrubs + layout switch + pop-out/redock +
snapshot), the **live object counts are stable**:
- `DataFrame` instances: **10** (exactly one log's worth) at every cycle — old data is
  released.
- `ndarray`: 0 retained; workspace frame cache bounded (≤ distinct surfaces); snapshots
  cleared on reload (≤ 1); **cursor subscriber count constant** across reloads.

Resident RSS does climb with cycles, but this is **glibc malloc arena retention**, not
leaked objects: it is non-monotonic across operation mixes (a true leak would be
additive), `malloc_trim` recovers part of it, and the rest is reused by subsequent
parses (bounded, not unbounded). The object-count invariant is codified as a
regression test (`TestSoakNoLeak.test_no_object_leak_across_reloads`).

---

## Crashes / hangs / state corruption

- **Crashes:** none across all adversarial inputs (33 tests).
- **Hangs:** none; the byte scans are bounded (`bytes.find`), playback timers stop at
  the span end, and reload mid-play handles a changed span.
- **Incorrect analytics:** none observed — degraded inputs yield `NO DATA`/partial
  verdicts, never fabricated values; tamper never verifies.
- **State corruption:** none — reload resets the cursor, rebuilds shared services,
  clears snapshots, and re-uses (does not duplicate) cursor subscriptions; pop-out
  redocks cleanly; corrupt saved-layout settings fall back to empty.

## Residual / known (low severity, documented)
- Rapidly switching workspace layouts that swap pyqtgraph surfaces (Signals↔Map) still
  costs ~0.1 MB per switch in allocator terms (reusable, not a live-object leak).
- 3-D Replay requires a desktop OpenGL context (unchanged; headless degrades safely).

**Assessment:** no release-blocking crashes, hangs, leaks, or state corruption found;
the two real defects (workspace churn, floating-window lifetime) are fixed and
regression-tested.
