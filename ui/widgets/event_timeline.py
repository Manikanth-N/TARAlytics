from PyQt6.QtWidgets import QWidget, QToolTip
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QRect
from PyQt6.QtGui import QPainter, QColor, QPen, QFont


SEVERITY_HEIGHTS = {
    'CRITICAL': 32,
    'ERROR':    24,
    'WARNING':  18,
    'INFO':     12,
}

SEVERITY_COLORS = {
    'CRITICAL': QColor('#dc3545'),
    'ERROR':    QColor('#fd7e14'),
    'WARNING':  QColor('#ffc107'),
    'INFO':     QColor('#4a90d9'),
}


class EventTimeline(QWidget):
    timeline_clicked = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(32)
        self.setMouseTracking(True)
        self._events = []
        self._t_min = 0.0
        self._t_max = 1.0

    def set_events(self, events: list, t_min: float, t_max: float):
        self._events = events
        self._t_min = t_min
        self._t_max = t_max if t_max > t_min else t_min + 1.0
        self.update()

    def _t_to_x(self, t: float) -> int:
        r = self._t_max - self._t_min
        if r == 0:
            return 0
        frac = (t - self._t_min) / r
        return int(frac * self.width())

    def _x_to_t(self, x: int) -> float:
        if self.width() == 0:
            return self._t_min
        frac = x / self.width()
        return self._t_min + frac * (self._t_max - self._t_min)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        p.fillRect(0, 0, w, h, QColor('#1a1a2e'))
        p.setPen(QPen(QColor('#3a3a5a'), 1))
        p.drawLine(0, 0, w, 0)

        if not self._events or self._t_min >= self._t_max:
            p.end()
            return

        t_range = self._t_max - self._t_min
        for ts, sev, etype, msg in self._events:
            x = int((float(ts) - self._t_min) / t_range * w)
            tick_h = SEVERITY_HEIGHTS.get(sev, 12)
            color = SEVERITY_COLORS.get(sev, QColor('#4a90d9'))
            p.setPen(QPen(color, 2))
            p.drawLine(x, h - tick_h, x, h)
        p.end()

    def mouseMoveEvent(self, event):
        t = self._x_to_t(event.pos().x())
        best = None
        best_dist = 8
        for ts, sev, etype, msg in self._events:
            dx = abs(self._t_to_x(float(ts)) - event.pos().x())
            if dx < best_dist:
                best_dist = dx
                best = (ts, sev, etype, msg)
        if best:
            QToolTip.showText(
                self.mapToGlobal(event.pos()),
                f'[{best[0]:.3f}s] {best[1]} {best[2]}: {best[3]}'
            )
        else:
            QToolTip.hideText()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            t = self._x_to_t(event.pos().x())
            best = None
            best_dist = 15
            for ts, sev, etype, msg in self._events:
                dx = abs(self._t_to_x(float(ts)) - event.pos().x())
                if dx < best_dist:
                    best_dist = dx
                    best = ts
            if best is not None:
                self.timeline_clicked.emit(float(best))
            else:
                self.timeline_clicked.emit(t)
