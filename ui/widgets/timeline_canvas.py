"""
TimelineCanvas — the primary cursor-driven navigation surface (Step 4.2).

A single QPainter widget that renders the flight's temporal structure as stacked
lanes sharing one time axis, and drives the shared cursor (AppState.set_cursor_time)
on click / drag, with wheel zoom, pan, and event / flight-window stepping.

Render order (back to front), per the approved spec:
    1. Flight Windows         (visually dominant for multi-flight logs)
    2. Mission Phase Summary   (narrative summary strip)
    3. Altitude Profile        (the visual spine)
    4. Phase Bands
    5. Mode Bands
    6. Event Pins              (clustered + density-aware, zoom-aware)
    7. Verification Coverage
    8. Cursor                  (live overlay; blitted over a cached lane pixmap)

Performance: lanes 1-7 are rendered once into a cached QPixmap (rebuilt only on
data / view / size change). A cursor move repaints by blitting that pixmap and
drawing the thin cursor overlay, so scrubbing is independent of log size.

The time<->pixel transform and event clustering are module-level pure functions so
they can be unit-tested without a Qt widget.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import numpy as np

from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QPixmap, QPolygonF, QPainterPath,
)

from ui.design.tokens import T
from core import verification_model as vmodel


# ── layout constants ─────────────────────────────────────────────────────────
GUTTER = 78          # left label gutter (px)
AXIS_H = 22          # bottom time-axis height (px)
PAD_TOP = 8
LANE_GAP = 4
CLUSTER_MIN_PX = 11  # event pins closer than this collapse into a cluster


# ── colour maps ──────────────────────────────────────────────────────────────
_PHASE_COLOR = {
    'PRE_ARM': '#243042', 'POST': '#243042',
    'TAKEOFF': '#00C896', 'LAND': '#FFB300',
    'CLIMB':   '#1A9FD5', 'DESCENT': '#0D6FA0',
    'HOVER':   '#42566B', 'RTL': '#9B59B6', 'FLIGHT': '#42566B',
}
_MODE_PALETTE = ['#1A9FD5', '#00C896', '#FFB300', '#9B59B6',
                 '#E67E22', '#16A085', '#E74C3C', '#3498DB']
_SEV_COLOR = {
    'CRITICAL': T.status.critical, 'ERROR': T.status.caution,
    'WARNING': T.status.caution, 'INFO': T.brand.blue,
}
_SEV_RANK = {'INFO': 0, 'WARNING': 1, 'ERROR': 2, 'CRITICAL': 3}
_RANK_SEV = {v: k for k, v in _SEV_RANK.items()}


# ── pure transform / aggregation helpers (no Qt; unit-testable) ───────────────

def time_to_x(t: float, view_start: float, view_end: float,
              x0: float, x1: float) -> float:
    """Map an absolute time to an x pixel within the plot area [x0, x1]."""
    span = view_end - view_start
    if span <= 0:
        return x0
    return x0 + (t - view_start) / span * (x1 - x0)


def x_to_time(x: float, view_start: float, view_end: float,
              x0: float, x1: float) -> float:
    """Inverse of time_to_x; clamps to the view window."""
    if x1 <= x0:
        return view_start
    frac = (x - x0) / (x1 - x0)
    frac = min(1.0, max(0.0, frac))
    return view_start + frac * (view_end - view_start)


@dataclass
class EventCluster:
    t: float                 # representative (mean) time
    count: int
    severity: str            # highest severity among members
    members: list            # the raw event tuples


def cluster_events(events: list, view_start: float, view_end: float,
                   x0: float, x1: float, min_px: float = CLUSTER_MIN_PX) -> list:
    """
    Zoom-aware event clustering. Events visible in [view_start, view_end] whose
    x-pixel positions fall within `min_px` of the running cluster are merged into
    one EventCluster carrying the member count and the highest severity. As the
    view zooms in, clusters split apart and individual pins reappear.

    `events` are (t, severity, type, message) tuples (EventExtractor format).
    """
    vis = [e for e in events if view_start <= e[0] <= view_end]
    vis.sort(key=lambda e: e[0])
    clusters: list[EventCluster] = []
    cur: list = []
    anchor_x = None
    for e in vis:
        ex = time_to_x(e[0], view_start, view_end, x0, x1)
        if anchor_x is None or (ex - anchor_x) <= min_px:
            cur.append(e)
            if anchor_x is None:
                anchor_x = ex
        else:
            clusters.append(_make_cluster(cur))
            cur = [e]
            anchor_x = ex
    if cur:
        clusters.append(_make_cluster(cur))
    return clusters


def _make_cluster(members: list) -> EventCluster:
    t = float(np.mean([m[0] for m in members]))
    rank = max(_SEV_RANK.get(m[1], 0) for m in members)
    return EventCluster(t=t, count=len(members),
                        severity=_RANK_SEV[rank], members=list(members))


def event_density(times: np.ndarray, view_start: float, view_end: float,
                  n_bins: int) -> np.ndarray:
    """Per-bin event counts across the view — the density underlay. Independent of
    cluster collapsing, so distribution stays visible even when pins merge."""
    if n_bins <= 0 or view_end <= view_start or times.size == 0:
        return np.zeros(max(n_bins, 0), dtype=int)
    m = (times >= view_start) & (times <= view_end)
    if not np.any(m):
        return np.zeros(n_bins, dtype=int)
    edges = np.linspace(view_start, view_end, n_bins + 1)
    hist, _ = np.histogram(times[m], bins=edges)
    return hist.astype(int)


def _fmt_clock(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    m, s = divmod(int(round(seconds)), 60)
    return f'{m}:{s:02d}'


# ── the widget ───────────────────────────────────────────────────────────────

class TimelineCanvas(QWidget):
    """Cursor-driven timeline. Reads structure from AppState.timeline_model and
    drives AppState.set_cursor_time on interaction."""

    def __init__(self, app_state, parent=None):
        super().__init__(parent)
        self._app = app_state
        self.setMinimumHeight(300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # derived structure (rebuilt on data_changed)
        self._t_start = 0.0
        self._t_end = 0.0
        self._flights: list = []
        self._phases: list = []
        self._modes: list = []
        self._alt_t = np.array([])
        self._alt_y = np.array([])
        self._alt_src = 'none'
        self._events: list = []
        self._event_times = np.array([])

        # view + cursor state
        self._view_start = 0.0
        self._view_end = 1.0
        self._cursor = 0.0

        # interaction
        self._scrubbing = False
        self._panning = False
        self._pan_x = 0.0
        self._pan_view = (0.0, 1.0)

        # hit-test caches (widget coords, set during static render)
        self._flight_rects: list = []     # (QRectF, FlightWindow)
        self._pin_hits: list = []         # (x, y, EventCluster)
        self._lane_y: dict = {}

        # cached static render
        self._static: Optional[QPixmap] = None

        app_state.data_changed.connect(self._on_data)
        app_state.verification_changed.connect(lambda *_: self._invalidate())
        app_state.connect_cursor(self._on_cursor, 'TimelineCanvas')

    # ── data / view ──────────────────────────────────────────────────────────

    def _on_data(self, _data: dict):
        tm = self._app.timeline_model
        if tm is None:
            self._flights = self._phases = self._modes = self._events = []
            self._alt_t = self._alt_y = self._event_times = np.array([])
            self._t_start, self._t_end = 0.0, 0.0
        else:
            self._t_start, self._t_end = tm.log_span()
            self._flights = tm.flight_windows()
            self._phases = tm.phases()
            self._modes = tm.mode_segments()
            ap = tm.altitude_profile()
            self._alt_t, self._alt_y, self._alt_src = ap.times, ap.agl, ap.source
            self._events = tm.event_regions()
            self._event_times = np.array([e[0] for e in self._events], dtype=float)
        if self._t_end <= self._t_start:
            self._t_end = self._t_start + 1.0
        self._view_start, self._view_end = self._t_start, self._t_end
        self._cursor = self._app.cursor_time
        self._invalidate()

    def _on_cursor(self, t: float):
        self._cursor = float(t)
        self.update()        # cheap: blit cached lanes + overlay

    def _invalidate(self):
        self._static = None
        self.update()

    def resizeEvent(self, e):
        self._invalidate()
        super().resizeEvent(e)

    # ── geometry helpers ───────────────────────────────────────────────────────

    def _plot_x(self) -> tuple[float, float]:
        return float(GUTTER), float(self.width() - 8)

    def _t2x(self, t: float) -> float:
        x0, x1 = self._plot_x()
        return time_to_x(t, self._view_start, self._view_end, x0, x1)

    def _x2t(self, x: float) -> float:
        x0, x1 = self._plot_x()
        return x_to_time(x, self._view_start, self._view_end, x0, x1)

    def _lane_layout(self) -> list:
        """Return [(key, y, h)] for the stacked lanes, top to bottom."""
        n_flights = len(self._flights)
        flight_h = 58 if n_flights > 1 else 40
        specs = [
            ('flights', flight_h),
            ('summary', 22),
            ('altitude', 96),
            ('phase', 26),
            ('mode', 26),
            ('events', 42),
            ('verify', 16),
        ]
        y = PAD_TOP
        out = []
        for key, h in specs:
            out.append((key, y, h))
            y += h + LANE_GAP
        return out

    # ── public API (driven by the module header buttons) ───────────────────────

    @property
    def cursor_time(self) -> float:
        return self._cursor

    def fit(self):
        """Reset zoom/pan to the full log span."""
        self._view_start, self._view_end = self._t_start, self._t_end
        self._invalidate()

    def step_event(self, direction: int):
        """Move the cursor to the next (+1) / previous (-1) event and keep it
        visible. Uses raw event times for precision (not cluster reps)."""
        if self._event_times.size == 0:
            return
        t = self._cursor
        if direction > 0:
            later = self._event_times[self._event_times > t + 1e-6]
            if later.size == 0:
                return
            target = float(later.min())
        else:
            earlier = self._event_times[self._event_times < t - 1e-6]
            if earlier.size == 0:
                return
            target = float(earlier.max())
        self._ensure_visible(target)
        self._app.jump_to_event(target)

    def step_flight(self, direction: int):
        """Jump to the next/previous flight window: zoom to it and put the cursor
        at its start."""
        if not self._flights:
            return
        t = self._cursor
        if direction > 0:
            nxt = [f for f in self._flights if f.start > t + 1e-6]
            target = nxt[0] if nxt else None
        else:
            prv = [f for f in self._flights if f.start < t - 1e-6]
            target = prv[-1] if prv else None
        if target is None:
            return
        self._zoom_to_flight(target)
        self._app.set_cursor_time(target.start)

    # ── interaction ────────────────────────────────────────────────────────────

    def _ensure_visible(self, t: float):
        if self._view_start <= t <= self._view_end:
            return
        half = (self._view_end - self._view_start) / 2
        self._view_start = max(self._t_start, t - half)
        self._view_end = min(self._t_end, self._view_start + 2 * half)
        self._invalidate()

    def _zoom_to_flight(self, fw):
        pad = max(0.02 * (fw.end - fw.start), 0.5)
        self._view_start = max(self._t_start, fw.start - pad)
        self._view_end = min(self._t_end, fw.end + pad)
        if self._view_end <= self._view_start:
            self._view_end = self._view_start + 1.0
        self._invalidate()

    def mousePressEvent(self, e):
        pos = e.position()
        if e.button() == Qt.MouseButton.RightButton:
            self._panning = True
            self._pan_x = pos.x()
            self._pan_view = (self._view_start, self._view_end)
            return
        if e.button() != Qt.MouseButton.LeftButton:
            return
        # flight-bar click → zoom to that flight
        for rect, fw in self._flight_rects:
            if rect.contains(pos):
                self._zoom_to_flight(fw)
                self._app.set_cursor_time(fw.start)
                return
        # event-pin click → jump to event (single) or zoom into cluster (multi)
        for px, py, cl in self._pin_hits:
            if abs(pos.x() - px) <= 7 and abs(pos.y() - py) <= 9:
                if cl.count == 1:
                    self._app.jump_to_event(cl.t)
                else:
                    self._zoom_to_cluster(cl)
                return
        # otherwise scrub the cursor
        self._scrubbing = True
        self._app.set_cursor_time(self._x2t(pos.x()))

    def _zoom_to_cluster(self, cl: EventCluster):
        ts = [m[0] for m in cl.members]
        lo, hi = min(ts), max(ts)
        pad = max(0.5, 0.25 * (hi - lo))
        self._view_start = max(self._t_start, lo - pad)
        self._view_end = min(self._t_end, hi + pad)
        if self._view_end <= self._view_start:
            self._view_end = self._view_start + 1.0
        self._invalidate()

    def mouseMoveEvent(self, e):
        pos = e.position()
        if self._scrubbing:
            self._app.set_cursor_time(self._x2t(pos.x()))
        elif self._panning:
            x0, x1 = self._plot_x()
            span = self._view_end - self._view_start
            dt = (pos.x() - self._pan_x) / max(1.0, (x1 - x0)) * span
            vs = self._pan_view[0] - dt
            ve = self._pan_view[1] - dt
            if vs < self._t_start:
                ve += self._t_start - vs; vs = self._t_start
            if ve > self._t_end:
                vs -= ve - self._t_end; ve = self._t_end
            self._view_start = max(self._t_start, vs)
            self._view_end = min(self._t_end, ve)
            self._invalidate()

    def mouseReleaseEvent(self, e):
        self._scrubbing = False
        self._panning = False

    def wheelEvent(self, e):
        x0, x1 = self._plot_x()
        mx = e.position().x()
        if mx < x0:
            mx = x0
        pivot = self._x2t(mx)
        factor = 0.82 if e.angleDelta().y() > 0 else 1.0 / 0.82
        span = (self._view_end - self._view_start) * factor
        full = self._t_end - self._t_start
        span = min(full, max(full * 1e-4, span))   # clamp zoom range
        frac = (pivot - self._view_start) / max(1e-9, self._view_end - self._view_start)
        vs = pivot - frac * span
        ve = vs + span
        if vs < self._t_start:
            vs = self._t_start; ve = vs + span
        if ve > self._t_end:
            ve = self._t_end; vs = ve - span
        self._view_start = max(self._t_start, vs)
        self._view_end = min(self._t_end, ve)
        self._invalidate()
        e.accept()

    # ── painting ───────────────────────────────────────────────────────────────

    def paintEvent(self, _):
        if self._static is None or self._static.size() != self.size():
            self._render_static()
        p = QPainter(self)
        p.drawPixmap(0, 0, self._static)
        self._draw_cursor(p)
        p.end()

    def _render_static(self):
        pm = QPixmap(self.size())
        pm.fill(QColor(T.surface.base))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._flight_rects = []
        self._pin_hits = []
        self._lane_y = {}

        lanes = self._lane_layout()
        for key, y, h in lanes:
            self._lane_y[key] = (y, h)
            self._draw_lane_label(p, key, y, h)

        if self._t_end > self._t_start:
            self._draw_flights(p, *self._lane_y['flights'])
            self._draw_summary(p, *self._lane_y['summary'])
            self._draw_altitude(p, *self._lane_y['altitude'])
            self._draw_bands(p, self._phases, *self._lane_y['phase'], kind='phase')
            self._draw_bands(p, self._modes, *self._lane_y['mode'], kind='mode')
            self._draw_events(p, *self._lane_y['events'])
            self._draw_verify(p, *self._lane_y['verify'])
            self._draw_axis(p, lanes)
        else:
            self._draw_empty(p)
        p.end()
        self._static = pm

    # -- lane primitives --

    def _draw_lane_label(self, p, key, y, h):
        labels = {'flights': 'FLIGHTS', 'summary': '', 'altitude': 'ALT (m)',
                  'phase': 'PHASE', 'mode': 'MODE', 'events': 'EVENTS',
                  'verify': 'VERIFY'}
        txt = labels.get(key, key.upper())
        if not txt:
            return
        f = QFont(T.font.brand, T.size.xs); f.setWeight(T.weight.semibold)
        p.setFont(f)
        p.setPen(QPen(QColor(T.text.muted)))
        p.drawText(QRectF(6, y, GUTTER - 12, h),
                   int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), txt)

    def _draw_flights(self, p, y, h):
        x0, x1 = self._plot_x()
        # lane backdrop
        p.fillRect(QRectF(x0, y, x1 - x0, h), QColor(T.surface.panel))
        multi = len(self._flights) > 1
        for fw in self._flights:
            fx0 = self._t2x(fw.start); fx1 = self._t2x(fw.end)
            fx0 = max(fx0, x0); fx1 = min(fx1, x1)
            if fx1 - fx0 < 1:
                continue
            rect = QRectF(fx0, y + 3, fx1 - fx0, h - 6)
            self._flight_rects.append((rect, fw))
            base = QColor(T.brand.blue)
            base.setAlphaF(0.30 if fw.index % 2 == 0 else 0.20)
            p.setBrush(QBrush(base))
            active = fw.contains(self._cursor)
            p.setPen(QPen(QColor(T.brand.blue_bright if active else T.brand.blue_deep),
                          2 if active else 1))
            p.drawRoundedRect(rect, 4, 4)
            if rect.width() > 46:
                f = QFont(T.font.brand, T.size.sm); f.setWeight(T.weight.bold)
                p.setFont(f); p.setPen(QPen(QColor(T.text.primary)))
                label = f'F{fw.index + 1}  {_fmt_clock(fw.duration)}'
                if multi and rect.width() > 120:
                    label += f'  ·  {fw.peak_agl:.0f} m  ·  {fw.event_count} ev'
                p.drawText(rect.adjusted(8, 0, -6, 0),
                           int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                           label)

    def _draw_summary(self, p, y, h):
        x0, x1 = self._plot_x()
        n = len(self._flights)
        armed = sum(f.duration for f in self._flights)
        peak = max((f.peak_agl for f in self._flights), default=0.0)
        n_modes = len({s.mode_num for s in self._modes})
        parts = [f"{n} FLIGHT{'S' if n != 1 else ''}",
                 f'ARMED {_fmt_clock(armed)}',
                 f'PEAK {peak:.1f} m',
                 f'{len(self._events)} EVENTS',
                 f'{n_modes} MODES']
        f = QFont(T.font.brand, T.size.sm); f.setWeight(T.weight.semibold)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.6)
        p.setFont(f); p.setPen(QPen(QColor(T.text.secondary)))
        p.drawText(QRectF(x0, y, x1 - x0, h),
                   int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                   '   ·   '.join(parts))

    def _draw_altitude(self, p, y, h):
        x0, x1 = self._plot_x()
        p.fillRect(QRectF(x0, y, x1 - x0, h), QColor(T.surface.panel))
        if self._alt_t.size < 2:
            return
        m = (self._alt_t >= self._view_start) & (self._alt_t <= self._view_end)
        if np.count_nonzero(m) < 2:
            return
        ts = self._alt_t[m]; ys = self._alt_y[m]
        finite = np.isfinite(ys)
        if np.count_nonzero(finite) < 2:
            return
        ymin = float(np.nanmin(ys[finite])); ymax = float(np.nanmax(ys[finite]))
        if ymax - ymin < 1e-6:
            ymax = ymin + 1.0
        top, bot = y + 5, y + h - 5

        def py(v):
            return bot - (v - ymin) / (ymax - ymin) * (bot - top)

        path = QPainterPath(); fill = QPainterPath()
        started = False
        for t, v in zip(ts, ys):
            if not np.isfinite(v):
                continue
            xx = self._t2x(t); yy = py(v)
            if not started:
                path.moveTo(xx, yy); fill.moveTo(xx, bot); fill.lineTo(xx, yy)
                started = True
            else:
                path.lineTo(xx, yy); fill.lineTo(xx, yy)
        if started:
            fill.lineTo(self._t2x(ts[-1]), bot); fill.closeSubpath()
            fc = QColor(T.brand.blue); fc.setAlphaF(0.10)
            p.fillPath(fill, QBrush(fc))
            p.setPen(QPen(QColor(T.brand.blue_bright), 1.4))
            p.drawPath(path)
        # min/max ticks
        f = QFont(T.font.data, T.size.xs); p.setFont(f)
        p.setPen(QPen(QColor(T.text.muted)))
        p.drawText(QRectF(x0 + 2, top - 2, 60, 12),
                   int(Qt.AlignmentFlag.AlignLeft), f'{ymax:.0f}')
        p.drawText(QRectF(x0 + 2, bot - 12, 60, 12),
                   int(Qt.AlignmentFlag.AlignLeft), f'{ymin:.0f}')

    def _draw_bands(self, p, segs, y, h, kind: str):
        x0, x1 = self._plot_x()
        p.fillRect(QRectF(x0, y, x1 - x0, h), QColor(T.surface.panel))
        f = QFont(T.font.brand, T.size.xs); f.setWeight(T.weight.semibold)
        for s in segs:
            if s.t_end < self._view_start or s.t_start > self._view_end:
                continue
            sx0 = max(self._t2x(s.t_start), x0); sx1 = min(self._t2x(s.t_end), x1)
            if sx1 - sx0 < 1:
                continue
            if kind == 'phase':
                col = QColor(_PHASE_COLOR.get(s.kind, '#42566B')); label = s.kind
            else:
                col = QColor(_MODE_PALETTE[s.mode_num % len(_MODE_PALETTE)]
                             if s.mode_num >= 0 else '#42566B'); label = s.mode
            col.setAlphaF(0.55)
            rect = QRectF(sx0, y + 2, sx1 - sx0, h - 4)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(col))
            p.drawRect(rect)
            if rect.width() > 34:
                p.setFont(f); p.setPen(QPen(QColor(T.text.primary)))
                p.drawText(rect.adjusted(4, 0, -2, 0),
                           int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                           label)

    def _draw_events(self, p, y, h):
        x0, x1 = self._plot_x()
        # density underlay
        n_bins = max(1, int((x1 - x0) / 3))
        dens = event_density(self._event_times, self._view_start, self._view_end, n_bins)
        if dens.size and dens.max() > 0:
            bw = (x1 - x0) / n_bins
            dc = QColor(T.brand.blue); dc.setAlphaF(0.12)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(dc))
            mx = dens.max()
            for i, c in enumerate(dens):
                if c <= 0:
                    continue
                bh = (c / mx) * (h - 6)
                p.drawRect(QRectF(x0 + i * bw, y + h - bh, max(1.0, bw), bh))
        # clustered pins
        clusters = cluster_events(self._events, self._view_start, self._view_end, x0, x1)
        stem_top = y + 6; stem_bot = y + h - 2
        for cl in clusters:
            cx = self._t2x(cl.t)
            col = QColor(_SEV_COLOR.get(cl.severity, T.brand.blue))
            p.setPen(QPen(col, 1)); p.drawLine(QPointF(cx, stem_bot), QPointF(cx, stem_top))
            r = 6 if cl.count > 1 else 4
            p.setBrush(QBrush(col)); p.setPen(QPen(QColor(T.surface.base), 1))
            p.drawEllipse(QPointF(cx, stem_top), r, r)
            self._pin_hits.append((cx, stem_top, cl))
            if cl.count > 1:
                f = QFont(T.font.data, 7); f.setWeight(T.weight.bold)
                p.setFont(f); p.setPen(QPen(QColor(T.surface.base)))
                p.drawText(QRectF(cx - r, stem_top - r, 2 * r, 2 * r),
                           int(Qt.AlignmentFlag.AlignCenter),
                           str(cl.count) if cl.count < 100 else '99+')

    def _draw_verify(self, p, y, h):
        x0, x1 = self._plot_x()
        v = self._app.verification
        state = vmodel.normalize_state(getattr(v, 'state', 'UNKNOWN'))
        info = vmodel.info(state)
        col = QColor(info.color)
        label = info.label.lower()
        if state == vmodel.VERIFIED:
            col.setAlphaF(0.45); cover = 1.0
        elif state == vmodel.PARTIAL:
            col.setAlphaF(0.45); cover = 0.9; label = 'partial — interrupted'
        elif state in (vmodel.UNSIGNED, vmodel.UNKNOWN):
            col.setAlphaF(0.30); cover = 0.0
        else:  # INVALID / CORRUPTED / WRONG_KEY
            col.setAlphaF(0.45); cover = 0.0
        rect = QRectF(x0, y + 2, x1 - x0, h - 4)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(T.surface.panel)); p.drawRect(rect)
        if cover > 0:
            p.setBrush(QBrush(col))
            p.drawRect(QRectF(x0, y + 2, (x1 - x0) * cover, h - 4))
        if cover < 1.0 and state == vmodel.PARTIAL:
            hc = QColor(T.status.critical); hc.setAlphaF(0.40)
            p.setBrush(QBrush(hc, Qt.BrushStyle.BDiagPattern))
            p.drawRect(QRectF(x0 + (x1 - x0) * cover, y + 2, (x1 - x0) * (1 - cover), h - 4))
        f = QFont(T.font.brand, T.size.xs); p.setFont(f)
        p.setPen(QPen(QColor(T.text.primary)))
        p.drawText(rect.adjusted(6, 0, -4, 0),
                   int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), label)

    def _draw_axis(self, p, lanes):
        x0, x1 = self._plot_x()
        ay = lanes[-1][1] + lanes[-1][2] + LANE_GAP + 2
        p.setPen(QPen(QColor(T.border.default), 1))
        p.drawLine(QPointF(x0, ay), QPointF(x1, ay))
        f = QFont(T.font.data, T.size.xs); p.setFont(f)
        p.setPen(QPen(QColor(T.text.muted)))
        span = self._view_end - self._view_start
        step = _nice_step(span, 8)
        t = np.ceil(self._view_start / step) * step
        while t <= self._view_end:
            xx = self._t2x(t)
            p.drawLine(QPointF(xx, ay), QPointF(xx, ay + 4))
            p.drawText(QRectF(xx - 28, ay + 4, 56, 14),
                       int(Qt.AlignmentFlag.AlignCenter), f'{t:.0f}s')
            t += step

    def _draw_empty(self, p):
        p.setPen(QPen(QColor(T.text.muted)))
        f = QFont(T.font.brand, T.size.md); p.setFont(f)
        p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter),
                   'No flight loaded — parse a .BIN log')

    def _draw_cursor(self, p):
        if self._t_end <= self._t_start:
            return
        if not (self._view_start <= self._cursor <= self._view_end):
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx = self._t2x(self._cursor)
        lanes = self._lane_layout()
        top = PAD_TOP
        bot = lanes[-1][1] + lanes[-1][2]
        col = QColor(T.brand.blue_bright)
        p.setPen(QPen(col, 1.4)); p.drawLine(QPointF(cx, top), QPointF(cx, bot))
        # playhead triangle
        tri = QPolygonF([QPointF(cx - 5, top - 6), QPointF(cx + 5, top - 6),
                         QPointF(cx, top + 2)])
        p.setBrush(QBrush(col)); p.setPen(Qt.PenStyle.NoPen); p.drawPolygon(tri)
        # readout box (time + phase + mode)
        tm = self._app.timeline_model
        phase = mode = None
        if tm is not None:
            ph = tm.phase_at(self._cursor); phase = ph.kind if ph else None
            mode = tm.mode_at(self._cursor)
        txt = f'{self._cursor:.2f} s'
        if phase:
            txt += f'  ·  {phase}'
        if mode:
            txt += f'  ·  {mode}'
        f = QFont(T.font.data, T.size.xs); f.setWeight(T.weight.semibold)
        p.setFont(f)
        fm = p.fontMetrics(); tw = fm.horizontalAdvance(txt) + 12
        bx = min(max(cx + 6, GUTTER), self.width() - tw - 4)
        by = top + 2
        p.setBrush(QColor(T.surface.elevated)); p.setPen(QPen(col, 1))
        p.drawRoundedRect(QRectF(bx, by, tw, 16), 3, 3)
        p.setPen(QPen(QColor(T.text.primary)))
        p.drawText(QRectF(bx + 6, by, tw, 16),
                   int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), txt)


def _nice_step(span: float, target_ticks: int) -> float:
    """A human-friendly axis step (1/2/5 × 10ⁿ) for the given span."""
    if span <= 0:
        return 1.0
    raw = span / max(1, target_ticks)
    mag = 10 ** np.floor(np.log10(raw))
    for m in (1, 2, 5, 10):
        if raw <= m * mag:
            return float(m * mag)
    return float(10 * mag)
