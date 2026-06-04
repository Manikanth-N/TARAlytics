"""
CursorDock — the persistent right-side context surface (Step 4.3).

Always visible across every module so numeric context never requires switching
screens. Three stacked pieces, all driven by the shared cursor:

  CursorContextPanel   flight # · time · phase · mode · AGL · speed · GPS · sats · verify
      AttitudeMatrix   Roll/Pitch/Yaw × Pilot / Demand / Actual (immediate diagnosis)
  ValuesAtCursorTable  configurable raw-signal watchlist; one SampleService.batch();
                       provenance on hover

Reads everything through the AppState shared services (sample_service / timeline_model
/ rc_model) and follows AppState.cursor_time_changed. No surface recomputes data the
others already have on the hot path.
"""
from __future__ import annotations
from dataclasses import dataclass

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QFrame, QHeaderView,
    QTableWidget, QTableWidgetItem, QSizePolicy, QAbstractItemView, QPushButton,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor

from ui.design.tokens import T
from core.health_analyzer import GPS_FIX_NAMES
from core import diagnostics


# ── altitude / gps source resolution (documented hierarchy, via SampleService) ─
_AGL_SOURCES = [('POS', 'RelHomeAlt'), ('BARO[0]', 'Alt'), ('BARO', 'Alt'),
                ('POS', 'Alt')]
_GPS_KEYS = ('GPS[0]', 'GPS')
_DIVERGE_WARN = 8.0     # deg |demand-actual| → caution
_DIVERGE_CRIT = 20.0    # deg → critical


def _angle_diff(a: float, b: float) -> float:
    """Smallest signed difference a-b on a circle (handles yaw wrap)."""
    return ((a - b + 180.0) % 360.0) - 180.0


def _mono(size=T.size.sm, weight=T.weight.regular) -> QFont:
    f = QFont(T.font.data, size); f.setWeight(weight); return f


def _brand(size=T.size.sm, weight=T.weight.semibold) -> QFont:
    f = QFont(T.font.brand, size); f.setWeight(weight); return f


def _caption(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    f = _brand(T.size.xs, T.weight.bold)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.8)
    lbl.setFont(f)
    lbl.setStyleSheet(f'color: {T.text.muted};')
    return lbl


def _divider() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet(f'color: {T.border.subtle}; background: {T.border.subtle};')
    line.setFixedHeight(1)
    return line


# ── Attitude matrix ───────────────────────────────────────────────────────────

class AttitudeMatrix(QWidget):
    """Roll/Pitch/Yaw/Throttle × Pilot / Demand / Actual + Δ. The diagnosis grid:
    who commanded what (pilot stick), what the controller asked for (demand), what
    the aircraft did (actual), and the explicit divergence magnitude (Δ), colour-
    flagged. Throttle compares pilot stick / controller throttle (CTUN.ThO) / motor
    output (RCOU)."""

    # (symbol, axis, kind) — kind 'angle' uses ATT.Des*/ATT.*; 'throttle' uses
    # pilot stick / CTUN.ThO / servo output, all 0..1.
    _ROWS = [('R', 'roll', 'angle'), ('P', 'pitch', 'angle'),
             ('Y', 'yaw', 'angle'), ('T', 'throttle', 'throttle')]
    _ANGLE_COLS = {'roll': ('DesRoll', 'Roll'), 'pitch': ('DesPitch', 'Pitch'),
                   'yaw': ('DesYaw', 'Yaw')}
    _THR_WARN, _THR_CRIT = 0.10, 0.25

    def __init__(self, app_state, parent=None):
        super().__init__(parent)
        self._app = app_state
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(T.spacing.px4)
        grid.setVerticalSpacing(3)

        for c, head in enumerate(('', 'PILOT', 'DEMAND', 'ACTUAL', 'Δ')):
            lbl = QLabel(head)
            lbl.setFont(_brand(T.size.xs, T.weight.bold))
            lbl.setStyleSheet(f'color: {T.text.muted};')
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight if c else Qt.AlignmentFlag.AlignLeft)
            grid.addWidget(lbl, 0, c)

        self._cells: dict = {}
        for r, (sym, axis, _kind) in enumerate(self._ROWS, start=1):
            ax = QLabel(sym)
            ax.setFont(_brand(T.size.md, T.weight.bold))
            ax.setStyleSheet(f'color: {T.text.secondary};')
            grid.addWidget(ax, r, 0)
            for c, kind in enumerate(('pilot', 'demand', 'actual', 'delta'), start=1):
                v = QLabel('—')
                v.setFont(_mono(T.size.xs if kind == 'delta' else T.size.sm))
                v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                v.setStyleSheet(f'color: {T.text.data};')
                grid.addWidget(v, r, c)
                self._cells[(axis, kind)] = v
        for c in (1, 2, 3):
            grid.setColumnStretch(c, 1)

    def refresh(self, t: float):
        svc = self._app.sample_service
        rc = self._app.rc_model
        if svc is None:
            self._blank(); return
        pilot = rc.pilot_input(svc, t) if rc is not None else None
        servo = rc.servo_output(svc, t) if rc is not None else None
        for sym, axis, kind in self._ROWS:
            if kind == 'angle':
                self._refresh_angle(svc, pilot, axis, t)
            else:
                self._refresh_throttle(svc, pilot, servo, axis, t)

    def _refresh_angle(self, svc, pilot, axis, t):
        des_col, act_col = self._ANGLE_COLS[axis]
        pv = getattr(pilot, axis, None) if pilot is not None else None
        dv = svc.value_at('ATT', des_col, t)
        av = svc.value_at('ATT', act_col, t)
        self._cells[(axis, 'pilot')].setText('—' if pv is None else f'{pv:+.2f}')
        self._cells[(axis, 'demand')].setText('—' if dv is None else f'{dv:+.0f}°')
        self._cells[(axis, 'actual')].setText('—' if av is None else f'{av:+.0f}°')
        diff = abs(_angle_diff(av, dv)) if (dv is not None and av is not None) else None
        self._set_delta(axis, diff, '{:.0f}°', _DIVERGE_WARN, _DIVERGE_CRIT)

    def _refresh_throttle(self, svc, pilot, servo, axis, t):
        pv = getattr(pilot, 'throttle', None) if pilot is not None else None
        av = getattr(servo, 'throttle', None) if servo is not None else None
        dv = svc.value_at('CTUN', 'ThO', t)   # controller throttle 0..1
        self._cells[(axis, 'pilot')].setText('—' if pv is None else f'{pv:.2f}')
        self._cells[(axis, 'demand')].setText('—' if dv is None else f'{dv:.2f}')
        self._cells[(axis, 'actual')].setText('—' if av is None else f'{av:.2f}')
        diff = abs(dv - av) if (dv is not None and av is not None) else None
        self._set_delta(axis, diff, '{:.2f}', self._THR_WARN, self._THR_CRIT)

    def _set_delta(self, axis, diff, fmt, warn, crit):
        cell = self._cells[(axis, 'delta')]
        act = self._cells[(axis, 'actual')]
        if diff is None:
            cell.setText('—'); colour = T.text.muted
        else:
            cell.setText(fmt.format(diff))
            colour = (T.status.critical if diff >= crit
                      else T.status.caution if diff >= warn else T.status.nominal)
        cell.setStyleSheet(f'color: {colour};')
        act.setStyleSheet(f'color: {colour if diff is not None and diff >= warn else T.text.data};')

    def _blank(self):
        for (axis, kind), cell in self._cells.items():
            cell.setText('—')
            cell.setStyleSheet(f'color: {T.text.muted if kind == "delta" else T.text.data};')


# ── Context panel ──────────────────────────────────────────────────────────────

class CursorContextPanel(QWidget):
    """Flight-level state at the cursor: flight #, time, phase, mode, AGL, speed,
    GPS status, satellites, verification — plus the AttitudeMatrix. Answers
    'what was happening' without opening a plot."""

    _FIELDS = ['flight', 'time', 'phase', 'mode', 'alt', 'vspeed', 'speed',
               'gps', 'sats', 'ekf', 'posdiv', 'verify']
    _LABELS = {'flight': 'Flight', 'time': 'Time', 'phase': 'Phase', 'mode': 'Mode',
               'alt': 'Alt AGL', 'vspeed': 'V.Speed', 'speed': 'Speed',
               'gps': 'GPS', 'sats': 'Sats', 'ekf': 'EKF', 'posdiv': 'Pos Div',
               'verify': 'Verify'}
    _STATE_COLOR = {'OK': '', 'CAUTION': T.status.caution, 'CRITICAL': T.status.critical}

    def __init__(self, app_state, parent=None):
        super().__init__(parent)
        self._app = app_state
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(T.spacing.px8)

        root.addWidget(_caption('Cursor Context'))
        grid = QGridLayout()
        grid.setHorizontalSpacing(T.spacing.px12)
        grid.setVerticalSpacing(4)
        self._vals: dict = {}
        for i, key in enumerate(self._FIELDS):
            r, c = divmod(i, 2)
            cap = QLabel(self._LABELS[key])
            cap.setFont(_brand(T.size.xs, T.weight.semibold))
            cap.setStyleSheet(f'color: {T.text.muted};')
            val = QLabel('—')
            val.setFont(_mono(T.size.sm, T.weight.semibold))
            val.setStyleSheet(f'color: {T.text.primary};')
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            box = QVBoxLayout(); box.setSpacing(0)
            box.addWidget(cap); box.addWidget(val)
            holder = QWidget(); holder.setLayout(box)
            grid.addWidget(holder, r, c)
            self._vals[key] = val
        root.addLayout(grid)

        root.addWidget(_divider())
        root.addWidget(_caption('Pilot · Controller · Aircraft'))
        self._matrix = AttitudeMatrix(self._app)
        root.addWidget(self._matrix)

        app_state.verification_changed.connect(lambda *_: self._refresh_verify())

    # -- data resolution --

    def _gps_msg(self):
        data = self._app.data
        return next((k for k in _GPS_KEYS if k in data), None)

    def _agl(self, t: float):
        svc = self._app.sample_service
        data = self._app.data
        for msg, col in _AGL_SOURCES:
            if msg in data:
                v = svc.value_at(msg, col, t)
                if v is not None:
                    return v, f'{msg}.{col}'
        return None, None

    def refresh(self, t: float):
        svc = self._app.sample_service
        tm = self._app.timeline_model
        data = self._app.data
        v = self._vals
        v['time'].setText(f'{t:.2f} s')
        if svc is None or tm is None:
            for k in ('flight', 'phase', 'mode', 'alt', 'vspeed', 'speed',
                      'gps', 'sats', 'ekf', 'posdiv'):
                v[k].setText('—'); v[k].setStyleSheet(f'color: {T.text.primary};')
            self._matrix._blank()
            self._refresh_verify()
            return

        # flight #
        flights = tm.flight_windows()
        idx = next((f.index for f in flights if f.contains(t)), None)
        v['flight'].setText(
            f'{idx + 1} / {len(flights)}' if idx is not None
            else (f'— / {len(flights)}' if flights else '—'))

        # phase / mode
        ph = tm.phase_at(t); v['phase'].setText(ph.kind if ph else '—')
        md = tm.mode_at(t); v['mode'].setText(md or '—')

        # altitude AGL
        alt, _src = self._agl(t)
        v['alt'].setText('—' if alt is None else f'{alt:.1f} m')

        # speed (GPS ground speed)
        gmsg = self._gps_msg()
        spd = svc.value_at(gmsg, 'Spd', t) if gmsg else None
        v['speed'].setText('—' if spd is None else f'{spd:.1f} m/s')

        # GPS status + sats
        if gmsg:
            st = svc.latest_at(gmsg, 'Status', t)
            sats = svc.latest_at(gmsg, 'NSats', t)
            v['gps'].setText(GPS_FIX_NAMES.get(int(st), f'FIX_{int(st)}')
                             if st is not None else '—')
            v['sats'].setText('—' if sats is None else str(int(sats)))
        else:
            v['gps'].setText('SITL' if 'SIM2' in self._app.data else '—')
            v['sats'].setText('—')

        # diagnostic aids: vertical speed, EKF health, position divergence
        vs = diagnostics.vertical_speed_at(svc, data, t)
        v['vspeed'].setText('—' if vs['value'] is None else f'{vs["value"]:+.1f} m/s')
        ekf = diagnostics.ekf_status_at(svc, data, t)
        self._set_indicator('ekf', ekf['state'] if ekf['ratio'] is not None else '—',
                            ekf['state'])
        pd = diagnostics.position_divergence_at(svc, data, t)
        self._set_indicator('posdiv',
                            '—' if pd['value'] is None else f'{pd["value"]:.1f} m',
                            pd['state'])

        self._matrix.refresh(t)
        self._refresh_verify()

    def _set_indicator(self, key: str, text: str, state: str):
        lbl = self._vals[key]
        lbl.setText(text)
        colour = self._STATE_COLOR.get(state) or T.text.primary
        lbl.setStyleSheet(f'color: {colour};')

    def _refresh_verify(self):
        state = getattr(self._app.verification, 'state', 'NOT_LOADED')
        lbl = self._vals['verify']
        lbl.setText(state.replace('_', ' '))
        colour = {
            'VERIFIED': T.status.nominal,
            'STRUCTURE_ERROR': T.status.caution, 'TRUNCATED': T.status.caution,
            'NOT_LOADED': T.text.muted, 'NOT_SIGNED': T.text.muted, '': T.text.muted,
        }.get(state, T.status.critical)
        lbl.setStyleSheet(f'color: {colour};')


# ── Values-at-cursor table ─────────────────────────────────────────────────────

@dataclass
class RowSpec:
    label: str
    msg: str
    col: str
    unit: str = ''
    fmt: str = '{:+.2f}'


# Default watchlist: complements the context panel / matrix rather than repeating
# them — power, motor outputs, and vibration (the raw engineering signals not
# surfaced above). Fully reconfigurable via set_rows().
DEFAULT_ROWS = [
    RowSpec('BAT Volt', 'BAT', 'Volt', 'V', '{:.2f}'),
    RowSpec('BAT Curr', 'BAT', 'Curr', 'A', '{:.1f}'),
    RowSpec('Motor 1', 'RCOU', 'C1', '', '{:.0f}'),
    RowSpec('Motor 2', 'RCOU', 'C2', '', '{:.0f}'),
    RowSpec('Motor 3', 'RCOU', 'C3', '', '{:.0f}'),
    RowSpec('Motor 4', 'RCOU', 'C4', '', '{:.0f}'),
    RowSpec('IMU AccZ', 'IMU[0]', 'AccZ', 'm/s²', '{:.1f}'),
    RowSpec('Vibe Z', 'VIBE', 'VibeZ', '', '{:.1f}'),
]


class ValuesAtCursorTable(QWidget):
    """Authoritative raw-signal readout. One SampleService.batch() per cursor move
    (no per-row sampling); '—' when out of range (never fabricated). Hover a value
    for its provenance (source field, sample time, interpolated yes/no)."""

    def __init__(self, app_state, parent=None):
        super().__init__(parent)
        self._app = app_state
        self._rows: list[RowSpec] = []
        self._t = 0.0

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(T.spacing.px4)
        self._header = _caption('Values @ —')
        root.addWidget(self._header)

        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(['SIGNAL', 'VALUE'])
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._table.setShowGrid(False)
        self._table.setMouseTracking(True)
        self._table.cellEntered.connect(self._on_hover)
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setFont(_brand(T.size.xs, T.weight.bold))
        self._table.setStyleSheet(
            f'QTableWidget {{ background: {T.surface.card}; border: none; '
            f'gridline-color: {T.border.subtle}; }} '
            f'QHeaderView::section {{ background: {T.surface.elevated}; '
            f'color: {T.text.muted}; border: none; padding: 2px 4px; }}'
        )
        self._table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addWidget(self._table, 1)

        self.set_rows(DEFAULT_ROWS)

    def set_rows(self, rows: list[RowSpec]):
        """Configure the watchlist. Pre-creates items once; refresh() only updates
        value text, so continuous scrubbing stays allocation-free."""
        self._rows = list(rows)
        self._table.setRowCount(len(rows))
        for i, spec in enumerate(rows):
            name = QTableWidgetItem(spec.label)
            name.setFont(_brand(T.size.sm))
            name.setForeground(QColor(T.text.secondary))
            name.setFlags(Qt.ItemFlag.ItemIsEnabled)
            val = QTableWidgetItem('—')
            val.setFont(_mono(T.size.sm))
            val.setForeground(QColor(T.text.data))
            val.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            val.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self._table.setItem(i, 0, name)
            self._table.setItem(i, 1, val)
        self._table.resizeRowsToContents()

    def refresh(self, t: float):
        self._t = t
        self._header.setText(f'VALUES @ {t:.2f} S')
        svc = self._app.sample_service
        if svc is None:
            for i in range(len(self._rows)):
                self._table.item(i, 1).setText('—')
            return
        # ONE batch call for the whole table (continuous signals).
        specs = [(r.label, r.msg, r.col) for r in self._rows]
        result = svc.batch(t, specs)
        for i, spec in enumerate(self._rows):
            v = result.get(spec.label)
            item = self._table.item(i, 1)
            if v is None:
                item.setText('—')
                item.setForeground(QColor(T.text.muted))
            else:
                txt = spec.fmt.format(v)
                if spec.unit:
                    txt += f' {spec.unit}'
                item.setText(txt)
                item.setForeground(QColor(T.text.data))

    def _on_hover(self, row: int, col: int):
        """Provenance tooltip — one sample_at for the hovered row only (cold path,
        not part of the per-frame batch)."""
        if not (0 <= row < len(self._rows)):
            return
        svc = self._app.sample_service
        if svc is None:
            return
        spec = self._rows[row]
        s = svc.sample_at(spec.msg, spec.col, self._t)
        if not s.ok:
            tip = f'{spec.msg}.{spec.col} — no data at {self._t:.2f} s'
        elif s.interpolated and s.bracket:
            tip = (f'{spec.msg}.{spec.col} = {s.value:.4f}\n'
                   f'interpolated between {s.bracket[0]:.3f}–{s.bracket[1]:.3f} s '
                   f'(query {self._t:.3f} s)')
        else:
            tip = (f'{spec.msg}.{spec.col} = {s.value:.4f}\n'
                   f'exact sample @ {s.sample_t:.3f} s')
        item = self._table.item(row, col)
        if item is not None:
            item.setToolTip(tip)


# ── The dock ───────────────────────────────────────────────────────────────────

class CursorDock(QWidget):
    """Persistent right-side context surface. One subscriber to the shared cursor;
    fans the move out to the context panel (incl. matrix) and the values table."""

    def __init__(self, app_state, parent=None):
        super().__init__(parent)
        self._app = app_state
        self.setFixedWidth(300)
        self.setStyleSheet(f'background: {T.surface.panel};')

        root = QVBoxLayout(self)
        root.setContentsMargins(T.spacing.px12, T.spacing.px12,
                                T.spacing.px12, T.spacing.px12)
        root.setSpacing(T.spacing.px8)

        # Snapshot action (placeholder — captures the cursor moment; export TBD).
        snap_row = QHBoxLayout(); snap_row.setSpacing(T.spacing.px8)
        self._snap_btn = QPushButton('★ Snapshot')
        self._snap_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._snap_btn.setToolTip('Capture an Investigation Snapshot at the cursor '
                                  '(manage & export in the Evidence module)')
        self._snap_btn.setStyleSheet(
            f'QPushButton {{ background: {T.surface.card}; color: {T.brand.blue_bright}; '
            f'border: 1px solid {T.border.active}; border-radius: 3px; '
            f'padding: 3px 10px; font-family: {T.font.brand}; '
            f'font-size: {T.size.sm}px; font-weight: {T.weight.semibold}; }} '
            f'QPushButton:hover {{ background: {T.surface.elevated}; }}')
        self._snap_btn.clicked.connect(self._on_snapshot)
        self._snap_status = QLabel('')
        self._snap_status.setFont(_mono(T.size.xs))
        self._snap_status.setStyleSheet(f'color: {T.text.muted};')
        snap_row.addWidget(self._snap_btn)
        snap_row.addWidget(self._snap_status, 1)
        root.addLayout(snap_row)

        self._context = CursorContextPanel(app_state)
        root.addWidget(self._context)
        root.addWidget(_divider())
        self._values = ValuesAtCursorTable(app_state)
        root.addWidget(self._values, 1)

        app_state.connect_cursor(self._refresh, 'CursorDock')
        app_state.data_changed.connect(lambda *_: self._refresh(app_state.cursor_time))

    def _refresh(self, t: float):
        self._context.refresh(t)
        self._values.refresh(t)

    def _on_snapshot(self):
        """Capture an Investigation Snapshot at the current cursor (P2)."""
        snap = self._app.capture_snapshot()
        if snap is None:
            self._snap_status.setText('no log loaded')
            return
        self._snap_status.setText(
            f'#{snap.index} @ {snap.cursor_time:.2f}s captured · {len(self._app.snapshots)} total')

    # exposed for tests
    @property
    def context(self) -> CursorContextPanel:
        return self._context

    @property
    def values(self) -> ValuesAtCursorTable:
        return self._values
