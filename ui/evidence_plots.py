"""
Evidence plot rendering (P3.4) — small signal plots embedded in evidence reports.

Given the parsed data and a Finding, render its supporting signals over the relevant
window to a PNG (QPainter → QImage, no extra dependency). The narrative report then
embeds the image so a finding is backed by the actual trace, not just a number.
"""
from __future__ import annotations
import re
import numpy as np

from PyQt6.QtGui import QImage, QPainter, QColor, QPen, QFont, QPainterPath
from PyQt6.QtCore import Qt, QRectF, QPointF

from ui.design.tokens import T

_INST = re.compile(r'^(.+)\[(\d+)\]$')
_PAIR = re.compile(r'^([A-Za-z0-9]+)\.([A-Za-z0-9_]+)$')

# Fallback signals per finding category (when evidence strings aren't plottable).
_CATEGORY_SIGNALS = {
    'OSCILLATION': [('ATT', 'Roll'), ('ATT', 'DesRoll'), ('ATT', 'Pitch'), ('ATT', 'DesPitch')],
    'TRACKING': [('ATT', 'Roll'), ('ATT', 'DesRoll'), ('ATT', 'Pitch'), ('ATT', 'DesPitch')],
    'YAW': [('ATT', 'Yaw'), ('ATT', 'DesYaw')],
    'SATURATION': [('RCOU', 'C1'), ('RCOU', 'C2'), ('RCOU', 'C3'), ('RCOU', 'C4')],
    'LANDING': [('BARO', 'CRt'), ('POS', 'RelHomeAlt')],
    'VIBE': [('VIBE', 'VibeX'), ('VIBE', 'VibeY'), ('VIBE', 'VibeZ')],
    'EKF': [('XKF4', 'SV'), ('XKF4', 'SP'), ('XKF4', 'SH'), ('XKF4', 'SM')],
    'GPS': [('GPS', 'NSats'), ('GPS', 'HDop')],
    'POWER': [('BAT', 'Volt'), ('BAT', 'Curr')],
}
_COLORS = ['#22AADF', '#FF3DBE', '#00C896', '#FFB300', '#E67E22', '#9B59B6']


def _resolve_key(data, base):
    if base in data:
        return base
    insts = sorted(k for k in data if _INST.match(k) and _INST.match(k).group(1) == base)
    return insts[0] if insts else None


def _signals_for(data, finding):
    pairs = []
    for e in finding.evidence:
        m = _PAIR.match(e)
        if m:
            pairs.append((m.group(1), m.group(2)))
    if not pairs:
        pairs = _CATEGORY_SIGNALS.get(finding.category, [])
    out = []
    for base, col in pairs:
        key = _resolve_key(data, base)
        df = data.get(key) if key else None
        if df is not None and 'TimeS' in df.columns and col in df.columns:
            out.append((f'{base}.{col}', key, col))
    return out


def can_plot(data, finding) -> bool:
    return len(_signals_for(data, finding)) > 0


def render_finding_plot(data, finding, path, span=None, w=620, h=200) -> bool:
    """Render a finding's evidence signals to a PNG. `span` = (t0,t1); defaults to a
    ±6 s window around the finding time, or the data span for trend findings."""
    sigs = _signals_for(data, finding)
    if not sigs:
        return False
    # window
    if span is None:
        if finding.t_start is not None:
            t0, t1 = finding.t_start - 6.0, finding.t_start + 6.0
        else:
            t0, t1 = _data_span(data, sigs)
    else:
        t0, t1 = span
    if t1 <= t0:
        t1 = t0 + 1.0

    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor(T.surface.base))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pad_l, pad_r, pad_t, pad_b = 8, 8, 26, 22
    x0, x1 = pad_l, w - pad_r
    y0, y1 = pad_t, h - pad_b
    p.fillRect(QRectF(x0, y0, x1 - x0, y1 - y0), QColor(T.surface.panel))

    # title
    p.setPen(QPen(QColor(T.text.secondary))); p.setFont(QFont(T.font.brand, 9, QFont.Weight.Bold))
    p.drawText(QRectF(0, 4, w, 16), int(Qt.AlignmentFlag.AlignCenter),
               f'{finding.title}  ({t0:.1f}–{t1:.1f} s)')

    # collect series, common value range
    series = []
    vmin, vmax = np.inf, -np.inf
    for label, key, col in sigs:
        df = data[key]
        t = df['TimeS'].to_numpy(float); v = df[col].to_numpy(float)
        order = np.argsort(t); t, v = t[order], v[order]
        m = (t >= t0) & (t <= t1) & np.isfinite(v)
        if np.count_nonzero(m) < 2:
            continue
        series.append((label, t[m], v[m]))
        vmin = min(vmin, float(v[m].min())); vmax = max(vmax, float(v[m].max()))
    if not series:
        p.end(); return False
    if vmax - vmin < 1e-6:
        vmax = vmin + 1.0
    rng = (vmax - vmin) * 1.1
    mid = (vmax + vmin) / 2
    lo, hi = mid - rng / 2, mid + rng / 2

    def px(tt): return x0 + (tt - t0) / (t1 - t0) * (x1 - x0)
    def py(vv): return y1 - (vv - lo) / (hi - lo) * (y1 - y0)

    if lo < 0 < hi:
        p.setPen(QPen(QColor(T.border.default), 1, Qt.PenStyle.DotLine))
        p.drawLine(QPointF(x0, py(0)), QPointF(x1, py(0)))
    # finding time marker
    if finding.t_start is not None and t0 <= finding.t_start <= t1:
        p.setPen(QPen(QColor(T.status.caution), 1, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(px(finding.t_start), y0), QPointF(px(finding.t_start), y1))

    p.setFont(QFont(T.font.data, 8))
    for i, (label, t, v) in enumerate(series):
        col = QColor(_COLORS[i % len(_COLORS)])
        path_ = QPainterPath(); started = False
        for tt, vv in zip(t, v):
            xx, yy = px(float(tt)), py(float(vv))
            if not started:
                path_.moveTo(xx, yy); started = True
            else:
                path_.lineTo(xx, yy)
        p.setPen(QPen(col, 1.4)); p.drawPath(path_)
        # legend chip
        lx = x0 + 6 + i * (w - 12) / max(len(series), 1)
        p.fillRect(QRectF(lx, y1 + 6, 10, 8), col)
        p.setPen(QPen(QColor(T.text.secondary)))
        p.drawText(QRectF(lx + 13, y1 + 4, 130, 12), int(Qt.AlignmentFlag.AlignLeft), label)

    # value range labels
    p.setPen(QPen(QColor(T.text.muted)))
    p.drawText(QRectF(x0 + 2, y0 - 1, 60, 12), int(Qt.AlignmentFlag.AlignLeft), f'{hi:.1f}')
    p.drawText(QRectF(x0 + 2, y1 - 12, 60, 12), int(Qt.AlignmentFlag.AlignLeft), f'{lo:.1f}')
    p.end()
    return img.save(path, 'PNG')


def _data_span(data, sigs):
    lo, hi = np.inf, -np.inf
    for _, key, _col in sigs:
        t = data[key]['TimeS']
        lo = min(lo, float(t.min())); hi = max(hi, float(t.max()))
    if not np.isfinite(lo):
        return 0.0, 1.0
    return lo, hi
