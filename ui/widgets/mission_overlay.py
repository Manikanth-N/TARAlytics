"""
MissionProcessingOverlay (final UI enhancement).

A full-window branded loading overlay shown while a log is parsed: a TARA UAV mark,
an animated flight-path trace that fills with the *real* parser progress, the *real*
current parser stage, and a "MISSION READY" completion state before it fades away.

Driven by ParserSignals.stage / ParserSignals.progress — no fake progress.
"""
from __future__ import annotations
import math

from PyQt6.QtWidgets import QWidget, QGraphicsOpacityEffect
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF, pyqtSignal, QPropertyAnimation
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPainterPath, QPolygonF

from ui.design.tokens import T


def _mission_profile(x: float) -> float:
    """Mission altitude profile 0..1 over the flight (takeoff · cruise · land)."""
    if x < 0.16:
        return (x / 0.16) ** 0.8                      # climb
    if x > 0.86:
        return max(0.0, (1.0 - x) / 0.14) ** 0.9      # descent
    return 0.96 + 0.04 * math.sin(x * 18.0)           # cruise (slight ripple)


class MissionProcessingOverlay(QWidget):
    done = pyqtSignal()        # emitted after the Mission-Ready hold

    def __init__(self, parent=None):
        super().__init__(parent)
        self._target = 0.0
        self._progress = 0.0
        self._stage = 'Preparing…'
        self._phase = 'processing'   # 'processing' | 'ready'
        self._anim = 0.0
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self.hide()

    # ── API ─────────────────────────────────────────────────────────────────
    def start(self):
        self._target = self._progress = 0.0
        self._stage = 'Preparing…'
        self._phase = 'processing'
        self._anim = 0.0
        self.setGraphicsEffect(None)
        if self.parent():
            self.resize(self.parent().size())
        self.show(); self.raise_()
        self._timer.start()

    def set_stage(self, text: str):
        self._stage = text

    def set_progress(self, pct: int):
        self._target = max(self._target, float(max(0, min(100, pct))))

    def mission_ready(self):
        self._target = 100.0
        self._phase = 'ready'
        self._stage = 'Mission Ready'
        QTimer.singleShot(950, self._fade_out)

    def fail(self):
        # parse error: just hide immediately (the toolbar/status shows the error)
        self._timer.stop(); self.hide()

    # ── animation / fade ──────────────────────────────────────────────────────
    def _tick(self):
        self._anim += 0.033
        # ease real progress toward the latest target
        self._progress += (self._target - self._progress) * 0.18
        if self._target - self._progress < 0.4:
            self._progress = self._target
        self.update()

    def _fade_out(self):
        eff = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b'opacity', self)
        anim.setDuration(350); anim.setStartValue(1.0); anim.setEndValue(0.0)
        anim.finished.connect(self._finish)
        self._anim_obj = anim
        anim.start()

    def _finish(self):
        self._timer.stop()
        self.hide()
        self.setGraphicsEffect(None)
        self.done.emit()

    # ── paint ─────────────────────────────────────────────────────────────────
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        # backdrop
        p.fillRect(self.rect(), QColor(6, 14, 24, 244))
        cx = w / 2
        ready = self._phase == 'ready'
        accent = QColor(T.status.nominal) if ready else QColor(T.brand.blue_bright)

        # ── TARA mark (stylized eagle chevron) ──
        my = h * 0.30
        p.save(); p.translate(cx, my)
        glow = QColor(accent); glow.setAlphaF(0.18 + 0.10 * (1 + math.sin(self._anim * 3)) / 2)
        p.setBrush(glow); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(0, 0), 44, 44)
        pen = QPen(accent, 4, cap=Qt.PenCapStyle.RoundCap, join=Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        wing = QPainterPath()
        wing.moveTo(-26, 6); wing.lineTo(0, -16); wing.lineTo(26, 6)
        wing.moveTo(-14, 12); wing.lineTo(0, 0); wing.lineTo(14, 12)
        p.drawPath(wing)
        p.restore()

        # wordmark
        p.setPen(QPen(QColor(T.text.primary)))
        f = QFont(T.font.brand, 26, QFont.Weight.Bold)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 6)
        p.setFont(f)
        p.drawText(QRectF(0, my + 52, w, 38), int(Qt.AlignmentFlag.AlignHCenter), 'TARA UAV')
        f2 = QFont(T.font.brand, T.size.md); f2.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 4)
        p.setFont(f2); p.setPen(QPen(QColor(T.text.secondary)))
        p.drawText(QRectF(0, my + 90, w, 22), int(Qt.AlignmentFlag.AlignHCenter),
                   'MISSION READY' if ready else 'MISSION PROCESSING')

        # ── flight-path trace ──
        px0, px1 = w * 0.18, w * 0.82
        base = h * 0.66
        amp = h * 0.12
        n = 160
        full = QPainterPath(); trav = QPainterPath()
        frac = self._progress / 100.0
        ax = ay = None
        started_t = False
        for i in range(n + 1):
            x = i / n
            xx = px0 + x * (px1 - px0)
            yy = base - _mission_profile(x) * amp
            if i == 0:
                full.moveTo(xx, yy)
            else:
                full.lineTo(xx, yy)
            if x <= frac:
                if not started_t:
                    trav.moveTo(xx, yy); started_t = True
                else:
                    trav.lineTo(xx, yy)
                ax, ay = xx, yy
        p.setPen(QPen(QColor(60, 80, 104), 1.5, Qt.PenStyle.DashLine)); p.drawPath(full)
        p.setPen(QPen(accent, 2.6)); p.drawPath(trav)
        # ground line
        p.setPen(QPen(QColor(T.border.subtle), 1)); p.drawLine(QPointF(px0, base + 4), QPointF(px1, base + 4))
        # aircraft marker at the leading edge
        if ax is not None:
            halo = QColor(accent); halo.setAlphaF(0.25 + 0.2 * (1 + math.sin(self._anim * 6)) / 2)
            p.setBrush(halo); p.setPen(Qt.PenStyle.NoPen); p.drawEllipse(QPointF(ax, ay), 9, 9)
            tri = QPolygonF([QPointF(ax + 7, ay), QPointF(ax - 5, ay - 5), QPointF(ax - 5, ay + 5)])
            p.setBrush(QBrush(accent)); p.drawPolygon(tri)

        # ── stage + percentage ──
        p.setFont(QFont(T.font.data, T.size.md))
        p.setPen(QPen(QColor(T.text.data)))
        p.drawText(QRectF(0, base + 24, w, 22), int(Qt.AlignmentFlag.AlignHCenter), self._stage)
        if ready:
            p.setPen(QPen(QColor(T.status.nominal)))
            p.setFont(QFont(T.font.brand, T.size.x2l, QFont.Weight.Bold))
            p.drawText(QRectF(0, base + 50, w, 36), int(Qt.AlignmentFlag.AlignHCenter), '✓  READY')
        else:
            p.setFont(QFont(T.font.data, T.size.x2l, QFont.Weight.Bold))
            p.setPen(QPen(accent))
            p.drawText(QRectF(0, base + 48, w, 34), int(Qt.AlignmentFlag.AlignHCenter),
                       f'{int(self._progress)}%')
        p.end()
