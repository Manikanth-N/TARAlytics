"""NoLogState — shown in the main canvas when no log is loaded."""
from __future__ import annotations
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QFont

from ui.design.tokens import T


class NoLogState(QWidget):
    open_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(T.spacing.px16)

        msg = QLabel('NO FLIGHT DATA LOADED')
        f = QFont(T.font.brand, T.size.md); f.setWeight(T.weight.bold)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.0)
        msg.setFont(f)
        msg.setStyleSheet(f'color: {T.text.muted};')
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)

        sub = QLabel('Use “Open Log” in the header, then Parse.')
        sub.setStyleSheet(f'color: {T.text.muted}; font-size: {T.size.sm}px;')
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)

        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._open_btn = QPushButton('Open Log File')
        self._open_btn.setProperty('role', 'primary')
        self._open_btn.setFixedWidth(140)
        self._open_btn.clicked.connect(self.open_requested)
        btn_row.addWidget(self._open_btn)

        layout.addWidget(msg)
        layout.addWidget(sub)
        layout.addLayout(btn_row)

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(T.surface.base))
        p.end()
