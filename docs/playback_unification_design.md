# Playback Unification — Architecture Review (P0.1)

**Status:** REVIEW ONLY — approved findings, implementation **held until P1 (GPU
validation of vertical exaggeration) is complete**, per directive. No replay code is to
change before that.

**Origin:** RC Validation audit finding **F1** — dual, unsynchronized playback engines.

---

## 1. Current architecture — what's actually duplicated

Position is already unified: `AppState.cursor_time` + `cursor_time_changed`, with the
`_broadcasting` loop-guard; every surface follows it. Everything *else* about playback is
duplicated:

| State | TimelineTransport (bottom) | ReplayControls (3D tab) |
|---|---|---|
| Timer (33 ms) | own `QTimer` (`ui/widgets/timeline_transport.py:201`) | own `QTimer` (`ui/widgets/replay_controls.py:23`) |
| Play flag | `_playing` | `_playing` |
| Speed | `_speed_cb` combo | 0.5×/1×/2×/5×/10× buttons |
| Position (`_current`) | reads `AppState` | own `_current` |
| Drives cursor | `_tick → set_cursor_time` | `_tick → time_changed → View3D → set_cursor_time` |

Shortcuts (Space / [ / ]) are wired to **only** the 3D replay
(`ui/main_window.py:288-294`). Timer, play flag, and speed exist twice and never sync —
the root of F1 (double-drive + button desync).

## 2. Target architecture — one controller, two views

A single **`PlaybackController`** owns the only timer, play flag, and speed, and advances
`AppState.cursor_time`. `TimelineTransport` and `ReplayControls` become **views**: they
render controller state and send commands; they own no timer/flag/speed.

```
        ┌──────────────────────── AppState ────────────────────────┐
        │  cursor_time / cursor_time_changed   (position — already) │
        │  playback : PlaybackController        (NEW, lazy, 1/window)│
        └───────────────────────────────────────────────────────────┘
                         ▲ commands              │ signals
        play/pause/toggle│ set_speed/seek/step   │ playing_changed(bool)
                         │                        │ speed_changed(float)
        ┌────────────────┴───────┐    ┌───────────┴────────────┐
        │  TimelineTransport     │    │  ReplayControls (3D)   │
        │  (view: ▶/⏸, speed,   │    │  (view: ▶/⏸, speed,   │
        │   playhead)            │    │   slider, time label)  │
        └────────────────────────┘    └────────────────────────┘
                  shortcuts (Space/[/]) → app_state.playback
```

`PlaybackController(QObject)` — one per AppState (per window → multi-instance safe):

```
signals: playing_changed(bool), speed_changed(float)
owns:    QTimer(33ms), _playing, _speed, _t0/_t1 (span)
api:     set_span(t0,t1); play(); pause(); toggle(); set_speed(x);
         seek(t)  -> app.set_cursor_time(t)        # scrub
         step(dt) -> seek(cursor + dt)
         _tick(): t = cursor + (dt*_speed); if t>=t1: pause(); app.set_cursor_time(t)
         is_playing; speed
```

- Position stays `AppState.cursor_time` (no third copy).
- One play flag, one speed, one timer.

## 3. Responsibilities after refactor

- **Transport / ReplayControls views:** play → `playback.toggle()`; speed →
  `playback.set_speed()`; scrub/drag → `playback.seek()`. Subscribe to `playing_changed`
  (set ▶/⏸) and `speed_changed` (set combo/buttons). Playhead/labels still follow
  `cursor_time_changed`. Keep thin `toggle_play()/step()` shims that delegate (preserve
  existing callers/tests).
- **Shortcuts:** `Space → app_state.playback.toggle()`, `[ / ] → playback.step(∓0.5)`.
- **View3D:** drop `_on_replay_time → set_cursor_time` (controller owns it); keep
  `set_time` (cursor follower for the 3-D scene).

## 4. Migration plan (phased, when unblocked)

- **A** — add `PlaybackController` + lazy `AppState.playback`; unit-test
  play/pause/speed/seek/step + end-of-span stop. No behaviour change.
- **B** — repoint `TimelineTransport` (remove its timer/flag/speed-as-truth → views).
- **C** — repoint `ReplayControls`; remove `View3D._on_replay_time` cursor write;
  shortcuts → controller.
- **D** — update tests; add regression: two views, one controller — toggling either flips
  both ▶/⏸ and never double-advances.

## 5. Affected code & tests

- Code: `ui/widgets/timeline_transport.py`, `ui/widgets/replay_controls.py`,
  `ui/tab_3d_view.py` (`_on_replay_time`), `ui/main_window.py` (shortcuts),
  `ui/app_state.py` (add `playback`).
- Tests: `tests/test_isolation.py` uses `a._transport.toggle_play(); a._transport._tick()`
  — keep working via delegating `toggle_play()` + ticks routed through the controller, or
  adjust. Grep for any `_replay`/`_transport` timer/flag access before Phase B.

## 6. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Behaviour change to headline Replay during an RC | Phased, each phase test-gated; delegating shims keep public API stable |
| Two speed widgets drift | Both render from `speed_changed`; single source |
| Multi-instance leakage | Controller per-AppState (per window); re-run `test_isolation` |
| Hidden view while playing | Controller is AppState-owned, independent of mounted views |

## 7. Done =
One timer, one play flag, one speed. Play/Space anywhere flips both buttons; scrubbing
either updates the other; no double-speed when both are visible. A new regression test
asserts this.

---

## P1 prerequisite (blocks implementation)

Validate the P2 vertical exaggeration on a real GPU display (`pyqtgraph.opengl` cannot
render headless). Per-log: 00000002 ≈ ×1.0, 00000011 ≈ ×2.8, 00000012 ≈ ×2.0; confirm
telemetry Alt shows **true** metres, path colour matches true altitude, and
takeoff/climb/hover/descent/landing are distinguishable from the replay alone. Only after
this confirmation does P0.1 implementation begin.
