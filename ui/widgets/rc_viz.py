"""
RCVisualization — pilot stick visualization driven by the shared cursor (P1.5).

Two Mode-2 stick boxes:
  left  = Yaw (X) / Throttle (Y)
  right = Roll (X) / Pitch (Y)
The filled dot is pilot input (RCIN, semantic via RCModel); the hollow ghost is the
servo/motor output (RCOU) for the same axis, so pilot-vs-output is visible at a
glance. Four labelled value rows back the sticks. Cursor-synced; pure QPainter.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont

from ui.design.tokens import T

_PILOT = QColor(T.brand.blue_bright)
_OUTPUT = QColor(T.status.caution)


class RCVisualization(QWidget):
    def __init__(self, app_state, parent=None):
        super().__init__(parent)
        self._app = app_state
        self._pilot = None     # StickState
        self._servo = None
        self.setMinimumSize(220, 160)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        app_state.connect_cursor(self._on_cursor, 'RCVisualization')
        app_state.data_changed.connect(lambda *_: self._on_cursor(app_state.cursor_time))

    def _on_cursor(self, t: float):
        svc = self._app.sample_service
        rc = self._app.rc_model
        if svc is None or rc is None:
            self._pilot = self._servo = None
        else:
            self._pilot = rc.pilot_input(svc, t)
            self._servo = rc.servo_output(svc, t)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(T.surface.base))
        w, h = self.width(), self.height()

        box = min((w - 36) / 2, h - 52)
        if box < 40:
            p.end(); return
        gap = 12
        total = box * 2 + gap
        x0 = (w - total) / 2
        y0 = 8
        left = QRectF(x0, y0, box, box)
        right = QRectF(x0 + box + gap, y0, box, box)

        pv = self._pilot.as_dict() if self._pilot is not None else {}
        sv = self._servo.as_dict() if self._servo is not None else {}

        # left stick: X=yaw(-1..1), Y=throttle(0..1, bottom..top)
        self._draw_box(p, left, 'YAW', 'THR')
        self._draw_marker(p, left, pv.get('yaw'), pv.get('throttle'), _PILOT, filled=True,
                          y_is_throttle=True)
        self._draw_marker(p, left, sv.get('yaw'), sv.get('throttle'), _OUTPUT, filled=False,
                          y_is_throttle=True)
        # right stick: X=roll(-1..1), Y=pitch(-1..1, up=+pitch)
        self._draw_box(p, right, 'ROLL', 'PITCH')
        self._draw_marker(p, right, pv.get('roll'), pv.get('pitch'), _PILOT, filled=True,
                          y_is_throttle=False)
        self._draw_marker(p, right, sv.get('roll'), sv.get('pitch'), _OUTPUT, filled=False,
                          y_is_throttle=False)

        # value rows
        p.setFont(QFont(T.font.data, T.size.xs))
        rows = [('Roll', 'roll', '{:+.2f}'), ('Pitch', 'pitch', '{:+.2f}'),
                ('Yaw', 'yaw', '{:+.2f}'), ('Throttle', 'throttle', '{:.2f}')]
        ry = y0 + box + 6
        cw = w / 2
        for i, (label, key, fmt) in enumerate(rows):
            cx = 8 + (i % 2) * cw
            yy = ry + (i // 2) * 15
            pvk = pv.get(key); svk = sv.get(key)
            txt = f'{label:<8} ' + ('—' if pvk is None else fmt.format(pvk))
            p.setPen(QPen(QColor(T.text.secondary)))
            p.drawText(QRectF(cx, yy, cw - 12, 14),
                       int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), txt)
            if svk is not None:
                p.setPen(QPen(_OUTPUT))
                p.drawText(QRectF(cx, yy, cw - 14, 14),
                           int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                           fmt.format(svk))
        # legend
        p.setFont(QFont(T.font.brand, T.size.xs))
        p.setPen(QPen(_PILOT)); p.drawText(QRectF(8, h - 14, 80, 12),
                                           int(Qt.AlignmentFlag.AlignLeft), '● pilot')
        p.setPen(QPen(_OUTPUT)); p.drawText(QRectF(70, h - 14, 90, 12),
                                            int(Qt.AlignmentFlag.AlignLeft), '○ output')
        p.end()

    def _draw_box(self, p, rect: QRectF, xlabel: str, ylabel: str):
        p.setBrush(QColor(T.surface.panel))
        p.setPen(QPen(QColor(T.border.default), 1))
        p.drawRoundedRect(rect, 4, 4)
        p.setPen(QPen(QColor(T.border.subtle), 1, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(rect.center().x(), rect.top()), QPointF(rect.center().x(), rect.bottom()))
        p.drawLine(QPointF(rect.left(), rect.center().y()), QPointF(rect.right(), rect.center().y()))
        p.setPen(QPen(QColor(T.text.muted)))
        p.setFont(QFont(T.font.brand, T.size.xs))
        p.drawText(rect.adjusted(2, 0, -2, -2),
                   int(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter), xlabel)
        p.save(); p.translate(rect.left() + 8, rect.center().y()); p.rotate(-90)
        p.drawText(QRectF(-30, -8, 60, 14), int(Qt.AlignmentFlag.AlignCenter), ylabel)
        p.restore()

    def _draw_marker(self, p, rect: QRectF, x, y, colour, filled: bool, y_is_throttle: bool):
        if x is None or y is None:
            return
        px = rect.center().x() + max(-1.0, min(1.0, x)) * (rect.width() / 2 - 6)
        if y_is_throttle:
            py = rect.bottom() - 4 - max(0.0, min(1.0, y)) * (rect.height() - 8)
        else:
            py = rect.center().y() - max(-1.0, min(1.0, y)) * (rect.height() / 2 - 6)
        r = 6
        if filled:
            p.setBrush(QBrush(colour)); p.setPen(QPen(QColor(T.surface.base), 1))
        else:
            p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(colour, 2))
        p.drawEllipse(QPointF(px, py), r, r)
