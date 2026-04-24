from PyQt6.QtWidgets import (
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QLabel,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush


SEVERITY_ORDER = {'CRITICAL': 0, 'ERROR': 1, 'WARNING': 2, 'INFO': 3}

ROW_COLORS = {
    'CRITICAL': QColor(220, 53, 69, 30),
    'ERROR':    QColor(253, 126, 20, 30),
    'WARNING':  QColor(255, 193, 7,  30),
    'INFO':     None,
}

BADGE_COLORS = {
    'CRITICAL': ('#ff4444', '#3a0000'),
    'ERROR':    ('#ff8c00', '#3a1800'),
    'WARNING':  ('#ffc107', '#2a1a00'),
    'INFO':     ('#4a90d9', '#0a1a2a'),
}

MODE_NAMES = {
    0: 'STABILIZE', 1: 'ACRO', 2: 'ALT_HOLD', 3: 'AUTO', 4: 'GUIDED',
    5: 'LOITER', 6: 'RTL', 9: 'LAND', 16: 'POSHOLD', 17: 'BRAKE',
    18: 'THROW', 19: 'AVOID_ADSB', 20: 'GUIDED_NOGPS', 21: 'SMART_RTL',
}

EV_NAMES = {
    10: 'Armed', 11: 'Disarmed', 15: 'Auto_Armed', 16: 'Land_Complete',
    18: 'Not_Landed', 25: 'Set_Home', 26: 'Wrote_EEPROM',
    27: 'Load_Default_Params', 28: 'Pilot_YawSet',
}

ERR_SUBSYS = {
    1: 'Main', 2: 'Radio', 3: 'Compass', 5: 'FailSafe_Radio',
    6: 'FailSafe_Batt', 7: 'FailSafe_GPS', 10: 'FlightMode', 11: 'GPS',
    16: 'EKF_Check', 17: 'FailSafe_EKF', 18: 'Barometer',
}


def _col(df, *names):
    for n in names:
        if n in df.columns:
            return df[n]
    return None


def _make_badge(severity: str) -> QLabel:
    badge = QLabel(severity)
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    fg, bg = BADGE_COLORS.get(severity, ('#888888', '#1a1a1a'))
    badge.setStyleSheet(
        f'QLabel {{ color: {fg}; background-color: {bg}; '
        f'border: 1px solid {fg}; border-radius: 3px; '
        f'padding: 1px 6px; font-size: 10px; font-weight: bold; }}'
    )
    return badge


class EventTable(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(4)
        self.setHorizontalHeaderLabels(['Timestamp (s)', 'Severity', 'Type', 'Message'])
        self.setAlternatingRowColors(False)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSortingEnabled(True)
        hdr = self.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(28)
        self.setStyleSheet("""
            QTableWidget {
                background-color: #12121e;
                alternate-background-color: #1a1a2e;
                gridline-color: #2a2a3e;
                color: #d0d0e8;
                font-size: 12px;
                border: none;
            }
            QTableWidget::item {
                padding: 4px 8px;
                background-color: transparent;
                border: none;
            }
            QTableWidget::item:selected {
                background-color: #2a3a6a;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #1e1e30;
                color: #8888aa;
                font-size: 11px;
                font-weight: bold;
                padding: 5px 8px;
                border: none;
                border-bottom: 2px solid #3a3a5e;
            }
            QScrollBar:vertical {
                background-color: #1a1a2a;
                width: 10px;
                border: none;
            }
            QScrollBar::handle:vertical {
                background-color: #3a3a5a;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)
        self.viewport().setStyleSheet('background-color: #12121e;')
        self._events = []

    def populate(self, data: dict):
        self._events = []
        self._collect_events(data)
        self._events.sort(key=lambda e: e[0])
        self.setSortingEnabled(False)
        self.setRowCount(len(self._events))
        for row, (ts, sev, etype, msg) in enumerate(self._events):
            self._set_row(row, ts, sev, etype, msg)
        self.setSortingEnabled(True)

    def _set_row(self, row: int, ts: float, sev: str, etype: str, msg: str):
        ts_item = QTableWidgetItem(f'{ts:.3f}')
        ts_item.setData(Qt.ItemDataRole.UserRole, ts)
        ts_item.setFlags(ts_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

        type_item = QTableWidgetItem(etype)
        type_item.setFlags(type_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

        msg_item = QTableWidgetItem(msg)
        msg_item.setFlags(msg_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

        color = ROW_COLORS.get(sev)
        for item in (ts_item, type_item, msg_item):
            if color:
                item.setBackground(QBrush(color))

        self.setItem(row, 0, ts_item)
        # Severity as badge widget
        badge = _make_badge(sev)
        self.setCellWidget(row, 1, badge)
        self.setItem(row, 2, type_item)
        self.setItem(row, 3, msg_item)

    def _collect_events(self, data: dict):
        msg_df = data.get('MSG')
        if msg_df is not None and not msg_df.empty:
            ts_col = _col(msg_df, 'TimeS')
            msg_col = _col(msg_df, 'Message', 'Msg')
            if ts_col is not None and msg_col is not None:
                for ts, msg in zip(ts_col, msg_col):
                    msg = str(msg)
                    lo = msg.lower()
                    sev = 'CRITICAL' if any(k in lo for k in ('fail', 'error', 'crash', 'critical')) else 'INFO'
                    self._events.append((float(ts), sev, 'MSG', msg))

        ev_df = data.get('EV')
        if ev_df is not None and not ev_df.empty:
            ts_col = _col(ev_df, 'TimeS')
            id_col = _col(ev_df, 'Id', 'ID', 'id')
            if ts_col is not None and id_col is not None:
                for ts, eid in zip(ts_col, id_col):
                    name = EV_NAMES.get(int(eid), f'EV_{int(eid)}')
                    self._events.append((float(ts), 'INFO', 'EV', name))

        err_df = data.get('ERR')
        if err_df is not None and not err_df.empty:
            ts_col = _col(err_df, 'TimeS')
            sub_col = _col(err_df, 'Subsys', 'SubSys', 'subsys')
            ec_col  = _col(err_df, 'ECode', 'Ecode', 'ecode')
            if ts_col is not None and sub_col is not None and ec_col is not None:
                for ts, sub, ec in zip(ts_col, sub_col, ec_col):
                    sname = ERR_SUBSYS.get(int(sub), f'Subsys_{int(sub)}')
                    self._events.append(
                        (float(ts), 'ERROR', 'ERR', f'ERR: {sname} code={int(ec)}')
                    )

        arm_df = data.get('ARM')
        if arm_df is not None and not arm_df.empty:
            ts_col    = _col(arm_df, 'TimeS')
            state_col = _col(arm_df, 'ArmState', 'Armed', 'State')
            method_col = _col(arm_df, 'Method', 'method')
            if ts_col is not None and state_col is not None:
                for i, (ts, st) in enumerate(zip(ts_col, state_col)):
                    armed = int(st) == 1
                    sev = 'INFO' if armed else 'WARNING'
                    if method_col is not None:
                        m = int(method_col.iloc[i])
                        msg = 'Armed' if armed else f'Disarmed (method={m})'
                    else:
                        msg = 'Armed' if armed else 'Disarmed'
                    self._events.append((float(ts), sev, 'ARM', msg))

        mode_df = data.get('MODE')
        if mode_df is not None and not mode_df.empty:
            ts_col   = _col(mode_df, 'TimeS')
            mode_col = _col(mode_df, 'Mode', 'ModeNum')
            if ts_col is not None and mode_col is not None:
                for ts, m in zip(ts_col, mode_col):
                    name = MODE_NAMES.get(int(m), f'MODE_{int(m)}')
                    self._events.append((float(ts), 'INFO', 'MODE', f'Mode: {name}'))

    def get_events(self):
        return self._events

    def scroll_to_time(self, t: float):
        best_row, best_diff = -1, float('inf')
        for row in range(self.rowCount()):
            item = self.item(row, 0)
            if item:
                ts = item.data(Qt.ItemDataRole.UserRole)
                if ts is not None and abs(float(ts) - t) < best_diff:
                    best_diff = abs(float(ts) - t)
                    best_row = row
        if best_row >= 0:
            self.scrollToItem(self.item(best_row, 0))
            self.selectRow(best_row)
