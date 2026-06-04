"""
EventsModule — the Unified Events investigation surface (P1.5).

One authoritative event source (EventExtractor — the same list the Timeline and
Debrief use), made navigable: free-text search, severity + type filters, per-event
notes and review status, prev/next stepping, and jump-to-cursor. Selecting an event
drives the shared cursor (AppState.jump_to_event), so one click updates every other
surface (Timeline, Context, Matrix, Horizon, RC, Map).
"""
from __future__ import annotations
import numpy as np

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont

from ui.design.tokens import T
from ui.app_state import AppState
from ui.widgets.module_header import ModuleHeader
from core.event_extractor import EventExtractor

_SEV_COLOR = {'CRITICAL': T.status.critical, 'ERROR': '#E67E22',
              'WARNING': T.status.caution, 'INFO': T.brand.blue}
_SEV_ORDER = {'CRITICAL': 0, 'ERROR': 1, 'WARNING': 2, 'INFO': 3}
_STATUS_CYCLE = ['OPEN', 'REVIEWED', 'FLAGGED']
_STATUS_COLOR = {'OPEN': T.text.muted, 'REVIEWED': T.status.nominal,
                 'FLAGGED': T.status.critical}

# columns
_C_TIME, _C_SEV, _C_TYPE, _C_MSG, _C_STATUS, _C_NOTES = range(6)


def _tool_button(text: str, tip: str) -> QPushButton:
    b = QPushButton(text); b.setToolTip(tip)
    b.setCursor(Qt.CursorShape.PointingHandCursor); b.setFixedHeight(24)
    b.setStyleSheet(
        f'QPushButton {{ background: {T.surface.card}; color: {T.text.secondary}; '
        f'border: 1px solid {T.border.default}; border-radius: 3px; padding: 2px 9px; '
        f'font-family: {T.font.brand}; font-size: {T.size.sm}px; '
        f'font-weight: {T.weight.semibold}; }} '
        f'QPushButton:hover {{ color: {T.brand.blue_bright}; border-color: {T.border.active}; }}')
    return b


class EventsModule(QWidget):
    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self._app = app_state
        self._events: list = []           # [(t, sev, type, msg)]
        self._times = np.array([])
        self._status: dict = {}           # row -> status str
        self._notes: dict = {}            # row -> note str
        self._programmatic = False        # guard: don't jump on programmatic selection
        self._setup_ui()

        app_state.data_changed.connect(self._on_data)
        app_state.connect_cursor(self._on_cursor, 'EventsModule')

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        header = ModuleHeader('Events')
        self._b_prev = _tool_button('◀ Prev', 'Previous event (before cursor)')
        self._b_next = _tool_button('Next ▶', 'Next event (after cursor)')
        self._b_jump = _tool_button('⌖ At Cursor', 'Select the event nearest the cursor')
        for b in (self._b_prev, self._b_next, self._b_jump):
            header.add_action(b)
        root.addWidget(header)

        bar = QHBoxLayout()
        bar.setContentsMargins(T.spacing.px12, T.spacing.px8, T.spacing.px12, T.spacing.px8)
        bar.setSpacing(T.spacing.px8)
        self._search = QLineEdit(); self._search.setPlaceholderText('Search message / type…')
        self._search.setClearButtonEnabled(True)
        self._search.setStyleSheet(
            f'QLineEdit {{ background: {T.surface.card}; color: {T.text.primary}; '
            f'border: 1px solid {T.border.default}; border-radius: 3px; padding: 3px 8px; '
            f'font-size: {T.size.sm}px; }} '
            f'QLineEdit:focus {{ border-color: {T.border.active}; }}')
        self._sev = QComboBox(); self._sev.addItems(['All severities', 'CRITICAL', 'ERROR', 'WARNING', 'INFO'])
        self._type = QComboBox(); self._type.addItem('All types')
        for cb in (self._sev, self._type):
            cb.setStyleSheet(
                f'QComboBox {{ background: {T.surface.card}; color: {T.text.secondary}; '
                f'border: 1px solid {T.border.default}; border-radius: 3px; padding: 2px 8px; '
                f'font-size: {T.size.sm}px; }}')
        self._count = QLabel('—')
        self._count.setStyleSheet(f'color: {T.text.muted}; font-size: {T.size.sm}px;')
        bar.addWidget(self._search, 1)
        bar.addWidget(self._sev); bar.addWidget(self._type); bar.addWidget(self._count)
        root.addLayout(bar)

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ['Time (s)', 'Severity', 'Type', 'Message', 'Status', 'Notes'])
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        hh = self._table.horizontalHeader()
        for c in (_C_TIME, _C_SEV, _C_TYPE, _C_STATUS):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(_C_MSG, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(_C_NOTES, QHeaderView.ResizeMode.Interactive)
        self._table.setColumnWidth(_C_NOTES, 160)
        self._table.setStyleSheet(
            f'QTableWidget {{ background: {T.surface.card}; color: {T.text.data}; '
            f'gridline-color: {T.border.subtle}; border: none; font-size: {T.size.sm}px; }} '
            f'QTableWidget::item:selected {{ background: {T.border.active}; color: {T.brand.white}; }} '
            f'QHeaderView::section {{ background: {T.surface.elevated}; color: {T.text.muted}; '
            f'border: none; padding: 4px 6px; font-weight: bold; }}')
        root.addWidget(self._table, 1)

        # wiring
        self._search.textChanged.connect(self._apply_filters)
        self._sev.currentIndexChanged.connect(self._apply_filters)
        self._type.currentIndexChanged.connect(self._apply_filters)
        self._table.itemSelectionChanged.connect(self._on_selection)
        self._table.cellClicked.connect(self._on_cell_clicked)
        self._table.itemChanged.connect(self._on_item_changed)
        self._b_prev.clicked.connect(lambda: self._step(-1))
        self._b_next.clicked.connect(lambda: self._step(+1))
        self._b_jump.clicked.connect(lambda: self._select_nearest(self._app.cursor_time))

    # ── data ──────────────────────────────────────────────────────────────────

    def _on_data(self, data: dict):
        self._events = EventExtractor.collect(data)
        self._times = np.array([e[0] for e in self._events], dtype=float)
        self._status = {i: 'OPEN' for i in range(len(self._events))}
        self._notes = {}
        # populate type filter
        self._type.blockSignals(True)
        self._type.clear(); self._type.addItem('All types')
        for ty in sorted({e[2] for e in self._events}):
            self._type.addItem(ty)
        self._type.blockSignals(False)
        self._build_rows()

    def _build_rows(self):
        self._programmatic = True
        self._table.setRowCount(len(self._events))
        for i, (ts, sev, ty, msg) in enumerate(self._events):
            t_item = QTableWidgetItem(f'{ts:.3f}')
            t_item.setData(Qt.ItemDataRole.UserRole, ts)
            t_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)

            s_item = QTableWidgetItem(sev)
            s_item.setForeground(QColor(_SEV_COLOR.get(sev, T.text.secondary)))
            f = QFont(T.font.brand, T.size.xs); f.setWeight(T.weight.bold); s_item.setFont(f)
            s_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)

            ty_item = QTableWidgetItem(ty)
            ty_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            m_item = QTableWidgetItem(msg)
            m_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)

            st = self._status.get(i, 'OPEN')
            st_item = QTableWidgetItem(st)
            st_item.setForeground(QColor(_STATUS_COLOR[st]))
            st_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)

            n_item = QTableWidgetItem(self._notes.get(i, ''))
            n_item.setForeground(QColor(T.text.secondary))
            # Notes editable (double-click)
            n_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                            | Qt.ItemFlag.ItemIsEditable)

            for c, it in ((_C_TIME, t_item), (_C_SEV, s_item), (_C_TYPE, ty_item),
                          (_C_MSG, m_item), (_C_STATUS, st_item), (_C_NOTES, n_item)):
                self._table.setItem(i, c, it)
        self._programmatic = False
        self._apply_filters()

    # ── filters ────────────────────────────────────────────────────────────────

    def _apply_filters(self, *_):
        q = self._search.text().strip().lower()
        sev = self._sev.currentText()
        ty = self._type.currentText()
        shown = 0
        for i, (ts, esev, etype, msg) in enumerate(self._events):
            ok = True
            if sev != 'All severities' and esev != sev:
                ok = False
            if ok and ty != 'All types' and etype != ty:
                ok = False
            if ok and q and q not in msg.lower() and q not in etype.lower():
                ok = False
            self._table.setRowHidden(i, not ok)
            shown += ok
        self._count.setText(f'{shown} / {len(self._events)}')

    # ── interaction ────────────────────────────────────────────────────────────

    def _on_selection(self):
        if self._programmatic:
            return
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return
        i = rows[0].row()
        ts = self._table.item(i, _C_TIME).data(Qt.ItemDataRole.UserRole)
        if ts is not None:
            self._app.jump_to_event(float(ts))     # drives the shared cursor

    def _on_cell_clicked(self, row: int, col: int):
        if col == _C_STATUS:
            cur = self._status.get(row, 'OPEN')
            nxt = _STATUS_CYCLE[(_STATUS_CYCLE.index(cur) + 1) % len(_STATUS_CYCLE)]
            self._status[row] = nxt
            it = self._table.item(row, _C_STATUS)
            it.setText(nxt); it.setForeground(QColor(_STATUS_COLOR[nxt]))

    def _on_item_changed(self, item: QTableWidgetItem):
        if self._programmatic or item.column() != _C_NOTES:
            return
        self._notes[item.row()] = item.text()

    def _step(self, direction: int):
        if self._times.size == 0:
            return
        t = self._app.cursor_time
        if direction > 0:
            later = np.where(self._times > t + 1e-6)[0]
            idx = int(later[0]) if later.size else None
        else:
            earlier = np.where(self._times < t - 1e-6)[0]
            idx = int(earlier[-1]) if earlier.size else None
        if idx is None:
            return
        self._select_row(idx, jump=True)

    def _select_nearest(self, t: float):
        if self._times.size == 0:
            return
        idx = int(np.argmin(np.abs(self._times - t)))
        self._select_row(idx, jump=True)

    def _on_cursor(self, t: float):
        """Follow the shared cursor: highlight the nearest event without re-jumping."""
        if self._times.size == 0:
            return
        idx = int(np.argmin(np.abs(self._times - t)))
        self._select_row(idx, jump=False)

    def _select_row(self, idx: int, jump: bool):
        # jump=True  → leave the selection handler free to drive the cursor.
        # jump=False → programmatic follow; suppress the handler so we don't
        #              re-emit the cursor we're already following.
        self._programmatic = not jump
        if jump and self._table.currentRow() == idx:
            # selection won't change → drive the cursor explicitly
            self._app.jump_to_event(float(self._times[idx]))
        self._table.selectRow(idx)
        self._table.scrollToItem(self._table.item(idx, _C_TIME),
                                 QAbstractItemView.ScrollHint.PositionAtCenter)
        self._programmatic = False
