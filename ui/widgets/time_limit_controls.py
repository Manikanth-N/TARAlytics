from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QDoubleSpinBox,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush


class DualHandleSlider(QWidget):
    range_changed = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._min = 0.0
        self._max = 1.0
        self._lo  = 0.0
        self._hi  = 1.0
        self._drag = None
        self.setFixedHeight(22)
        self.setMinimumWidth(200)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_bounds(self, mn: float, mx: float):
        self._min, self._max = mn, mx
        self._lo, self._hi = mn, mx
        self.update()

    def set_range(self, lo: float, hi: float):
        span = max(self._max - self._min, 1e-9)
        self._lo = max(self._min, min(lo, self._max))
        self._hi = max(self._min, min(hi, self._max))
        self.update()

    def _val_to_px(self, v: float) -> int:
        span = max(self._max - self._min, 1e-9)
        return int(10 + (v - self._min) / span * (self.width() - 20))

    def _px_to_val(self, x: int) -> float:
        t = max(0.0, min(1.0, (x - 10) / max(self.width() - 20, 1)))
        return self._min + t * (self._max - self._min)

    def paintEvent(self, _):
        w, h = self.width(), self.height()
        if w < 20 or h < 10:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        mid = h // 2

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor('#343a40'))
        p.drawRoundedRect(10, mid - 3, w - 20, 6, 3, 3)

        x0 = self._val_to_px(self._lo)
        x1 = self._val_to_px(self._hi)
        p.setBrush(QColor('#0d6efd'))
        p.drawRect(x0, mid - 3, max(x1 - x0, 0), 6)

        p.setBrush(QColor('#ffffff'))
        p.setPen(QPen(QColor('#0d6efd'), 2))
        for x in (x0, x1):
            p.drawEllipse(x - 7, mid - 7, 14, 14)
        p.end()

    def mousePressEvent(self, ev):
        x = int(ev.position().x())
        x0 = self._val_to_px(self._lo)
        x1 = self._val_to_px(self._hi)
        self._drag = 'lo' if abs(x - x0) <= abs(x - x1) else 'hi'

    def mouseMoveEvent(self, ev):
        if not self._drag:
            return
        v = self._px_to_val(int(ev.position().x()))
        eps = (self._max - self._min) * 1e-5
        if self._drag == 'lo':
            self._lo = max(self._min, min(v, self._hi - eps))
        else:
            self._hi = min(self._max, max(v, self._lo + eps))
        self.update()
        self.range_changed.emit(self._lo, self._hi)

    def mouseReleaseEvent(self, _):
        self._drag = None


class TimeLimitControls(QWidget):
    range_changed = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._t_min = 0.0
        self._t_max = 1.0
        self._blocking = False
        self.setStyleSheet('background: #1e1e2e; color: #e0e0e0;')

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        row = QHBoxLayout()
        row.setSpacing(6)

        row.addWidget(QLabel('Time Range:'))

        row.addWidget(QLabel('Start:'))
        self._spin_start = QDoubleSpinBox()
        self._spin_start.setDecimals(2)
        self._spin_start.setSingleStep(0.1)
        self._spin_start.setFixedWidth(80)
        self._spin_start.setStyleSheet(
            'QDoubleSpinBox { background: #2a2a3e; color: #e0e0e0; '
            'border: 1px solid #495057; border-radius: 3px; padding: 2px; }'
        )
        row.addWidget(self._spin_start)
        row.addWidget(QLabel('s'))

        row.addWidget(QLabel('End:'))
        self._spin_end = QDoubleSpinBox()
        self._spin_end.setDecimals(2)
        self._spin_end.setSingleStep(0.1)
        self._spin_end.setFixedWidth(80)
        self._spin_end.setStyleSheet(self._spin_start.styleSheet())
        row.addWidget(self._spin_end)
        row.addWidget(QLabel('s'))

        apply_btn = QPushButton('Apply')
        apply_btn.setFixedWidth(58)
        apply_btn.setStyleSheet(
            'QPushButton { background: #0d6efd; color: white; border-radius: 3px; '
            'padding: 2px 6px; font-size: 11px; }'
            'QPushButton:hover { background: #0b5ed7; }'
        )
        apply_btn.clicked.connect(self._on_apply)
        row.addWidget(apply_btn)

        reset_btn = QPushButton('Reset to Log')
        reset_btn.setFixedWidth(88)
        reset_btn.setStyleSheet(
            'QPushButton { background: #495057; color: white; border-radius: 3px; '
            'padding: 2px 6px; font-size: 11px; }'
            'QPushButton:hover { background: #343a40; }'
        )
        reset_btn.clicked.connect(self._on_reset)
        row.addWidget(reset_btn)
        row.addStretch()
        layout.addLayout(row)

        self._slider = DualHandleSlider()
        self._slider.range_changed.connect(self._on_slider_changed)
        layout.addWidget(self._slider)

    def set_log_range(self, t_min: float, t_max: float):
        self._t_min = t_min
        self._t_max = t_max
        self._spin_start.setRange(t_min, t_max)
        self._spin_end.setRange(t_min, t_max)
        self._slider.set_bounds(t_min, t_max)
        self.set_range(t_min, t_max)

    def set_range(self, t_start: float, t_end: float):
        self._blocking = True
        t_start = max(self._t_min, min(t_start, self._t_max))
        t_end   = max(self._t_min, min(t_end,   self._t_max))
        self._spin_start.setValue(t_start)
        self._spin_end.setValue(t_end)
        self._slider.set_range(t_start, t_end)
        self._blocking = False

    def _on_apply(self):
        if not self._blocking:
            self.range_changed.emit(self._spin_start.value(), self._spin_end.value())

    def _on_reset(self):
        self.set_range(self._t_min, self._t_max)
        if not self._blocking:
            self.range_changed.emit(self._t_min, self._t_max)

    def _on_slider_changed(self, lo: float, hi: float):
        if self._blocking:
            return
        self._blocking = True
        self._spin_start.setValue(lo)
        self._spin_end.setValue(hi)
        self._blocking = False
        self.range_changed.emit(lo, hi)
