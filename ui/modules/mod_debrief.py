"""
DebriefModule — the landing screen (Module 1), rebuilt around the question that
matters first: **"Was this a good flight?"** (P3).

Leads with the whole-flight verdict and pilot scorecard from the Flight Intelligence
Layer, then the automated findings (click to jump the shared cursor to the moment),
then supporting flight profile + verification. Reads everything from AppState.
"""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QScrollArea, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from ui.design.tokens import T
from ui.app_state import AppState, VerifyResult
from ui.widgets.module_header import ModuleHeader
from ui.widgets.badge import StatusBadge
from ui.widgets.card import MetricCard
from core.flight_metrics import FlightMetrics

_NAV_SIGNALS = 4
_NAV_VERIFY = 6

_VERDICT_COLOR = {
    'GOOD': T.status.nominal, 'ACCEPTABLE': T.brand.blue,
    'MARGINAL': T.status.caution, 'POOR': T.status.critical,
    'NO DATA': T.text.muted,
}
_SEV_COLOR = {'CRITICAL': T.status.critical, 'ERROR': '#E67E22',
              'WARNING': T.status.caution, 'INFO': T.brand.blue}


def _score_color(score) -> str:
    if score is None:
        return T.text.muted
    if score >= 80:
        return T.status.nominal
    if score >= 60:
        return T.status.caution
    return T.status.critical


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    f = QFont(T.font.brand, T.size.xs); f.setWeight(T.weight.bold)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.8)
    lbl.setFont(f); lbl.setStyleSheet(f'color: {T.text.muted};')
    return lbl


class ScoreCard(QWidget):
    """A category score: name, 0-100 value, grade — coloured by score."""
    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f'background: {T.surface.card}; border-radius: 4px;')
        lay = QVBoxLayout(self)
        lay.setContentsMargins(T.spacing.px12, T.spacing.px8, T.spacing.px12, T.spacing.px8)
        lay.setSpacing(2)
        self._name = QLabel(name.upper())
        self._name.setFont(QFont(T.font.brand, T.size.xs, T.weight.bold))
        self._name.setStyleSheet(f'color: {T.text.muted};')
        row = QHBoxLayout(); row.setSpacing(T.spacing.px8)
        self._score = QLabel('—')
        self._score.setFont(QFont(T.font.data, T.size.x2l, T.weight.bold))
        self._grade = QLabel('')
        self._grade.setFont(QFont(T.font.brand, T.size.lg, T.weight.bold))
        self._grade.setAlignment(Qt.AlignmentFlag.AlignBottom)
        row.addWidget(self._score); row.addWidget(self._grade); row.addStretch()
        self._detail = QLabel('')
        self._detail.setStyleSheet(f'color: {T.text.secondary}; font-size: {T.size.xs}px;')
        lay.addWidget(self._name); lay.addLayout(row); lay.addWidget(self._detail)

    def set(self, score, grade, detail=''):
        col = _score_color(score)
        self._score.setText('—' if score is None else f'{score:.0f}')
        self._score.setStyleSheet(f'color: {col};')
        self._grade.setText(grade or ''); self._grade.setStyleSheet(f'color: {col};')
        self._detail.setText(detail)


class FindingRow(QWidget):
    """One automated finding; click jumps the shared cursor to its moment."""
    clicked = pyqtSignal(float)

    def __init__(self, finding, parent=None):
        super().__init__(parent)
        self._t = finding.t_start
        self.setCursor(Qt.CursorShape.PointingHandCursor if self._t is not None
                       else Qt.CursorShape.ArrowCursor)
        hl = QHBoxLayout(self); hl.setContentsMargins(4, 3, 4, 3); hl.setSpacing(T.spacing.px8)
        sev = QLabel(finding.severity)
        sev.setFixedWidth(64)
        sev.setFont(QFont(T.font.brand, T.size.xs, T.weight.bold))
        sev.setStyleSheet(f'color: {_SEV_COLOR.get(finding.severity, T.text.secondary)};')
        cat = QLabel(finding.category); cat.setFixedWidth(86)
        cat.setStyleSheet(f'color: {T.text.muted}; font-size: {T.size.xs}px;')
        txt = QLabel(f'<b>{finding.title}</b> — {finding.detail}')
        txt.setStyleSheet(f'color: {T.text.secondary}; font-size: {T.size.sm}px;')
        txt.setWordWrap(True)
        when = QLabel(f'{finding.t_start:.1f} s' if finding.t_start is not None else '')
        when.setFixedWidth(60)
        when.setStyleSheet(f'color: {T.text.muted}; font-family: {T.font.data}; '
                           f'font-size: {T.size.xs}px;')
        when.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        hl.addWidget(sev); hl.addWidget(cat); hl.addWidget(txt, 1); hl.addWidget(when)

    def mousePressEvent(self, e):
        if self._t is not None:
            self.clicked.emit(float(self._t))


class DebriefModule(QWidget):
    nav_requested = pyqtSignal(int)

    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self._app = app_state
        self._setup_ui()
        app_state.data_changed.connect(self._on_data)
        app_state.verification_changed.connect(self._on_verify)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        root.addWidget(ModuleHeader('Debrief'))
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget(); scroll.setWidget(content); root.addWidget(scroll, 1)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(T.spacing.px24, T.spacing.px24, T.spacing.px24, T.spacing.px24)
        layout.setSpacing(T.spacing.px16)

        layout.addWidget(self._build_verdict())
        layout.addWidget(_section_label('Pilot Scorecard'))
        layout.addLayout(self._build_scorecard())
        layout.addWidget(_section_label('Automated Findings'))
        layout.addWidget(self._build_findings())

        row = QHBoxLayout(); row.setSpacing(T.spacing.px16)
        row.addWidget(self._build_profile(), 1)
        row.addWidget(self._build_verify(), 1)
        layout.addLayout(row)
        layout.addLayout(self._build_actions())
        layout.addStretch()

    def _build_verdict(self) -> QWidget:
        self._verdict_panel = QFrame()
        self._verdict_panel.setStyleSheet(
            f'background: {T.surface.elevated}; border-radius: 6px;')
        lay = QVBoxLayout(self._verdict_panel)
        lay.setContentsMargins(T.spacing.px24, T.spacing.px16, T.spacing.px24, T.spacing.px16)
        lay.setSpacing(T.spacing.px4)
        q = QLabel('WAS THIS A GOOD FLIGHT?')
        qf = QFont(T.font.brand, T.size.sm, T.weight.bold)
        qf.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.2)
        q.setFont(qf); q.setStyleSheet(f'color: {T.text.muted};')
        lay.addWidget(q)
        row = QHBoxLayout(); row.setSpacing(T.spacing.px16)
        self._verdict = QLabel('—')
        self._verdict.setFont(QFont(T.font.brand, T.size.x2l + 8, T.weight.bold))
        self._score_big = QLabel('')
        self._score_big.setFont(QFont(T.font.data, T.size.x2l, T.weight.bold))
        self._score_big.setAlignment(Qt.AlignmentFlag.AlignBottom)
        row.addWidget(self._verdict); row.addWidget(self._score_big); row.addStretch()
        lay.addLayout(row)
        self._headline = QLabel('Load a log to assess the flight.')
        self._headline.setStyleSheet(f'color: {T.text.secondary}; font-size: {T.size.md}px;')
        self._headline.setWordWrap(True)
        lay.addWidget(self._headline)
        self._factors = QLabel('')
        self._factors.setStyleSheet(f'color: {T.text.muted}; font-size: {T.size.sm}px;')
        lay.addWidget(self._factors)
        return self._verdict_panel

    def _build_scorecard(self) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(T.spacing.px12)
        self._sc_overall = ScoreCard('Overall')
        self._sc_track = ScoreCard('Attitude Tracking')
        self._sc_smooth = ScoreCard('Control Smoothness')
        self._sc_yaw = ScoreCard('Yaw Discipline')
        self._sc_land = ScoreCard('Landing')
        for c in (self._sc_overall, self._sc_track, self._sc_smooth, self._sc_yaw, self._sc_land):
            row.addWidget(c)
        return row

    def _build_findings(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet(f'background: {T.surface.card}; border-radius: 4px;')
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(T.spacing.px12, T.spacing.px8, T.spacing.px12, T.spacing.px8)
        lay.setSpacing(2)
        self._findings_layout = lay
        self._findings_empty = QLabel('No findings — clean flight.')
        self._findings_empty.setStyleSheet(f'color: {T.text.secondary}; font-size: {T.size.sm}px;')
        lay.addWidget(self._findings_empty)
        return panel

    def _build_profile(self) -> QWidget:
        panel = QWidget(); panel.setStyleSheet(f'background: {T.surface.card}; border-radius: 4px;')
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(T.spacing.px16, T.spacing.px12, T.spacing.px16, T.spacing.px12)
        lay.setSpacing(T.spacing.px8)
        lay.addWidget(_section_label('Flight Profile'))
        self._m_duration = MetricCard('Flight time')
        self._m_alt = MetricCard('Max altitude')
        self._m_events = MetricCard('Events')
        self._m_modes = MetricCard('Mode changes')
        for c in (self._m_duration, self._m_alt, self._m_events, self._m_modes):
            lay.addWidget(c)
        lay.addStretch()
        return panel

    def _build_verify(self) -> QWidget:
        panel = QWidget(); panel.setStyleSheet(f'background: {T.surface.card}; border-radius: 4px;')
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(T.spacing.px16, T.spacing.px12, T.spacing.px16, T.spacing.px12)
        lay.setSpacing(T.spacing.px8)
        lay.addWidget(_section_label('Verification'))
        self._v_badge = StatusBadge('UNVERIFIED', 'UNVERIFIED')
        self._v_algo = QLabel('—'); self._v_chunks = QLabel('—'); self._v_detail = QLabel('')
        self._v_detail.setWordWrap(True)
        for lbl in (self._v_algo, self._v_chunks, self._v_detail):
            lbl.setStyleSheet(f'color: {T.text.secondary}; font-size: {T.size.sm}px;')
        for wgt in (self._v_badge, self._v_algo, self._v_chunks, self._v_detail):
            lay.addWidget(wgt)
        lay.addStretch()
        return panel

    def _build_actions(self) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(T.spacing.px8)
        b_sig = QPushButton('Open Signal Plotter'); b_sig.setProperty('role', 'primary')
        b_sig.clicked.connect(lambda: self.nav_requested.emit(_NAV_SIGNALS))
        b_ver = QPushButton('View Verification')
        b_ver.clicked.connect(lambda: self.nav_requested.emit(_NAV_VERIFY))
        row.addWidget(b_sig); row.addWidget(b_ver); row.addStretch()
        return row

    # ── data ──────────────────────────────────────────────────────────────────

    def _on_data(self, data: dict):
        self._fill_quality()
        self._fill_profile(data)

    def _fill_quality(self):
        rep = self._app.flight_report
        if rep is None:
            return
        q = rep.quality
        col = _VERDICT_COLOR.get(q.verdict, T.text.muted)
        self._verdict.setText(q.verdict); self._verdict.setStyleSheet(f'color: {col};')
        self._verdict_panel.setStyleSheet(
            f'background: {T.surface.elevated}; border-radius: 6px; '
            f'border-left: 4px solid {col};')
        self._score_big.setText('' if q.score is None else f'{q.score:.0f}/100')
        self._score_big.setStyleSheet(f'color: {col};')
        self._headline.setText(q.headline)
        self._factors.setText(('Drivers: ' + ' · '.join(q.factors)) if q.factors else '')

        sc = rep.scorecard
        self._sc_overall.set(sc.overall, sc.grade,
                             f'{rep.flight_count} flight(s) · {rep.armed_duration_s:.0f}s armed')
        by = {c.name: c for c in sc.categories}
        self._sc_track.set(*self._cat(by, 'Attitude tracking'))
        self._sc_smooth.set(*self._cat(by, 'Control smoothness'))
        self._sc_yaw.set(*self._cat(by, 'Yaw discipline'))
        self._sc_land.set(*self._cat(by, 'Landing quality'))
        self._fill_findings(rep.findings)

    @staticmethod
    def _cat(by, name):
        c = by.get(name)
        return (c.score, c.grade, c.detail) if c else (None, None, '—')

    def _fill_findings(self, findings):
        while self._findings_layout.count():
            it = self._findings_layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        if not findings:
            empty = QLabel('No findings — clean flight.')
            empty.setStyleSheet(f'color: {T.status.nominal}; font-size: {T.size.sm}px;')
            self._findings_layout.addWidget(empty)
            return
        for f in findings[:20]:
            row = FindingRow(f)
            row.clicked.connect(self._app.jump_to_event)
            self._findings_layout.addWidget(row)

    def _fill_profile(self, data: dict):
        self._m_duration.set_value(FlightMetrics.duration(data)[1])
        self._m_alt.set_value(FlightMetrics.max_altitude(data)[1])
        self._m_events.set_value(str(FlightMetrics.event_count(data)))
        self._m_modes.set_value(str(FlightMetrics.mode_change_count(data)))

    def _on_verify(self, result: VerifyResult):
        self._v_badge.set_state(result.state, result.state)
        self._v_algo.setText(result.algo_name if result.algo_name != '—' else '—')
        self._v_chunks.setText(
            f'{result.chain_chunks:,} chunks verified' if result.chain_chunks else '—')
        self._v_detail.setText(result.detail[:80] if result.detail else '')
