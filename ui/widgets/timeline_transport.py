"""
Persistent Timeline Transport (P4.1).

A thin, always-visible strip at the bottom of the window: a compact whole-flight
timeline (mode bands · event pins · altitude spine · cursor) plus playback controls
(reset / play-pause / speed). It is the single global time control — scrubbing or
playing here drives the shared cursor, so every module (Signals, Replay, Map,
Situation, Evidence, Verification …) follows the same transport without switching to
the Timeline tab.

Reuses the pure time↔pixel + clustering helpers from timeline_canvas; no new analysis.
"""
from __future__ import annotations
import numpy as np

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QComboBox, QLabel, QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QPainterPath, QPolygonF, QFontMetrics,
)

from ui.design.tokens import T
from ui.widgets.timeline_canvas import (
    time_to_x, x_to_time, cluster_events, _MODE_PALETTE, _SEV_COLOR,
)

_SPEEDS = [0.5, 1.0, 2.0, 5.0, 10.0]
_GUTTER = 4


class MiniTimeline(QWidget):
    """Compact whole-flight strip: mode bands + event pins + altitude + cursor.
    Click/drag scrubs the shared cursor; it follows cursor_time_changed."""

    def __init__(self, app_state, parent=None):
        super().__init__(parent)
        self._app = app_state
        self._t0 = 0.0
        self._t1 = 1.0
        self._cursor = 0.0
        self._modes = []
        self._events = []
        self._alt_t = np.array([])
        self._alt_y = np.array([])
        self._scrubbing = False
        self.setMinimumHeight(48)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        app_state.data_changed.connect(self._on_data)
        app_state.connect_cursor(self._on_cursor, 'TimelineTransport')

    # data / cursor
    def _on_data(self, _d):
        tm = self._app.timeline_model
        if tm is None:
            self._modes, self._events = [], []
            self._alt_t = self._alt_y = np.array([]); self._t0, self._t1 = 0.0, 1.0
        else:
            self._t0, self._t1 = tm.log_span()
            if self._t1 <= self._t0:
                self._t1 = self._t0 + 1.0
            self._modes = tm.mode_segments()
            self._events = tm.event_regions()
            ap = tm.altitude_profile(max_points=1200)
            self._alt_t, self._alt_y = ap.times, ap.agl
        self._cursor = self._app.cursor_time
        self.update()

    def _on_cursor(self, t):
        self._cursor = float(t)
        self.update()

    # geometry
    def _plot_x(self):
        return float(_GUTTER), float(self.width() - _GUTTER)

    def _x2t(self, x):
        x0, x1 = self._plot_x()
        return x_to_time(x, self._t0, self._t1, x0, x1)

    def _t2x(self, t):
        x0, x1 = self._plot_x()
        return time_to_x(t, self._t0, self._t1, x0, x1)

    # interaction
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._scrubbing = True
            self._app.set_cursor_time(self._x2t(e.position().x()))

    def mouseMoveEvent(self, e):
        if self._scrubbing:
            self._app.set_cursor_time(self._x2t(e.position().x()))

    def mouseReleaseEvent(self, e):
        self._scrubbing = False

    # paint
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(T.surface.panel))
        x0, x1 = self._plot_x()
        if self._t1 <= self._t0:
            p.end(); return

        mode_h = 10
        alt_top = 4
        alt_bot = h - mode_h - 14
        mode_y = h - mode_h - 12
        axis_y = h - 11

        # altitude spine
        if self._alt_t.size >= 2 and alt_bot > alt_top:
            ys = self._alt_y[np.isfinite(self._alt_y)]
            if ys.size:
                lo, hi = float(ys.min()), float(ys.max())
                if hi - lo < 1e-6:
                    hi = lo + 1.0
                path = QPainterPath(); started = False
                for t, v in zip(self._alt_t, self._alt_y):
                    if not np.isfinite(v):
                        continue
                    xx = self._t2x(t)
                    yy = alt_bot - (v - lo) / (hi - lo) * (alt_bot - alt_top)
                    if not started:
                        path.moveTo(xx, yy); started = True
                    else:
                        path.lineTo(xx, yy)
                if started:
                    p.setPen(QPen(QColor(T.brand.blue_bright), 1.2)); p.drawPath(path)

        # mode bands
        for s in self._modes:
            sx0 = max(self._t2x(s.t_start), x0); sx1 = min(self._t2x(s.t_end), x1)
            if sx1 - sx0 < 1:
                continue
            col = QColor(_MODE_PALETTE[s.mode_num % len(_MODE_PALETTE)]
                         if s.mode_num >= 0 else '#42566B')
            col.setAlphaF(0.55)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(col))
            p.drawRect(QRectF(sx0, mode_y, sx1 - sx0, mode_h))
            if sx1 - sx0 > 40:
                p.setFont(QFont(T.font.brand, 8)); p.setPen(QPen(QColor(T.text.primary)))
                p.drawText(QRectF(sx0 + 3, mode_y, sx1 - sx0 - 4, mode_h),
                           int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                           s.mode)

        # event pins (clustered)
        clusters = cluster_events(self._events, self._t0, self._t1, x0, x1, min_px=8)
        for cl in clusters:
            cx = self._t2x(cl.t)
            col = QColor(_SEV_COLOR.get(cl.severity, T.brand.blue))
            p.setPen(QPen(col, 1)); p.drawLine(QPointF(cx, alt_bot), QPointF(cx, mode_y))
            p.setBrush(QBrush(col)); p.setPen(QPen(QColor(T.surface.panel), 1))
            p.drawEllipse(QPointF(cx, alt_bot + 2), 3, 3)

        # axis ticks (coarse)
        p.setPen(QPen(QColor(T.text.muted))); p.setFont(QFont(T.font.data, 8))
        span = self._t1 - self._t0
        step = _nice(span)
        t = np.ceil(self._t0 / step) * step
        while t <= self._t1:
            xx = self._t2x(t)
            p.drawText(QRectF(xx - 24, axis_y, 48, 11), int(Qt.AlignmentFlag.AlignCenter), f'{t:.0f}s')
            t += step

        # cursor playhead
        if self._t0 <= self._cursor <= self._t1:
            cx = self._t2x(self._cursor)
            col = QColor(T.brand.blue_bright)
            p.setPen(QPen(col, 1.4)); p.drawLine(QPointF(cx, 0), QPointF(cx, mode_y + mode_h))
            tri = QPolygonF([QPointF(cx - 4, 0), QPointF(cx + 4, 0), QPointF(cx, 6)])
            p.setBrush(QBrush(col)); p.setPen(Qt.PenStyle.NoPen); p.drawPolygon(tri)
        p.end()


def _nice(span):
    if span <= 0:
        return 1.0
    raw = span / 8
    mag = 10 ** np.floor(np.log10(raw))
    for m in (1, 2, 5, 10):
        if raw <= m * mag:
            return float(m * mag)
    return float(10 * mag)


class TimelineTransport(QWidget):
    """Bottom bar: playback controls + MiniTimeline. The single global time control."""

    def __init__(self, app_state, parent=None):
        super().__init__(parent)
        self._app = app_state
        self._speed = 1.0
        self._playing = False
        self._direction = 1            # +1 forward, -1 reverse
        self._t0 = 0.0
        self._total = 0.0
        self._use_hours = False
        self.setFixedHeight(74)
        self.setStyleSheet(f'background: {T.surface.panel};')

        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)

        root = QHBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 4)
        root.setSpacing(8)

        ctl = QVBoxLayout(); ctl.setSpacing(3)
        btns = QHBoxLayout(); btns.setSpacing(4)
        # Directional transport — the single, global playback controller. Every
        # control drives the shared cursor, so all surfaces (Replay, Map, Signals,
        # Horizon, Timeline, Dock) follow. Replay does not own playback.
        self._start_btn    = self._tbtn('⏮', 'Jump to start')
        self._stepback_btn = self._tbtn('⏪', 'Step back 0.5 s')
        self._rev_btn      = self._tbtn('◀', 'Play in reverse')
        self._play_btn     = self._tbtn('▶', 'Play / pause', primary=True)
        self._fwd_btn      = self._tbtn('▶', 'Play forward')
        self._stepfwd_btn  = self._tbtn('⏩', 'Step forward 0.5 s')
        self._start_btn.clicked.connect(self._to_start)
        self._stepback_btn.clicked.connect(lambda: self.step(-0.5))
        self._rev_btn.clicked.connect(lambda: self._play(-1))
        self._play_btn.clicked.connect(self.toggle_play)
        self._fwd_btn.clicked.connect(lambda: self._play(1))
        self._stepfwd_btn.clicked.connect(lambda: self.step(0.5))

        self._speed_cb = QComboBox()
        for s in _SPEEDS:
            self._speed_cb.addItem(f'{s:g}×', s)
        self._speed_cb.setCurrentIndex(1)
        self._speed_cb.setStyleSheet(
            f'QComboBox {{ background: {T.surface.card}; color: {T.text.secondary}; '
            f'border: 1px solid {T.border.default}; border-radius: 3px; padding: 1px 4px; '
            f'font-size: {T.size.xs}px; }}')
        self._speed_cb.currentIndexChanged.connect(
            lambda i: setattr(self, '_speed', self._speed_cb.itemData(i)))

        for w in (self._start_btn, self._stepback_btn, self._rev_btn,
                  self._play_btn, self._fwd_btn, self._stepfwd_btn):
            btns.addWidget(w)
        btns.addSpacing(8)
        spd_lbl = QLabel('Speed')
        spd_lbl.setStyleSheet(f'color: {T.text.muted}; font-size: {T.size.xs}px;')
        btns.addWidget(spd_lbl)
        btns.addWidget(self._speed_cb)
        btns.addStretch()
        # Fixed-width monospaced transport clock (elapsed / total). Reserving the
        # width for the longest expected value keeps the bar perfectly still while
        # playback runs — the digits update in place, nothing reflows.
        clock_font = QFont(T.font.data, T.size.xs)
        clock_font.setStyleHint(QFont.StyleHint.Monospace)
        self._time_lbl = QLabel('00:00 / 00:00')
        self._time_lbl.setFont(clock_font)
        self._time_lbl.setStyleSheet(f'color: {T.text.primary};')
        self._time_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._size_clock()
        ctl.addLayout(btns); ctl.addWidget(self._time_lbl)
        root.addLayout(ctl)

        self._mini = MiniTimeline(app_state)
        root.addWidget(self._mini, 1)

        app_state.connect_cursor(self._on_cursor, 'TimelineTransport.label')
        app_state.data_changed.connect(self._on_total)

    def _tbtn(self, text, tip, primary=False):
        b = QPushButton(text); b.setToolTip(tip)
        b.setFixedSize(36 if primary else 30, 24 if primary else 22)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        bg = T.brand.blue_deep if primary else T.surface.card
        weight = 'bold' if primary else 'normal'
        b.setStyleSheet(
            f'QPushButton {{ background: {bg}; color: {T.text.primary}; '
            f'border: 1px solid {T.border.default}; border-radius: 3px; '
            f'font-size: 12px; font-weight: {weight}; }} '
            f'QPushButton:hover {{ border-color: {T.border.active}; }}')
        return b

    def _on_cursor(self, t):
        elapsed = max(0.0, float(t) - self._t0)
        self._time_lbl.setText(f'{self._fmt_clock(elapsed)} / {self._fmt_clock(self._total)}')

    def _on_total(self, _data=None):
        t0, t1 = self._span()
        self._t0 = t0
        self._total = max(0.0, t1 - t0)
        self._use_hours = self._total >= 3600
        self._size_clock()
        self._on_cursor(self._app.cursor_time)

    def _fmt_clock(self, seconds: float) -> str:
        s = int(round(seconds))
        if self._use_hours:
            return f'{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}'
        return f'{s // 60:02d}:{s % 60:02d}'

    def _size_clock(self):
        # Reserve width for the longest value the current log can show.
        longest = '00:00:00 / 00:00:00' if self._use_hours else '00:00 / 00:00'
        w = QFontMetrics(self._time_lbl.font()).horizontalAdvance(longest) + 10
        self._time_lbl.setFixedWidth(w)

    def _span(self):
        tm = self._app.timeline_model
        if tm is not None:
            return tm.log_span()
        return 0.0, 0.0

    def _play(self, direction):
        """Start playing in the given direction (+1 forward, -1 reverse)."""
        self._direction = 1 if direction >= 0 else -1
        t0, t1 = self._span()
        if t1 <= t0:
            return
        cur = self._app.cursor_time
        if self._direction > 0 and cur >= t1:      # at end → rewind to start
            self._app.set_cursor_time(t0)
        elif self._direction < 0 and cur <= t0:    # at start → jump to end
            self._app.set_cursor_time(t1)
        self._playing = True
        self._timer.start()
        self._update_play_icon()

    def toggle_play(self):
        if self._playing:
            self._stop()
        else:
            self._play(self._direction)

    def step(self, dt: float):
        """Single-step the cursor by dt seconds (pauses playback)."""
        self._stop()
        t0, t1 = self._span()
        if t1 <= t0:
            return
        self._app.set_cursor_time(min(max(self._app.cursor_time + dt, t0), t1))

    def _to_start(self):
        self._stop()
        t0, _ = self._span()
        self._app.set_cursor_time(t0)

    # kept for back-compat (older callers / tests)
    def _reset(self):
        self._to_start()

    def _stop(self):
        self._playing = False
        self._timer.stop()
        self._update_play_icon()

    def _update_play_icon(self):
        self._play_btn.setText('⏸' if self._playing else '▶')

    def _tick(self):
        t0, t1 = self._span()
        if t1 <= t0:
            self._stop(); return
        t = self._app.cursor_time + 0.033 * self._speed * self._direction
        stop = False
        if t >= t1:
            t, stop = t1, True
        elif t <= t0:
            t, stop = t0, True
        self._app.set_cursor_time(t)
        if stop:
            self._stop()
