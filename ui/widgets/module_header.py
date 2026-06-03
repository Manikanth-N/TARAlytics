"""ModuleHeader — consistent 40px section header used atop every module."""
from __future__ import annotations
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QSizePolicy
from PyQt6.QtGui import QPainter, QColor, QPen, QFont
from PyQt6.QtCore import Qt

from ui.design.tokens import T


class ModuleHeader(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(T.layout.module_header_height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(T.spacing.px16, 0, T.spacing.px16, 0)
        layout.setSpacing(T.spacing.px8)

        self._title_label = QLabel(title.upper())
        font = QFont(T.font.brand, T.size.md)
        font.setWeight(T.weight.bold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.8)
        self._title_label.setFont(font)
        self._title_label.setStyleSheet(f'color: {T.text.secondary};')

        self._actions = QHBoxLayout()
        self._actions.setSpacing(T.spacing.px8)

        layout.addWidget(self._title_label)
        layout.addStretch()
        layout.addLayout(self._actions)

    def add_action(self, widget: QWidget):
        self._actions.addWidget(widget)

    def paintEvent(self, _):
        p = QPainter(self)
        r = self.rect()
        p.fillRect(r, QColor(T.surface.elevated))
        top = QColor(T.brand.blue)
        top.setAlphaF(0.12)
        p.setPen(QPen(top, 1))
        p.drawLine(r.left(), r.top(), r.right(), r.top())
        p.setPen(QPen(QColor(T.border.default), 1))
        p.drawLine(r.left(), r.bottom(), r.right(), r.bottom())
        p.end()
