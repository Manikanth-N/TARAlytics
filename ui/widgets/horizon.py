"""
ArtificialHorizon — attitude indicator driven by the shared cursor (P1.5).

Shows the aircraft's actual attitude (ATT.Roll/Pitch) as a classic sky/ground card
with a pitch ladder and bank pointer, and overlays the controller's desired attitude
(ATT.DesRoll/DesPitch) as a translucent "ghost" horizon — so demand-vs-response is
visible as a gap between the card and the ghost, without opening a plot.

Cursor-synced: redraws on AppState.cursor_time_changed. Pure QPainter.
"""
from __future__ import annotations
import math

from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPainterPath, QPolygonF

from ui.design.tokens import T

_SKY = QColor('#1E6FA0')
_GROUND = QColor('#6B4A2A')
_GHOST = QColor('#FF3DBE')      # desired-attitude ghost (magenta flight-director hue)
_PPD_DEG = 30                   # degrees of pitch visible across the radius


class ArtificialHorizon(QWidget):
    def __init__(self, app_state, parent=None):
        super().__init__(parent)
        self._app = app_state
        self._roll = self._pitch = 0.0
        self._des_roll = self._des_pitch = None
        self._has = False
        self.setMinimumSize(180, 180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        app_state.connect_cursor(self._on_cursor, 'ArtificialHorizon')
        app_state.data_changed.connect(lambda *_: self._on_cursor(app_state.cursor_time))

    def _on_cursor(self, t: float):
        svc = self._app.sample_service
        if svc is None:
            self._has = False
            self.update(); return
        r = svc.value_at('ATT', 'Roll', t)
        p = svc.value_at('ATT', 'Pitch', t)
        self._has = r is not None and p is not None
        self._roll = r or 0.0
        self._pitch = p or 0.0
        self._des_roll = svc.value_at('ATT', 'DesRoll', t)
        self._des_pitch = svc.value_at('ATT', 'DesPitch', t)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(T.surface.base))
        cx, cy = w / 2, h / 2
        R = min(w, h) / 2 - 10
        if R <= 0:
            p.end(); return
        ppd = R / _PPD_DEG

        circle = QPainterPath()
        circle.addEllipse(QPointF(cx, cy), R, R)

        if not self._has:
            p.setPen(QPen(QColor(T.text.muted)))
            p.setFont(QFont(T.font.brand, T.size.sm))
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), 'NO ATTITUDE DATA')
            p.end(); return

        # ── moving card: sky / ground / horizon / pitch ladder (actual) ──
        p.save()
        p.setClipPath(circle)
        p.translate(cx, cy)
        p.rotate(-self._roll)
        p.translate(0, self._pitch * ppd)
        big = 3 * R
        p.fillRect(QRectF(-big, -big, 2 * big, big), _SKY)
        p.fillRect(QRectF(-big, 0, 2 * big, big), _GROUND)
        p.setPen(QPen(QColor('#EAF2F8'), 2))
        p.drawLine(QPointF(-big, 0), QPointF(big, 0))
        # pitch ladder
        p.setPen(QPen(QColor('#D5E2EE'), 1))
        p.setFont(QFont(T.font.data, 8))
        for k in (-30, -20, -10, 10, 20, 30):
            y = -k * ppd
            half = 26 if k % 20 == 0 else 16
            p.drawLine(QPointF(-half, y), QPointF(half, y))
            p.drawText(QRectF(half + 3, y - 7, 26, 14),
                       int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), str(abs(k)))
            p.drawText(QRectF(-half - 29, y - 7, 26, 14),
                       int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), str(abs(k)))
        p.restore()

        # ── desired-attitude ghost horizon ──
        if self._des_roll is not None and self._des_pitch is not None:
            p.save()
            p.setClipPath(circle)
            p.translate(cx, cy)
            p.rotate(-self._des_roll)
            p.translate(0, self._des_pitch * ppd)
            pen = QPen(_GHOST, 2, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawLine(QPointF(-R, 0), QPointF(R, 0))
            # ghost wing markers
            p.setPen(QPen(_GHOST, 2))
            p.drawLine(QPointF(-22, 0), QPointF(-10, 0))
            p.drawLine(QPointF(10, 0), QPointF(22, 0))
            p.restore()

        # ── instrument bezel ──
        p.setPen(QPen(QColor(T.border.active), 2)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), R, R)

        # ── fixed aircraft reference (actual) ──
        p.setPen(QPen(QColor(T.status.caution), 3))
        p.drawLine(QPointF(cx - 34, cy), QPointF(cx - 12, cy))
        p.drawLine(QPointF(cx + 12, cy), QPointF(cx + 34, cy))
        p.setBrush(QColor(T.status.caution)); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), 3, 3)

        # ── bank pointer (roll) at top ──
        p.save()
        p.translate(cx, cy)
        p.setPen(QPen(QColor('#EAF2F8'), 1))
        for ang in (-60, -30, -20, -10, 0, 10, 20, 30, 60):
            a = math.radians(ang - 90)
            r2 = R
            r1 = R - (9 if ang % 30 == 0 else 5)
            p.drawLine(QPointF(r1 * math.cos(a), r1 * math.sin(a)),
                       QPointF(r2 * math.cos(a), r2 * math.sin(a)))
        # roll triangle
        p.rotate(self._roll)
        tri = QPolygonF([QPointF(0, -R + 1), QPointF(-6, -R + 12), QPointF(6, -R + 12)])
        p.setBrush(QColor(T.status.caution)); p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(tri)
        p.restore()

        # ── numeric readouts ──
        p.setFont(QFont(T.font.data, T.size.xs))
        p.setPen(QPen(QColor(T.text.data)))
        p.drawText(QRectF(6, h - 34, w - 12, 14), int(Qt.AlignmentFlag.AlignLeft),
                   f'ROLL  {self._roll:+.1f}°' +
                   (f'  (dem {self._des_roll:+.1f}°)' if self._des_roll is not None else ''))
        p.drawText(QRectF(6, h - 18, w - 12, 14), int(Qt.AlignmentFlag.AlignLeft),
                   f'PITCH {self._pitch:+.1f}°' +
                   (f'  (dem {self._des_pitch:+.1f}°)' if self._des_pitch is not None else ''))
        p.setPen(QPen(_GHOST))
        p.drawText(QRectF(6, 6, w - 12, 14), int(Qt.AlignmentFlag.AlignRight), '┄ desired')
        p.end()
