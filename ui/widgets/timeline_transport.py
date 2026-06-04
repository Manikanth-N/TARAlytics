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
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPainterPath, QPolygonF

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
        self._reset_btn = self._tbtn('⏮', 'Reset to start')
        self._play_btn = self._tbtn('▶', 'Play / pause')
        self._play_btn.setStyleSheet(self._play_btn.styleSheet().replace(
            T.surface.card, T.brand.blue_deep))
        self._reset_btn.clicked.connect(self._reset)
        self._play_btn.clicked.connect(self.toggle_play)
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
        btns.addWidget(self._reset_btn); btns.addWidget(self._play_btn)
        btns.addWidget(self._speed_cb)
        self._time_lbl = QLabel('0.00 s')
        self._time_lbl.setFont(QFont(T.font.data, T.size.xs))
        self._time_lbl.setStyleSheet(f'color: {T.text.primary};')
        ctl.addLayout(btns); ctl.addWidget(self._time_lbl)
        root.addLayout(ctl)

        self._mini = MiniTimeline(app_state)
        root.addWidget(self._mini, 1)

        app_state.connect_cursor(self._on_cursor, 'TimelineTransport.label')

    def _tbtn(self, text, tip):
        b = QPushButton(text); b.setToolTip(tip); b.setFixedSize(30, 22)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(
            f'QPushButton {{ background: {T.surface.card}; color: {T.text.primary}; '
            f'border: 1px solid {T.border.default}; border-radius: 3px; font-size: 12px; }} '
            f'QPushButton:hover {{ border-color: {T.border.active}; }}')
        return b

    def _on_cursor(self, t):
        self._time_lbl.setText(f'{t:.2f} s')

    def _span(self):
        tm = self._app.timeline_model
        if tm is not None:
            return tm.log_span()
        return 0.0, 0.0

    def toggle_play(self):
        if self._playing:
            self._playing = False; self._timer.stop(); self._play_btn.setText('▶')
        else:
            t0, t1 = self._span()
            if t1 <= t0:
                return
            if self._app.cursor_time >= t1:
                self._app.set_cursor_time(t0)
            self._playing = True; self._timer.start(); self._play_btn.setText('⏸')

    def _reset(self):
        self._playing = False; self._timer.stop(); self._play_btn.setText('▶')
        t0, _ = self._span()
        self._app.set_cursor_time(t0)

    def _tick(self):
        t0, t1 = self._span()
        if t1 <= t0:
            self._timer.stop(); self._playing = False; self._play_btn.setText('▶'); return
        t = self._app.cursor_time + 0.033 * self._speed
        if t >= t1:
            t = t1; self._playing = False; self._timer.stop(); self._play_btn.setText('▶')
        self._app.set_cursor_time(t)
