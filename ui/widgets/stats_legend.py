import numpy as np
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QFrame, QScrollArea, QVBoxLayout, QSizePolicy
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter


class ColorSwatch(QWidget):
    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self.setFixedSize(14, 14)
        self._color = QColor(color)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setBrush(self._color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(self.rect())
        p.end()

    def set_color(self, color: str):
        self._color = QColor(color)
        self.update()


class SignalStatRow(QWidget):
    def __init__(self, key: str, color: str, parent=None):
        super().__init__(parent)
        self._key = key
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        self._swatch = ColorSwatch(color)
        layout.addWidget(self._swatch)

        self._name_lbl = QLabel(key)
        self._name_lbl.setStyleSheet('font-weight: bold; font-size: 11px;')
        self._name_lbl.setMinimumWidth(160)
        layout.addWidget(self._name_lbl)

        sep = QLabel('|')
        sep.setStyleSheet('color: #adb5bd;')
        layout.addWidget(sep)

        self._stats_lbl = QLabel('— no data in view')
        self._stats_lbl.setStyleSheet('font-size: 11px; font-family: monospace;')
        layout.addWidget(self._stats_lbl, 1)

    def update_stats(self, values: np.ndarray):
        if values is None or len(values) == 0:
            self._stats_lbl.setText('— no data in view')
            return
        arr = values[~np.isnan(values)]
        if len(arr) == 0:
            self._stats_lbl.setText('— no data in view')
            return
        mn   = float(np.min(arr))
        mx   = float(np.max(arr))
        mean = float(np.mean(arr))
        std  = float(np.std(arr))
        n    = len(arr)
        self._stats_lbl.setText(
            f'Min: {mn:.3f}  |  Max: {mx:.3f}  |  Mean: {mean:.3f}  |  Std: {std:.3f}  |  N: {n}'
        )

    def set_color(self, color: str):
        self._swatch.set_color(color)


class StatsLegend(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMaximumHeight(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.setStyleSheet('background: #1e1e2e;')

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet('QScrollArea { border: none; }')

        inner = QWidget()
        self._inner_layout = QVBoxLayout(inner)
        self._inner_layout.setContentsMargins(0, 0, 0, 0)
        self._inner_layout.setSpacing(0)
        self._inner_layout.addStretch(1)
        scroll.setWidget(inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self._rows: dict[str, SignalStatRow] = {}

    def add_signal(self, key: str, color: str):
        if key in self._rows:
            return
        row = SignalStatRow(key, color)
        self._rows[key] = row
        layout = self._inner_layout
        layout.insertWidget(layout.count() - 1, row)

    def remove_signal(self, key: str):
        row = self._rows.pop(key, None)
        if row:
            self._inner_layout.removeWidget(row)
            row.deleteLater()

    def update_signal_stats(self, key: str, values: np.ndarray):
        row = self._rows.get(key)
        if row:
            row.update_stats(values)

    def update_color(self, key: str, color: str):
        row = self._rows.get(key)
        if row:
            row.set_color(color)

    def clear(self):
        for key in list(self._rows.keys()):
            self.remove_signal(key)
