"""
PlaybackController — the single source of truth for replay playback.

Owns the only playback timer, the one play/pause flag, and the one speed, and advances
the shared cursor (`AppState.cursor_time`). The TimelineTransport and 3D ReplayControls
will become thin views/controllers of this object in a later phase; the shared
*position* already lives in AppState, so this adds the missing shared *play state*.

Phase A: added and unit-tested, but **not yet wired** to any view or shortcut — nothing
constructs/uses it in the running UI, so there is no behavior change. One controller per
AppState (per window) keeps multi-instance isolation.
"""
from __future__ import annotations
from PyQt6.QtCore import QObject, QTimer, pyqtSignal


class PlaybackController(QObject):
    playing_changed = pyqtSignal(bool)     # play/pause state
    speed_changed   = pyqtSignal(float)    # playback rate (×)

    _INTERVAL_MS = 33                       # ~30 Hz, matches the existing transports

    def __init__(self, app_state, parent=None):
        super().__init__(parent)
        self._app = app_state
        self._playing = False
        self._speed = 1.0
        self._t0 = 0.0
        self._t1 = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(self._INTERVAL_MS)
        self._timer.timeout.connect(self._tick)

    # ── span ──────────────────────────────────────────────────────────────────
    def set_span(self, t0: float, t1: float):
        """Playable time range [t0, t1] (absolute seconds)."""
        self._t0, self._t1 = float(t0), float(t1)

    @property
    def span(self) -> tuple:
        return (self._t0, self._t1)

    # ── state ─────────────────────────────────────────────────────────────────
    @property
    def is_playing(self) -> bool:
        return self._playing

    @property
    def speed(self) -> float:
        return self._speed

    def set_speed(self, x: float):
        x = float(x)
        if x > 0 and x != self._speed:
            self._speed = x
            self.speed_changed.emit(x)

    # ── transport commands ──────────────────────────────────────────────────────
    def play(self):
        if self._playing:
            return
        # Restart from the start if parked at (or past) the end.
        if self._t1 > self._t0 and self._app.cursor_time >= self._t1:
            self._app.set_cursor_time(self._t0)
        self._playing = True
        self._timer.start()
        self.playing_changed.emit(True)

    def pause(self):
        if not self._playing:
            return
        self._playing = False
        self._timer.stop()
        self.playing_changed.emit(False)

    def toggle(self):
        self.pause() if self._playing else self.play()

    def seek(self, t: float):
        """Move the cursor to an absolute time (clamped to the span)."""
        t = float(t)
        if self._t1 > self._t0:
            t = max(self._t0, min(self._t1, t))
        self._app.set_cursor_time(t)

    def step(self, dt: float):
        self.seek(self._app.cursor_time + float(dt))

    # ── timer ─────────────────────────────────────────────────────────────────
    def _tick(self):
        t = self._app.cursor_time + (self._INTERVAL_MS / 1000.0) * self._speed
        if self._t1 > self._t0 and t >= self._t1:
            self._app.set_cursor_time(self._t1)
            self.pause()
            return
        self._app.set_cursor_time(t)
