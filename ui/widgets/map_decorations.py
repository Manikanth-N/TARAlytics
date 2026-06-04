"""
Map decorations — metric scale bar + north arrow (M4).

A transparent overlay child of the Map PlotWidget that paints:
  * a metric scale bar (bottom-left) whose length is derived from the live ENU
    metres-per-pixel and snapped to a 1/2/5×10ⁿ "nice" distance
  * a north arrow (top-right) — ENU north is canvas +Y, so it always points up

Because the overlay is a child of the PlotWidget, QWidget.grab() of the plot
includes it — so the same decorations appear identically in the live view, the
deterministic PNG export (M5) and the PDF report (M6) without re-implementation.

Pure QPainter; renders headless under the offscreen test harness.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QEvent, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QPolygonF
from PyQt6.QtWidgets import QWidget

_FG = QColor('#f2f4f8')
_SHADOW = QColor(0, 0, 0, 160)
_MARGIN = 14


class MapDecorations(QWidget):
    """Scale bar + north arrow drawn over a pyqtgraph PlotWidget."""

    def __init__(self, plot):
        super().__init__(plot)
        self._plot = plot
        self._vb = plot.getViewBox()
        self._enabled = True
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setGeometry(plot.rect())
        plot.installEventFilter(self)
        self._vb.sigRangeChanged.connect(self.update)
        self.raise_()

    def set_enabled(self, on: bool) -> None:
        self._enabled = bool(on)
        self.setVisible(self._enabled)
        self.update()

    # keep the overlay glued to the plot as it resizes
    def eventFilter(self, obj, ev):
        if obj is self._plot and ev.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self.setGeometry(self._plot.rect())
            self.raise_()
        return False

    # metres per screen pixel from the live view transform
    def _metres_per_pixel(self) -> float:
        (x0, x1), _ = self._vb.viewRange()
        w = self._vb.width()
        if w <= 0 or x1 <= x0:
            return 0.0
        return (x1 - x0) / w

    @staticmethod
    def _nice_length(target_m: float) -> float:
        if target_m <= 0:
            return 0.0
        import math
        mag = 10 ** math.floor(math.log10(target_m))
        for m in (1, 2, 5, 10):
            if target_m <= m * mag:
                return float(m * mag)
        return float(10 * mag)

    @staticmethod
    def _fmt(metres: float) -> str:
        if metres >= 1000:
            return f'{metres / 1000:g} km'
        return f'{metres:g} m'

    def paintEvent(self, _):
        if not self._enabled:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._draw_scale_bar(p)
        self._draw_north_arrow(p)
        p.end()

    def _draw_scale_bar(self, p: QPainter):
        mpp = self._metres_per_pixel()
        if mpp <= 0:
            return
        target_px = self.width() * 0.18                 # aim ~18% of width
        nice_m = self._nice_length(target_px * mpp)
        if nice_m <= 0:
            return
        bar_px = nice_m / mpp
        x0 = _MARGIN
        y = self.height() - _MARGIN - 6
        x1 = x0 + bar_px
        label = self._fmt(nice_m)

        def stroke(pen_color, off):
            p.setPen(QPen(pen_color, 2))
            p.drawLine(QPointF(x0 + off, y + off), QPointF(x1 + off, y + off))
            p.drawLine(QPointF(x0 + off, y - 4 + off), QPointF(x0 + off, y + 4 + off))
            p.drawLine(QPointF(x1 + off, y - 4 + off), QPointF(x1 + off, y + 4 + off))

        stroke(_SHADOW, 1)
        stroke(_FG, 0)
        p.setFont(QFont('', 8))
        p.setPen(QPen(_SHADOW))
        p.drawText(int(x0 + 1), int(y - 6 + 1), label)
        p.setPen(QPen(_FG))
        p.drawText(int(x0), int(y - 6), label)

    def _draw_north_arrow(self, p: QPainter):
        cx = self.width() - _MARGIN - 8
        top = _MARGIN
        bot = top + 22
        tip = QPointF(cx, top)
        left = QPointF(cx - 6, bot)
        right = QPointF(cx + 6, bot)
        mid = QPointF(cx, bot - 6)
        tri = QPolygonF([tip, left, mid, right])
        p.setPen(QPen(_SHADOW, 1))
        p.setBrush(_FG)
        p.translate(1, 1); p.setBrush(_SHADOW); p.drawPolygon(tri); p.translate(-1, -1)
        p.setBrush(_FG); p.setPen(QPen(_FG, 1)); p.drawPolygon(tri)
        p.setFont(QFont('', 8, QFont.Weight.Bold))
        p.setPen(QPen(_SHADOW)); p.drawText(int(cx - 3 + 1), int(top - 2 + 1), 'N')
        p.setPen(QPen(_FG)); p.drawText(int(cx - 3), int(top - 2), 'N')
