"""
StatusBadge — circular status indicator.

Geometry derived from the Tara UAV logo badge circle. Used for
VERIFIED / NOMINAL / CAUTION / CRITICAL / UNVERIFIED / TAMPERED states.
"""
from __future__ import annotations
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRectF, pyqtProperty
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QFontMetrics

from ui.design.tokens import T


class StatusBadge(QWidget):
    """20px circular badge plus an optional text label to its right."""

    COLORS = {
        'VERIFIED':   T.brand.blue,
        'NOMINAL':    T.status.nominal,
        'CAUTION':    T.status.caution,
        'CRITICAL':   T.status.critical,
        'UNVERIFIED': T.text.muted,
        'TAMPERED':   T.status.critical,
        'LOADING':    T.brand.blue,
        'NO DATA':    T.text.muted,
        'NOT_LOADED': T.text.muted,
    }
    FILLED = {'VERIFIED', 'NOMINAL', 'CAUTION', 'CRITICAL'}
    BROKEN = {'TAMPERED'}

    def __init__(self, state: str = 'UNVERIFIED', label: str = '', parent=None):
        super().__init__(parent)
        self._state = state
        self._label = label
        self._glow_opacity = 0.0
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._update_size()

    def set_state(self, state: str, label: str | None = None):
        self._state = state
        if label is not None:
            self._label = label
        self._update_size()
        self.update()

    def _update_size(self):
        if self._label:
            fm = QFontMetrics(self._label_font())
            w = 20 + 8 + fm.horizontalAdvance(self._label)
        else:
            w = 20
        self.setFixedSize(int(w), 20)

    def _label_font(self) -> QFont:
        f = QFont(T.font.brand, T.size.sm)
        f.setWeight(T.weight.bold)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.6)
        return f

    # glow_opacity animatable property (used by verification animation later)
    def _get_glow(self) -> float:
        return self._glow_opacity

    def _set_glow(self, v: float):
        self._glow_opacity = v
        self.update()

    glow_opacity = pyqtProperty(float, _get_glow, _set_glow)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(self.COLORS.get(self._state, T.text.muted))
        badge = QRectF(0.75, 0.75, 18.5, 18.5)

        if self._glow_opacity > 0:
            g = QColor(color)
            g.setAlphaF(0.25 * self._glow_opacity)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(g))
            p.drawEllipse(badge.adjusted(-4, -4, 4, 4))

        fill = QColor(color)
        fill.setAlphaF(0.15 if self._state in self.FILLED else 0.0)
        p.setBrush(QBrush(fill))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(badge)

        p.setBrush(Qt.BrushStyle.NoBrush)
        ring_pen = QPen(color, 1.5)
        if self._state in ('UNVERIFIED', 'NO DATA', 'NOT_LOADED'):
            ring_pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(ring_pen)
        if self._state in self.BROKEN:
            # broken ring — 40 degree gap centred at 12 o'clock
            p.drawArc(badge, 110 * 16, 280 * 16)
        else:
            p.drawEllipse(badge)

        if self._state in self.FILLED:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(color))
            p.drawEllipse(QRectF(7, 7, 6, 6))

        if self._label:
            p.setPen(QPen(QColor(T.text.primary)))
            p.setFont(self._label_font())
            p.drawText(QRectF(28, 0, self.width() - 28, 20),
                       Qt.AlignmentFlag.AlignVCenter, self._label)
        p.end()
