import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QCheckBox,
    QListWidget, QListWidgetItem, QFrame, QScrollArea,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor

EVENT_COLORS = {
    'CRITICAL':    '#dc3545',
    'ERROR':       '#fd7e14',
    'WARNING':     '#ffc107',
    'INFO':        '#4a90d9',
    'MODE_CHANGE': '#9932cc',
    'ARM':         '#28a745',
    'DISARM':      '#6c757d',
}

CATEGORY_LABELS = [
    ('CRITICAL',    'CRITICAL'),
    ('ERROR',       'ERROR'),
    ('WARNING',     'WARNING'),
    ('INFO',        'INFO'),
    ('MODE_CHANGE', 'MODE CHANGES'),
    ('ARM',         'ARM/DISARM'),
]


def _event_category(etype: str, severity: str, msg: str) -> str:
    if etype == 'MODE':
        return 'MODE_CHANGE'
    if etype == 'ARM':
        msg_lc = msg.lower()
        return 'DISARM' if 'disarm' in msg_lc else 'ARM'
    return severity


class EventOverlayPanel(QWidget):
    event_clicked              = pyqtSignal(float)        # relative timestamp
    severity_visibility_changed = pyqtSignal(str, bool)   # category, visible
    event_visibility_changed   = pyqtSignal(int, bool)    # index, visible

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(155)
        self.setStyleSheet('background: #13131f; color: #e0e0e0;')

        outer = QHBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(8)

        # ── Left: category checkboxes ─────────────────────────────────────────
        left = QWidget()
        left.setFixedWidth(175)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(2)

        hdr = QLabel('Event Overlays:')
        hdr.setStyleSheet('font-size: 11px; font-weight: bold; color: #adb5bd;')
        lv.addWidget(hdr)

        self._cat_checks: dict[str, QCheckBox] = {}
        for cat, label in CATEGORY_LABELS:
            cb = QCheckBox(label)
            cb.setChecked(True)
            color = EVENT_COLORS.get(cat, '#e0e0e0')
            cb.setStyleSheet(f'color: {color}; font-size: 10px;')
            cb.stateChanged.connect(
                lambda state, c=cat: self.severity_visibility_changed.emit(c, bool(state))
            )
            self._cat_checks[cat] = cb
            lv.addWidget(cb)

        # ARM also controls DISARM visibility (share the same checkbox)
        lv.addStretch()
        outer.addWidget(left)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet('color: #343a40;')
        outer.addWidget(sep)

        # ── Right: individual event list ──────────────────────────────────────
        self._list = QListWidget()
        self._list.setStyleSheet(
            'QListWidget { background: #1e1e2e; border: none; font-size: 10px; }'
            'QListWidget::item { padding: 1px 4px; }'
            'QListWidget::item:hover { background: #2a2a3e; }'
            'QListWidget::item:selected { background: #3a3a5e; }'
        )
        self._list.itemClicked.connect(self._on_item_clicked)
        self._list.itemChanged.connect(self._on_item_changed)
        outer.addWidget(self._list, 1)

        self._events: list[dict] = []

    def set_events(self, events: list):
        """events: list of (rel_ts: float, severity: str, etype: str, msg: str)"""
        self._list.blockSignals(True)
        self._list.clear()
        self._events = []

        for idx, (ts, sev, etype, msg) in enumerate(events):
            cat = _event_category(etype, sev, msg)
            color = EVENT_COLORS.get(cat, EVENT_COLORS.get(sev, '#e0e0e0'))
            short = msg[:50] if msg else ''
            text = f't={ts:6.2f}s  {etype:<6}  {short}'
            item = QListWidgetItem(text)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setForeground(QColor(color))
            item.setData(Qt.ItemDataRole.UserRole, idx)
            self._list.addItem(item)
            self._events.append({'ts': ts, 'cat': cat, 'sev': sev, 'etype': etype,
                                  'msg': msg, 'visible': True})

        self._list.blockSignals(False)

    def _on_item_clicked(self, item: QListWidgetItem):
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is not None and idx < len(self._events):
            self.event_clicked.emit(self._events[idx]['ts'])

    def _on_item_changed(self, item: QListWidgetItem):
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is not None and idx < len(self._events):
            visible = item.checkState() == Qt.CheckState.Checked
            self._events[idx]['visible'] = visible
            self.event_visibility_changed.emit(idx, visible)

    def get_category_visible(self, cat: str) -> bool:
        cb = self._cat_checks.get(cat)
        return cb.isChecked() if cb else True
