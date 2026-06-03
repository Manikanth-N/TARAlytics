"""
DebriefModule — post-flight summary (Module 1).

Landing screen after a parse. Answers "was this flight okay?" with a flight
profile column, a 2x2 health grid, a verification panel, and a notable-events
list. Reads everything from AppState signals and the core analyzers.
"""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QScrollArea, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from ui.design.tokens import T
from ui.app_state import AppState, FlightMeta, VerifyResult
from ui.widgets.module_header import ModuleHeader
from ui.widgets.badge import StatusBadge
from ui.widgets.card import MetricCard, HealthCard
from core.flight_metrics import FlightMetrics
from core.health_analyzer import HealthAnalyzer
from core.event_extractor import EventExtractor

# Module indices used by nav_requested (match MainWindow tab order).
_NAV_SIGNALS = 1
_NAV_VERIFY = 3

_SEV_COLORS = {
    'CRITICAL': T.status.critical,
    'ERROR':    T.status.caution,
    'WARNING':  T.status.caution,
    'INFO':     T.text.secondary,
}
_SEV_PRIORITY = {'CRITICAL': 0, 'ERROR': 1, 'WARNING': 2, 'INFO': 3}


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    f = QFont(T.font.brand, T.size.xs)
    f.setWeight(T.weight.bold)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.8)
    lbl.setFont(f)
    lbl.setStyleSheet(f'color: {T.text.muted};')
    return lbl


class DebriefModule(QWidget):
    nav_requested = pyqtSignal(int)

    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self._app_state = app_state
        self._setup_ui()
        app_state.data_changed.connect(self._on_data)
        app_state.verification_changed.connect(self._on_verify)

    # ── UI ──────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(ModuleHeader('Debrief'))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(T.spacing.px24, T.spacing.px24,
                                  T.spacing.px24, T.spacing.px24)
        layout.setSpacing(T.spacing.px16)

        row1 = QHBoxLayout()
        row1.setSpacing(T.spacing.px16)
        row1.addWidget(self._build_profile(), 1)
        row1.addWidget(self._build_health(), 2)
        row1.addWidget(self._build_verify(), 1)
        layout.addLayout(row1)

        layout.addWidget(self._build_events())
        layout.addLayout(self._build_actions())
        layout.addStretch()

    def _build_profile(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet(f'background: {T.surface.card}; border-radius: 4px;')
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(T.spacing.px16, T.spacing.px12,
                               T.spacing.px16, T.spacing.px12)
        lay.setSpacing(T.spacing.px8)
        lay.addWidget(_section_label('Flight Profile'))

        self._m_duration = MetricCard('Flight time')
        self._m_alt      = MetricCard('Max altitude')
        self._m_events   = MetricCard('Events')
        self._m_modes    = MetricCard('Mode changes')
        self._m_arm      = MetricCard('ARM events')
        for c in (self._m_duration, self._m_alt, self._m_events,
                  self._m_modes, self._m_arm):
            lay.addWidget(c)
        lay.addStretch()
        return panel

    def _build_health(self) -> QWidget:
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(T.spacing.px8)
        lay.addWidget(_section_label('Health Assessment'))

        grid = QGridLayout()
        grid.setSpacing(T.spacing.px8)
        self._h_nav  = HealthCard('NAVIGATION')
        self._h_prop = HealthCard('PROPULSION')
        self._h_pwr  = HealthCard('POWER')
        self._h_str  = HealthCard('STRUCTURAL')
        for hc in (self._h_nav, self._h_prop, self._h_pwr, self._h_str):
            hc.drill_down_requested.connect(lambda _=None: self.nav_requested.emit(_NAV_SIGNALS))
        grid.addWidget(self._h_nav, 0, 0)
        grid.addWidget(self._h_prop, 0, 1)
        grid.addWidget(self._h_pwr, 1, 0)
        grid.addWidget(self._h_str, 1, 1)
        lay.addLayout(grid, 1)
        return panel

    def _build_verify(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet(f'background: {T.surface.card}; border-radius: 4px;')
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(T.spacing.px16, T.spacing.px12,
                               T.spacing.px16, T.spacing.px12)
        lay.setSpacing(T.spacing.px8)
        lay.addWidget(_section_label('Verification'))

        self._v_badge  = StatusBadge('UNVERIFIED', 'UNVERIFIED')
        self._v_algo   = QLabel('—')
        self._v_chunks = QLabel('—')
        self._v_detail = QLabel('')
        self._v_detail.setWordWrap(True)
        for lbl in (self._v_algo, self._v_chunks, self._v_detail):
            lbl.setStyleSheet(f'color: {T.text.secondary}; font-size: {T.size.sm}px;')
        lay.addWidget(self._v_badge)
        lay.addWidget(self._v_algo)
        lay.addWidget(self._v_chunks)
        lay.addWidget(self._v_detail)
        lay.addStretch()
        return panel

    def _build_events(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet(f'background: {T.surface.card}; border-radius: 4px;')
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(T.spacing.px16, T.spacing.px12,
                               T.spacing.px16, T.spacing.px12)
        lay.setSpacing(T.spacing.px4)
        lay.addWidget(_section_label('Notable Events'))
        self._events_layout = QVBoxLayout()
        self._events_layout.setSpacing(2)
        lay.addLayout(self._events_layout)
        return panel

    def _build_actions(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(T.spacing.px8)
        b_sig = QPushButton('Open Signal Plotter')
        b_sig.setProperty('role', 'primary')
        b_sig.clicked.connect(lambda: self.nav_requested.emit(_NAV_SIGNALS))
        b_ver = QPushButton('View Verification')
        b_ver.clicked.connect(lambda: self.nav_requested.emit(_NAV_VERIFY))
        row.addWidget(b_sig)
        row.addWidget(b_ver)
        row.addStretch()
        return row

    # ── Data handlers ───────────────────────────────────────────────────────

    def _on_data(self, data: dict):
        self._fill_metrics(data)
        self._fill_health(data)
        self._fill_events(data)

    def _fill_metrics(self, data: dict):
        self._m_duration.set_value(FlightMetrics.duration(data)[1])
        self._m_alt.set_value(FlightMetrics.max_altitude(data)[1])
        self._m_events.set_value(str(FlightMetrics.event_count(data)))
        self._m_modes.set_value(str(FlightMetrics.mode_change_count(data)))
        self._m_arm.set_value(str(FlightMetrics.arm_count(data)))

    def _fill_health(self, data: dict):
        # Navigation — EKF + GPS
        ekf = HealthAnalyzer.ekf(data)
        gps = HealthAnalyzer.gps(data)
        nav_state = {'OK': 'NOMINAL', 'WARN': 'CAUTION', 'NO DATA': 'NO DATA'}.get(
            ekf['status'] if ekf['status'] != 'NO DATA' else gps['status'], 'NO DATA')
        self._h_nav.set_status(nav_state)
        self._h_nav.clear_metrics()
        self._h_nav.add_metric('EKF', ekf['status'])
        if gps['is_sitl']:
            self._h_nav.add_metric('GPS', 'SITL')
        else:
            self._h_nav.add_metric('GPS fix', gps['fix'])
            self._h_nav.add_metric('Sats', str(gps['sats']))

        # Propulsion — ESCX balance
        escx = [k for k in data if k.startswith('ESCX[')]
        outs = []
        for k in escx[:4]:
            df = data[k]
            if 'outpct' in df.columns and not df.empty:
                outs.append(float(df['outpct'].mean()))
        self._h_prop.clear_metrics()
        if outs:
            spread = max(outs) - min(outs)
            self._h_prop.set_status('NOMINAL' if spread <= 10 else 'CAUTION')
            self._h_prop.add_metric('Motors', str(len(outs)))
            self._h_prop.add_metric('Balance', f'{spread:.1f}', '%')
        else:
            self._h_prop.set_status('NO DATA')

        # Power — BAT
        bat = data.get('BAT')
        self._h_pwr.clear_metrics()
        if bat is not None and not bat.empty and 'Volt' in bat.columns:
            vmin, vmax = float(bat['Volt'].min()), float(bat['Volt'].max())
            curr = float(bat['Curr'].max()) if 'Curr' in bat.columns else 0.0
            self._h_pwr.set_status('NOMINAL' if vmax <= 0 or vmin >= vmax * 0.80 else 'CAUTION')
            self._h_pwr.add_metric('Min V', f'{vmin:.2f}', 'V')
            self._h_pwr.add_metric('Max I', f'{curr:.1f}', 'A')
        else:
            self._h_pwr.set_status('NO DATA')

        # Structural — IMU vibration envelope
        imu = data.get('IMU[0]')
        self._h_str.clear_metrics()
        if imu is not None and not imu.empty and 'AccZ' in imu.columns:
            rng = float(imu['AccZ'].max()) - float(imu['AccZ'].min())
            self._h_str.set_status('NOMINAL' if rng < 40 else 'CAUTION')
            self._h_str.add_metric('AccZ range', f'{rng:.1f}', 'm/s²')
        else:
            self._h_str.set_status('NO DATA')

    def _fill_events(self, data: dict):
        while self._events_layout.count():
            item = self._events_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        events = EventExtractor.collect(data)
        shown = sorted(events, key=lambda e: (_SEV_PRIORITY.get(e[1], 9), e[0]))[:8]

        for ts, sev, etype, msg in shown:
            row = QWidget()
            hl = QHBoxLayout(row)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(T.spacing.px8)

            t = QLabel(f'{ts:.3f} s')
            t.setFixedWidth(72)
            t.setStyleSheet(
                f'font-family: {T.font.data}; color: {T.text.muted}; '
                f'font-size: {T.size.xs}px;')

            s = QLabel(sev)
            s.setFixedWidth(56)
            sf = QFont(T.font.brand, T.size.xs); sf.setWeight(T.weight.bold)
            s.setFont(sf)
            s.setStyleSheet(f'color: {_SEV_COLORS.get(sev, T.text.secondary)};')

            m = QLabel(f'[{etype}] {msg}')
            m.setStyleSheet(f'color: {T.text.secondary}; font-size: {T.size.sm}px;')
            m.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

            hl.addWidget(t)
            hl.addWidget(s)
            hl.addWidget(m, 1)
            self._events_layout.addWidget(row)

    def _on_verify(self, result: VerifyResult):
        self._v_badge.set_state(result.state, result.state)
        self._v_algo.setText(result.algo_name if result.algo_name != '—' else '—')
        self._v_chunks.setText(
            f'{result.chain_chunks:,} chunks verified' if result.chain_chunks else '—')
        self._v_detail.setText(result.detail[:80] if result.detail else '')
