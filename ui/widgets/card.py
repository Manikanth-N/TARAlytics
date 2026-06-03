"""
Card widgets for the Debrief module.

MetricCard — large number + unit + description (flight profile stats).
HealthCard — system name + status badge + key metrics + drill-down link.
"""
from __future__ import annotations
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QFont

from ui.design.tokens import T
from ui.widgets.badge import StatusBadge


def _card_border(p: QPainter, r):
    """Shared card edge treatment: blue top highlight, dark bottom, subtle frame."""
    top = QColor(T.brand.blue); top.setAlphaF(0.08)
    bot = QColor('#000000');    bot.setAlphaF(0.35)
    p.setPen(QPen(top, 1)); p.drawLine(r.left(), r.top(), r.right(), r.top())
    p.setPen(QPen(bot, 1)); p.drawLine(r.left(), r.bottom(), r.right(), r.bottom())
    p.setPen(QPen(QColor(T.border.subtle), 1))
    p.drawRect(r.adjusted(0, 0, -1, -1))


class MetricCard(QWidget):
    def __init__(self, description: str, parent=None):
        super().__init__(parent)
        self.setMinimumSize(96, 64)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(T.spacing.px12, T.spacing.px8,
                                  T.spacing.px12, T.spacing.px8)
        layout.setSpacing(2)

        self._value = QLabel('—')
        vf = QFont(T.font.brand, T.size.x2l); vf.setWeight(T.weight.bold)
        self._value.setFont(vf)
        self._value.setStyleSheet(f'color: {T.text.primary};')

        self._unit = QLabel('')
        self._unit.setStyleSheet(f'color: {T.text.secondary}; font-size: {T.size.xs}px;')
        self._unit.setVisible(False)

        self._desc = QLabel(description.upper())
        df = QFont(T.font.brand, T.size.xs); df.setWeight(T.weight.semibold)
        df.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.6)
        self._desc.setFont(df)
        self._desc.setStyleSheet(f'color: {T.text.muted};')

        layout.addWidget(self._value)
        layout.addWidget(self._unit)
        layout.addStretch()
        layout.addWidget(self._desc)

    def set_value(self, value: str, unit: str = ''):
        self._value.setText(value)
        self._unit.setText(unit)
        self._unit.setVisible(bool(unit))

    def paintEvent(self, _):
        p = QPainter(self)
        r = self.rect()
        p.fillRect(r, QColor(T.surface.card))
        _card_border(p, r)
        p.end()


class HealthCard(QWidget):
    drill_down_requested = pyqtSignal(str)

    def __init__(self, system_name: str, parent=None):
        super().__init__(parent)
        self._system = system_name
        self._status = 'NO DATA'
        self.setMinimumSize(180, 104)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(T.spacing.px12, T.spacing.px12,
                                  T.spacing.px12, T.spacing.px12)
        layout.setSpacing(T.spacing.px8)

        header = QHBoxLayout()
        name = QLabel(system_name.upper())
        nf = QFont(T.font.brand, T.size.sm); nf.setWeight(T.weight.bold)
        nf.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.6)
        name.setFont(nf)
        name.setStyleSheet(f'color: {T.text.secondary};')
        self._badge = StatusBadge('NO DATA', 'NO DATA')
        header.addWidget(name)
        header.addStretch()
        header.addWidget(self._badge)

        self._metrics = QVBoxLayout()
        self._metrics.setSpacing(3)

        self._link = QLabel('VIEW SIGNALS →')
        lf = QFont(T.font.brand, T.size.xs); lf.setWeight(T.weight.semibold)
        self._link.setFont(lf)
        self._link.setStyleSheet(f'color: {T.brand.blue};')
        self._link.setCursor(Qt.CursorShape.PointingHandCursor)

        layout.addLayout(header)
        layout.addLayout(self._metrics)
        layout.addStretch()
        layout.addWidget(self._link)

    def set_status(self, state: str, label: str | None = None):
        self._status = state
        self._badge.set_state(state, label or state)
        self.update()

    def add_metric(self, key: str, value: str, unit: str = ''):
        row = QHBoxLayout()
        k = QLabel(key)
        k.setStyleSheet(f'color: {T.text.muted}; font-size: {T.size.xs}px;')
        v = QLabel(value)
        v.setFont(QFont(T.font.data, T.size.sm))
        v.setStyleSheet(f'color: {T.text.data};')
        u = QLabel(unit)
        u.setStyleSheet(f'color: {T.text.muted}; font-size: {T.size.xs}px;')
        row.addWidget(k); row.addStretch(); row.addWidget(v)
        if unit:
            row.addWidget(u)
        self._metrics.addLayout(row)

    def clear_metrics(self):
        while self._metrics.count():
            item = self._metrics.takeAt(0)
            if item.layout():
                self._clear_layout(item.layout())
            elif item.widget():
                item.widget().deleteLater()

    @staticmethod
    def _clear_layout(layout):
        while layout.count():
            it = layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and self._link.geometry().contains(ev.pos()):
            self.drill_down_requested.emit(self._system)
        super().mousePressEvent(ev)

    def paintEvent(self, _):
        p = QPainter(self)
        r = self.rect()
        p.fillRect(r, QColor(T.surface.card))
        if self._status == 'CAUTION':
            side = QColor(T.status.caution); side.setAlphaF(0.7)
            p.fillRect(0, 0, 3, r.height(), side)
        elif self._status == 'CRITICAL':
            side = QColor(T.status.critical); side.setAlphaF(0.7)
            p.fillRect(0, 0, 3, r.height(), side)
        _card_border(p, r)
        p.end()
