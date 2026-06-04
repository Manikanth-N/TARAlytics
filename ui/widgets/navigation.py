"""
NavigationRail — left-edge module switcher.

64px wide. Each item shows an icon glyph and a short label; the active item carries a
brand-blue left bar. The rail shows an ordered *subset* of modules (visibility is
user-configurable) — each item carries its target page index, so filtering/reordering
the rail never mis-routes a click. A gear button is pinned to the footer to open the
Module Visibility manager.
"""
from __future__ import annotations
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSizePolicy
from PyQt6.QtCore import pyqtSignal, Qt, QRect
from PyQt6.QtGui import QPainter, QColor, QPen, QFont

from ui.design.tokens import T

# Icon glyphs chosen for broad font coverage. (label -> glyph)
_ICONS = {
    'DEBRIEF':   '⊞',
    'TIMELINE':  '⊟',
    'EVENTS':    '⚑',
    'SITUATION': '✈',
    'SIGNALS':   '∿',
    'REPLAY':    '▶',
    'VERIFY':    '⬡',
    'MAP':       '◎',
    'EVIDENCE':  '🗎',
    'WORKSPACE': '▦',
    'CUSTOMIZE': '⚙',
}


class NavItem(QWidget):
    # Emits the target *page index* (not the item's position in the rail).
    clicked = pyqtSignal(int)

    def __init__(self, page_index: int, label: str, parent=None):
        super().__init__(parent)
        self._page_index = page_index
        self._label  = label
        self._icon   = _ICONS.get(label, '○')
        self._active = False
        self._hover  = False
        self.setFixedSize(T.layout.nav_rail_width, 56)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(label)

    @property
    def page_index(self) -> int:
        return self._page_index

    def set_active(self, active: bool):
        self._active = active
        self.update()

    def enterEvent(self, _): self._hover = True;  self.update()
    def leaveEvent(self, _): self._hover = False; self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._page_index)

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


class GearItem(NavItem):
    """Footer gear that opens the Module Visibility manager (not a module page)."""
    customize = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(-1, 'CUSTOMIZE', parent)
        self.setToolTip('Customize navigation — show/hide modules')

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.customize.emit()


class NavigationRail(QWidget):
    module_requested    = pyqtSignal(int)   # page index
    customize_requested = pyqtSignal()

    def __init__(self, modules: list | None = None, parent=None):
        """modules: ordered list of (page_index, label) to display."""
        super().__init__(parent)
        self._items: list[NavItem] = []
        self._active_page = -1
        self.setFixedWidth(T.layout.nav_rail_width)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, T.spacing.px16, 0, T.spacing.px16)
        self._layout.setSpacing(4)
        self._layout.addStretch()                 # pushes the gear to the footer

        self._gear = GearItem()
        self._gear.customize.connect(self.customize_requested)
        self._layout.addWidget(self._gear, 0, Qt.AlignmentFlag.AlignBottom)

        if modules:
            self.set_modules(modules)

    def set_modules(self, modules: list):
        """Rebuild the rail from an ordered list of (page_index, label). No gaps and
        no disabled items — only the requested modules are created."""
        for item in self._items:
            self._layout.removeWidget(item)
            item.setParent(None)
            item.deleteLater()
        self._items = []
        # Insert above the stretch (which sits just before the gear).
        for pos, (page_index, label) in enumerate(modules):
            item = NavItem(page_index, label)
            item.clicked.connect(self.module_requested)
            self._layout.insertWidget(pos, item)
            self._items.append(item)
        self.set_active(self._active_page)

    def visible_pages(self) -> list:
        return [it.page_index for it in self._items]

    def set_active(self, page_index: int):
        self._active_page = page_index
        for item in self._items:
            item.set_active(item.page_index == page_index)

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(T.surface.panel))
        p.setPen(QPen(QColor(T.border.subtle), 1))
        p.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
        p.end()
