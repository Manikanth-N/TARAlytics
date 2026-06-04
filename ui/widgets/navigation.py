"""
NavigationRail — left-edge module switcher.

64px wide (Sprint-1 adjustment from 48px). Each item shows an icon glyph and
a short label; the active item carries a brand-blue left bar derived from the
eagle-beak direction cue.
"""
from __future__ import annotations
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSizePolicy
from PyQt6.QtCore import pyqtSignal, Qt, QRect
from PyQt6.QtGui import QPainter, QColor, QPen, QFont

from ui.design.tokens import T

# Icon glyphs chosen for broad font coverage. (label -> glyph)
_ICONS = {
    'DEBRIEF':  '⊞',
    'TIMELINE': '⊟',
    'SIGNALS':  '∿',
    'REPLAY':   '▶',
    'VERIFY':   '⬡',
    'MAP':      '◎',
}


class NavItem(QWidget):
    clicked = pyqtSignal(int)

    def __init__(self, index: int, label: str, parent=None):
        super().__init__(parent)
        self._index  = index
        self._label  = label
        self._icon   = _ICONS.get(label, '○')
        self._active = False
        self._hover  = False
        self.setFixedSize(T.layout.nav_rail_width, 56)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(label)

    def set_active(self, active: bool):
        self._active = active
        self.update()

    def enterEvent(self, _): self._hover = True;  self.update()
    def leaveEvent(self, _): self._hover = False; self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._index)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        if self._hover and not self._active:
            bg = QColor(T.brand.blue); bg.setAlphaF(0.08)
            p.fillRect(self.rect(), bg)
        if self._active:
            bg = QColor(T.brand.blue); bg.setAlphaF(0.10)
            p.fillRect(self.rect(), bg)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(T.brand.blue))
            p.drawRect(QRect(0, 12, 3, h - 24))

        icon_color = T.brand.blue if self._active else T.text.secondary
        p.setPen(QPen(QColor(icon_color)))
        p.setFont(QFont('Segoe UI Symbol', T.size.lg))
        p.drawText(QRect(0, 6, w, 28), Qt.AlignmentFlag.AlignCenter, self._icon)

        label_color = T.text.primary if self._active else T.text.muted
        p.setPen(QPen(QColor(label_color)))
        lf = QFont(T.font.brand, 9); lf.setWeight(T.weight.semibold)
        p.setFont(lf)
        p.drawText(QRect(0, 34, w, 16), Qt.AlignmentFlag.AlignCenter, self._label)
        p.end()


class NavigationRail(QWidget):
    module_requested = pyqtSignal(int)

    def __init__(self, items: list[str], parent=None):
        """items: ordered list of labels matching QStackedWidget indices."""
        super().__init__(parent)
        self._items: list[NavItem] = []
        self.setFixedWidth(T.layout.nav_rail_width)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, T.spacing.px16, 0, T.spacing.px16)
        layout.setSpacing(4)

        for i, label in enumerate(items):
            item = NavItem(i, label)
            item.clicked.connect(self._on_clicked)
            self._items.append(item)
            layout.addWidget(item)
        layout.addStretch()

    def _on_clicked(self, index: int):
        self.set_active(index)
        self.module_requested.emit(index)

    def set_active(self, index: int):
        for i, item in enumerate(self._items):
            item.set_active(i == index)

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(T.surface.panel))
        p.setPen(QPen(QColor(T.border.subtle), 1))
        p.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
        p.end()
