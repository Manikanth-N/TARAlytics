# P1 Step 4.1 — Shared Cursor Infrastructure
## Status: implemented, wired end-to-end, tested, benchmarked. Timeline UI not started.

The shared-cursor backbone now lives in `AppState`: one cursor, one guarded broadcast,
and lazy shared services. The existing Plotter ↔ 3D ↔ Map sync was migrated onto it,
validating the backbone with real surfaces (no behaviour change).

---

## 1. Architecture Notes

`ui/app_state.py`:

```
# state
_cursor_time: float = 0.0
_broadcasting: bool = False          # loop-prevention guard
_sample_service / _timeline_model / _rc_model = None   # lazy, per-log

# API
cursor_time_changed = pyqtSignal(float)      # the one cursor (existing signal, now guarded)
set_cursor_time(t)                           # guarded broadcast; updates store; emits once
cursor_time -> float                         # last position (for late subscribers)
jump_to_event(t)                             # emits event_jumped + set_cursor_time (one op)

@property sample_service -> SampleService    # built on first use over current data
@property timeline_model  -> TimelineModel
@property rc_model         -> RCModel
```

- **Single source of truth.** `set_cursor_time` records `_cursor_time` and emits
  `cursor_time_changed` exactly once. Every surface reads the same cursor; late
  subscribers read `cursor_time`.
- **Loop prevention.** A subscriber whose handler calls `set_cursor_time` again is
  ignored while a broadcast is in flight (`_broadcasting` guard), so there is no
  feedback loop. The guard always clears (try/finally), so the next independent move
  still works.
- **Lazy shared services.** `sample_service` / `timeline_model` / `rc_model` are built
  on first access over the current `data` and **cached** (same instance returned), so
  all surfaces share one engine. On `set_parsed_data` they are **invalidated** and the
  cursor is **reset to 0**, so a log reload starts clean.
- **One-operation event selection.** `jump_to_event` emits `event_jumped` (for Events
  highlighting) and moves the shared cursor — a single user action updates everything.

---

## 2. Tests (`tests/test_app_state_cursor.py`, 12)

| Requirement | Test(s) |
|-------------|---------|
| single update propagation | one emission per set; cursor_time stored |
| no recursive updates | re-entrant `set_cursor_time` dropped; guard clears after broadcast |
| repeated cursor movement | 50 moves all propagate; final state correct |
| multiple subscribers | 3 subscribers all receive the same value |
| subscriber removal | disconnected subscriber stops receiving |
| log reload behavior | services rebuilt (new instances) + cursor reset to 0; all three services invalidated |
| lazy services | None without data; built+cached on data; `value_at` correct |

Backbone suite: **12 passed**. Full project suite after migration: **233 passed**
(no regressions).

End-to-end smoke (real log 02): plotter `crosshair_moved.emit(150)` → AppState
broadcast → `cursor_time == 150`, 3D/Map/Plotter follow, `sample_service` resolves.

---

## 3. Performance

| Scenario | Cost / move | Throughput |
|----------|-------------|-----------|
| Bare broadcast (guard + emit, 6 light subscribers) | **1.21 µs** | 828,000 moves/s |
| Realistic (1 panel subscriber = 12 SampleService lookups + 5 light) | **23.0 µs** | 43,400 moves/s |

The broadcast/guard mechanism itself is ~1 µs; the per-move cost is dominated by the
subscriber's data work (~23 µs for a full 12-signal panel), already proven flat across
4–440 MB logs in Steps 1–3. Against the 60 fps budget (16,700 µs) that is **~725×
headroom** — cursor dragging will be smooth with many subscribers attached.

---

## 4. Before / After Wiring Diagram

### Before (direct, point-to-point — no single cursor)
```
 Plotter.crosshair_moved ─┬─▶ MainWindow.plotter_cursor_moved
                          ├─▶ Tab3D.set_time
                          └─▶ Map.set_time
 (Plotter's own crosshair set only locally; Verification/Debrief used direct
  self._mw._tab_plotter.set_crosshair calls; no shared cursor, no guard, no
  single source of truth, no place for new surfaces to subscribe.)
```

### After (one guarded cursor through AppState)
```
            user interaction (drag plot / scrub / select event)
                              │ set_cursor_time(t)   [guarded: drops echoes]
                              ▼
                  AppState.cursor_time_changed(t)        ── cursor_time stored
        ┌───────────────┬───────────────┬───────────────┬─────────────── … ┐
        ▼               ▼               ▼               ▼                   ▼
   Plotter           Tab3D            Map         (future) Timeline   (future) Cursor
   set_crosshair     set_time        set_time      Canvas / Events     Context / Values
        │
        └─ Plotter.crosshair_moved ─▶ set_cursor_time   (drives the cursor)

 Shared services hang off the same AppState:
   AppState.sample_service / timeline_model / rc_model   (one instance each, per log)
```

The migration is behaviour-equivalent for today's surfaces (Plotter/3D/Map stay in
sync) but now there is **one cursor, one guard, one set of shared services**, and any
new surface (Timeline, Cursor Context Panel, Values-at-Cursor, Horizon, RC viz) joins
by connecting to `cursor_time_changed` and reading `sample_service` — no point-to-point
rewiring.

---

## 5. Conclusion / Next
The shared cursor backbone is complete, wired into the live app, validated (12 backbone
tests + 233 suite), and effectively free (~1 µs broadcast; ~23 µs with a full panel).
Surfaces can now be attached without bespoke wiring. Next: **Step 4.2 — TimelineCanvas
+ TimelineModule** (lanes from `TimelineModel`, click/drag → `set_cursor_time`,
event stepping), the first cursor-driven UI surface.
