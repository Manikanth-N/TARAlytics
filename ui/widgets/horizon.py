"""
ArtificialHorizon — attitude indicator driven by the shared cursor (P1.5 + P3).

Shows the aircraft's actual attitude (ATT.Roll/Pitch) as a classic sky/ground card
with a pitch ladder and bank pointer, the controller's desired attitude
(ATT.DesRoll/DesPitch) as a translucent ghost, **a fading motion trail of the last
10 s of attitude**, and a compact **actual-vs-desired history mini-plot** (last 10 s)
— so tracking and oscillation are visible over time, not just frozen at the instant.

Cursor-synced and (via the replay→shared-cursor wiring) animates during playback.
The history is read from the real flight data in the window [t−10, t], so it is the
actual last 10 s regardless of how the cursor got there. Pure QPainter.
"""
from __future__ import annotations
import math
import numpy as np

from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPainterPath, QPolygonF

from ui.design.tokens import T

_SKY = QColor('#1E6FA0')
_GROUND = QColor('#6B4A2A')
_GHOST = QColor('#FF3DBE')      # desired-attitude ghost (magenta flight-director hue)
_ACT = QColor(T.brand.blue_bright)
_PPD_DEG = 30                   # degrees of pitch visible across the radius
_HISTORY_S = 10.0               # seconds of trail / mini-plot
_TRAIL_N = 6                    # ghost horizon lines in the motion trail


class ArtificialHorizon(QWidget):
    def __init__(self, app_state, parent=None):
        super().__init__(parent)
        self._app = app_state
        self._roll = self._pitch = 0.0
        self._des_roll = self._des_pitch = None
        self._has = False
        # cached full-flight ATT arrays (for history windows)
        self._t = self._roll_h = self._pitch_h = None
        self._des_roll_h = self._des_pitch_h = None
        # current 10 s window slices
        self._win = None
        self.setMinimumSize(180, 220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        app_state.connect_cursor(self._on_cursor, 'ArtificialHorizon')
        app_state.data_changed.connect(self._on_data)

    def _on_data(self, _data):
        att = self._app.data.get('ATT')
        if att is not None and not att.empty and 'TimeS' in att.columns:
            t = att['TimeS'].to_numpy(float)
            order = np.argsort(t)
            self._t = t[order]
            self._roll_h = att['Roll'].to_numpy(float)[order] if 'Roll' in att else None
            self._pitch_h = att['Pitch'].to_numpy(float)[order] if 'Pitch' in att else None
            self._des_roll_h = att['DesRoll'].to_numpy(float)[order] if 'DesRoll' in att else None
            self._des_pitch_h = att['DesPitch'].to_numpy(float)[order] if 'DesPitch' in att else None
        else:
            self._t = None
        self._on_cursor(self._app.cursor_time)

    def _on_cursor(self, t: float):
        svc = self._app.sample_service
        if svc is None:
            self._has = False; self._win = None
            self.update(); return
        r = svc.value_at('ATT', 'Roll', t)
        p = svc.value_at('ATT', 'Pitch', t)
        self._has = r is not None and p is not None
        self._roll = r or 0.0
        self._pitch = p or 0.0
        self._des_roll = svc.value_at('ATT', 'DesRoll', t)
        self._des_pitch = svc.value_at('ATT', 'DesPitch', t)
        self._win = self._window(t)
        self.update()

    def _window(self, t: float):
        if self._t is None or self._roll_h is None:
            return None
        m = (self._t >= t - _HISTORY_S) & (self._t <= t)
        if np.count_nonzero(m) < 2:
            return None
        return {
            't': self._t[m], 'roll': self._roll_h[m], 'pitch': self._pitch_h[m],
            'des_roll': self._des_roll_h[m] if self._des_roll_h is not None else None,
            'des_pitch': self._des_pitch_h[m] if self._des_pitch_h is not None else None,
            't0': t - _HISTORY_S, 't1': t,
        }

    # ── painting ──────────────────────────────────────────────────────────────

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(T.surface.base))
        strip_h = max(54, int(h * 0.26))      # bottom history mini-plot
        ball_h = h - strip_h
        cx, cy = w / 2, ball_h / 2 + 4
        R = min(w, ball_h) / 2 - 10
        if R <= 10:
            p.end(); return
        ppd = R / _PPD_DEG

        if not self._has:
            p.setPen(QPen(QColor(T.text.muted)))
            p.setFont(QFont(T.font.brand, T.size.sm))
            p.drawText(QRectF(0, 0, w, ball_h), int(Qt.AlignmentFlag.AlignCenter),
                       'NO ATTITUDE DATA')
            self._draw_history(p, 0, ball_h, w, strip_h)
            p.end(); return

        circle = QPainterPath(); circle.addEllipse(QPointF(cx, cy), R, R)

        # motion trail: faint past horizon lines over the last 10 s
        if self._win is not None:
            self._draw_trail(p, circle, cx, cy, R, ppd)

        # moving card (actual)
        p.save(); p.setClipPath(circle); p.translate(cx, cy)
        p.rotate(-self._roll); p.translate(0, self._pitch * ppd)
        big = 3 * R
        p.fillRect(QRectF(-big, -big, 2 * big, big), _SKY)
        p.fillRect(QRectF(-big, 0, 2 * big, big), _GROUND)
        p.setPen(QPen(QColor('#EAF2F8'), 2)); p.drawLine(QPointF(-big, 0), QPointF(big, 0))
        p.setPen(QPen(QColor('#D5E2EE'), 1)); p.setFont(QFont(T.font.data, 8))
        for k in (-20, -10, 10, 20):
            y = -k * ppd; half = 22 if k % 20 == 0 else 14
            p.drawLine(QPointF(-half, y), QPointF(half, y))
            p.drawText(QRectF(half + 3, y - 7, 22, 14), int(Qt.AlignmentFlag.AlignLeft), str(abs(k)))
        p.restore()

        # desired ghost
        if self._des_roll is not None and self._des_pitch is not None:
            p.save(); p.setClipPath(circle); p.translate(cx, cy)
            p.rotate(-self._des_roll); p.translate(0, self._des_pitch * ppd)
            p.setPen(QPen(_GHOST, 2, Qt.PenStyle.DashLine)); p.drawLine(QPointF(-R, 0), QPointF(R, 0))
            p.restore()

        # bezel + fixed aircraft + bank pointer
        p.setPen(QPen(QColor(T.border.active), 2)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), R, R)
        p.setPen(QPen(QColor(T.status.caution), 3))
        p.drawLine(QPointF(cx - 30, cy), QPointF(cx - 10, cy))
        p.drawLine(QPointF(cx + 10, cy), QPointF(cx + 30, cy))
        p.setBrush(QColor(T.status.caution)); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), 3, 3)
        p.save(); p.translate(cx, cy); p.rotate(self._roll)
        tri = QPolygonF([QPointF(0, -R + 1), QPointF(-5, -R + 11), QPointF(5, -R + 11)])
        p.setBrush(QColor(T.status.caution)); p.setPen(Qt.PenStyle.NoPen); p.drawPolygon(tri)
        p.restore()

        self._draw_history(p, 0, ball_h, w, strip_h)
        p.end()

    def _draw_trail(self, p, circle, cx, cy, R, ppd):
        win = self._win
        n = win['roll'].size
        if n < 2:
            return
        idx = np.linspace(0, n - 1, min(_TRAIL_N, n)).astype(int)
        p.save(); p.setClipPath(circle)
        for j, i in enumerate(idx[:-1]):       # oldest..recent, skip the newest (drawn solid)
            age = j / max(len(idx) - 1, 1)
            col = QColor('#EAF2F8'); col.setAlphaF(0.08 + 0.10 * age)
            p.save(); p.translate(cx, cy)
            p.rotate(-float(win['roll'][i])); p.translate(0, float(win['pitch'][i]) * ppd)
            p.setPen(QPen(col, 1)); p.drawLine(QPointF(-R, 0), QPointF(R, 0))
            p.restore()
        p.restore()

    def _draw_history(self, p, x, y, w, h):
        """Actual-vs-desired roll & pitch over the last 10 s (two stacked lanes)."""
        p.setPen(QPen(QColor(T.border.subtle), 1))
        p.drawLine(QPointF(x + 6, y), QPointF(x + w - 6, y))
        p.setFont(QFont(T.font.brand, T.size.xs))
        p.setPen(QPen(QColor(T.text.muted)))
        p.drawText(QRectF(x + 8, y + 1, w, 12), int(Qt.AlignmentFlag.AlignLeft),
                   'ATTITUDE — LAST 10 s   (actual / ┄ desired)')
        win = self._win
        if win is None:
            return
        lane_h = (h - 16) / 2
        self._lane(p, x + 6, y + 14, w - 12, lane_h, win, 'roll', 'des_roll', 'R')
        self._lane(p, x + 6, y + 14 + lane_h, w - 12, lane_h, win, 'pitch', 'des_pitch', 'P')

    def _lane(self, p, x, y, w, h, win, act_key, des_key, label):
        t = win['t']; a = win[act_key]; d = win.get(des_key)
        vals = [a] + ([d] if d is not None else [])
        lo = min(float(np.min(v)) for v in vals)
        hi = max(float(np.max(v)) for v in vals)
        rng = max(hi - lo, 4.0)
        lo -= rng * 0.1; hi += rng * 0.1; rng = hi - lo
        t0, t1 = win['t0'], win['t1']
        tw = max(t1 - t0, 1e-3)

        def px(tt): return x + (tt - t0) / tw * w
        def py(vv): return y + h - (vv - lo) / rng * (h - 4) - 2

        # zero line
        if lo < 0 < hi:
            p.setPen(QPen(QColor(T.border.subtle), 1, Qt.PenStyle.DotLine))
            p.drawLine(QPointF(x, py(0)), QPointF(x + w, py(0)))
        if d is not None:
            self._poly(p, t, d, px, py, QPen(_GHOST, 1, Qt.PenStyle.DashLine))
        self._poly(p, t, a, px, py, QPen(_ACT, 1.4))
        p.setPen(QPen(QColor(T.text.muted))); p.setFont(QFont(T.font.brand, T.size.xs))
        p.drawText(QRectF(x + 2, y, 14, 12), int(Qt.AlignmentFlag.AlignLeft), label)

    @staticmethod
    def _poly(p, t, v, px, py, pen):
        path = QPainterPath(); started = False
        for tt, vv in zip(t, v):
            if not np.isfinite(vv):
                continue
            xx, yy = px(float(tt)), py(float(vv))
            if not started:
                path.moveTo(xx, yy); started = True
            else:
                path.lineTo(xx, yy)
        if started:
            p.setPen(pen); p.drawPath(path)
