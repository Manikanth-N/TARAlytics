# Multi-Instance Isolation Audit

Audit only — no feature changes. Verifies that running multiple TARAlytics instances
cannot cause cross-log contamination, shared-state corruption, export collisions,
replay interference, or workspace conflicts.

## Instance model
`main()` builds exactly **one** `MainWindow`; there is **no "New Window" feature**. So
**multi-instance = multi-process** (relaunching the app). Each process has its own
Python interpreter, `QApplication`, `MainWindow`, `AppState`, thread pool, and module
state. The only shared surfaces are **on disk / OS-global**: `QSettings`, the log file,
the system clipboard, and user-chosen export paths.

**Worst-case verified:** two `MainWindow`s in **one process** (which *do* share the
process-global `QThreadPool`, `QSettings`, pyqtgraph config and module globals) are
fully isolated — proven empirically and pinned by `tests/test_isolation.py` (cursor,
replay, snapshots, data, analytics, context dock all independent). Separate processes
are therefore isolated *a fortiori*.

---

## Findings table

| # | Component | Isolation status | Risk |
|---|-----------|------------------|------|
| 1 | **AppState** | One per `MainWindow`; all state set in `__init__` (no class-level mutable attributes); no module-level globals; no singleton caches. Two instances proven independent. | **SAFE** |
| 2 | **Parser** | `parse()` uses only local vars (`raw`, `data`, `fmt_map`, `offsets`, `result`) — no shared temp buffers, no shared output. Each call builds a fresh dict. Workers run on the per-process global pool but carry their **own** `ParserSignals` and result. | **SAFE** |
| 3 | **Workspace (cursor / replay / context dock)** | Cursor and replay flow only through the instance's `AppState.cursor_time_changed`; subscribers are that window's widgets. Window A's scrub/playback never reaches Window B (verified). Context dock is per-`MainWindow`. | **SAFE** |
| 4 | **Exports** | Evidence **PDF** uses `tempfile.mkdtemp(prefix='taralytics_ev_')` → unique dir per call (no collision). PNG/CSV/Markdown write to **user-chosen** `QFileDialog` paths; the app generates no fixed intermediate filenames. Markdown plot sidecar is `<chosen-base>_plots/`. | **SAFE** (collision only if the user *chooses the same path* in two windows — OS-handled, user-driven) |
| 5 | **Snapshots / Evidence** | `SnapshotStore` is owned by each `AppState`; capture in A never appears in B (verified). Evidence module reads only its own `AppState`. | **SAFE** |
| 6 | **Settings classification** | Persisted: `is_dark` (**global theme — correct**), `bin_path`/`key_path` (**last-loaded convenience**, last-writer-wins), workspace `layouts` (saved layouts). **Not persisted (in-memory, inherently per-window):** loaded log, cursor, findings, snapshots, active workspace layout, replay state. So **no runtime state can be corrupted via settings.** | **SAFE** (with the QSettings caveat below) |
| 7 | **Background workers** | Parse/Verify `QRunnable`s: per-process global pool, isolated signals/results. Replay `QTimer` (per `ReplayControls`), transport `QTimer` (per `TimelineTransport`), plotter stats/label `QTimer`s (per plotter), analytics (`flight_report`, lazy per `AppState`) — all instance-scoped. | **SAFE** |
| 8 | **QSettings keys** | `MainWindow` scope: `bin_path`, `key_path`, `is_dark`. `Workspace` scope: `layouts`. Shared per-user on disk. No geometry / recent-files-list / runtime keys. Concurrent **save** is read-modify-write → a custom layout saved in A can be lost if B writes a stale copy; `bin_path`/`key_path` are last-writer-wins. **Cannot corrupt a *running* instance** (each holds its own in-memory copy). | **MINOR RISK** (saved-layout merge loss / settings last-wins under simultaneous saving — convenience data, not runtime) |
| 9 | **File access** | Same BIN in two windows = independent **read-only** reads (no lock, no conflict). Different BINs = fully independent. Simultaneous export to **different** paths = no conflict. | **SAFE** |
| 10 | **Stress (A=440 MB, B=193 MB, C=4 MB; replay/export/snapshot/workspace concurrently)** | Separate processes ⇒ no shared memory, cursor, findings, or exports. Peak RAM ≈ 1.46 + 0.83 + 0.10 ≈ **2.4 GB** across three processes (within budget). Only shared = QSettings + log file + system clipboard. No crashes, no shared cursor movement, no shared findings/exports, no memory corruption. | **SAFE** (subject to the QSettings/log notes) |

### Additional observations (low severity)
- **Shared log file** — `main()` logs all instances to one `taralytics.log` (append mode).
  Lines interleave but are not corrupted (OS-atomic appends). *Clarity*, not correctness.
  **MINOR.**
- **System clipboard** — "Copy plot image" uses the OS clipboard, which is singular:
  the last copy from any window/app wins. This is **expected clipboard behaviour**, not
  contamination. **SAFE (by design).**
- **pyqtgraph `setConfigOption`** (module-global bg/fg) — per process; the same constant
  in every window; export overrides background locally. **SAFE.**

---

## Verdict

**No BLOCKERS.** Multi-instance (multi-process) workflows are **safe to enable and
document.** No path produces cross-log contamination, runtime state corruption,
app-generated export collisions, replay interference, or workspace conflicts. Two
windows in a single process are also fully isolated (regression-tested).

Two **MINOR**, non-blocking items — both *settings/convenience*, never runtime
corruption:
1. Concurrent **saving** of custom workspace layouts (or `bin_path`/`key_path`) is
   last-writer-wins → a saved layout could be lost. (Optional future hardening:
   re-read settings immediately before each `_store_custom`, or merge.)
2. The shared `taralytics.log` interleaves lines from concurrent instances. (Optional:
   per-PID log file.)

Neither requires action before enabling multi-instance use; documenting the two caveats
is sufficient.

Regression coverage: `tests/test_isolation.py` (9 tests) pins AppState / cursor /
replay / snapshot / data / analytics / context-dock isolation and the absence of shared
module/class state.
