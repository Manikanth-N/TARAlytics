"""
EvidenceModule — Investigation Snapshot management + evidence export (P2).

Lists the session's captured snapshots, shows a selected snapshot's full detail,
lets the engineer edit notes / status / delete, and exports the whole set as JSON,
Markdown, or PDF. Selecting a snapshot returns the shared cursor to that moment, so
captured findings stay live and re-investigable.

PDF is produced with Qt's QTextDocument → QPdfWriter (no extra dependency); JSON and
Markdown come from the pure-core core.evidence_export.
"""
from __future__ import annotations
import os

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QTextBrowser, QComboBox,
    QLineEdit, QFileDialog, QSplitter,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QTextDocument, QPdfWriter, QPageSize

from ui.design.tokens import T
from ui.app_state import AppState
from ui.widgets.module_header import ModuleHeader
from core import evidence_export as ex

_STATUS = ['OPEN', 'REVIEWED', 'FLAGGED']
_STATUS_COLOR = {'OPEN': T.text.muted, 'REVIEWED': T.status.nominal,
                 'FLAGGED': T.status.critical}
_MD_GH = QTextDocument.MarkdownFeature.MarkdownDialectGitHub


def export_pdf(markdown: str, path: str, title: str = 'TARAlytics Evidence'):
    """Render a Markdown evidence report to PDF via Qt (no external PDF lib)."""
    writer = QPdfWriter(path)
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setTitle(title)
    doc = QTextDocument()
    doc.setMarkdown(markdown, _MD_GH)
    doc.print(writer)


def _btn(text: str, primary=False) -> QPushButton:
    b = QPushButton(text); b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFixedHeight(24)
    fg = T.brand.blue_bright if primary else T.text.secondary
    b.setStyleSheet(
        f'QPushButton {{ background: {T.surface.card}; color: {fg}; '
        f'border: 1px solid {T.border.default if not primary else T.border.active}; '
        f'border-radius: 3px; padding: 2px 10px; font-family: {T.font.brand}; '
        f'font-size: {T.size.sm}px; font-weight: {T.weight.semibold}; }} '
        f'QPushButton:hover {{ color: {T.brand.blue_bright}; border-color: {T.border.active}; }}')
    return b


class EvidenceModule(QWidget):
    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self._app = app_state
        self._setup_ui()
        app_state.snapshots_changed.connect(self._refresh_list)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        header = ModuleHeader('Evidence')
        self._b_capture = _btn('★ Capture', primary=True)
        self._b_json = _btn('Export JSON')
        self._b_md = _btn('Export Markdown')
        self._b_pdf = _btn('Export PDF')
        self._b_clear = _btn('Clear All')
        for b in (self._b_capture, self._b_json, self._b_md, self._b_pdf, self._b_clear):
            header.add_action(b)
        root.addWidget(header)

        split = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(split, 1)

        # left: snapshot list
        left = QWidget(); ll = QVBoxLayout(left)
        ll.setContentsMargins(T.spacing.px12, T.spacing.px12, T.spacing.px8, T.spacing.px12)
        ll.setSpacing(T.spacing.px8)
        self._count = QLabel('No snapshots')
        self._count.setStyleSheet(f'color: {T.text.muted}; font-size: {T.size.sm}px;')
        ll.addWidget(self._count)
        self._list = QTableWidget(0, 4)
        self._list.setHorizontalHeaderLabels(['#', 'Time (s)', 'Event', 'Status'])
        self._list.verticalHeader().setVisible(False)
        self._list.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        h = self._list.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._list.setStyleSheet(
            f'QTableWidget {{ background: {T.surface.card}; color: {T.text.data}; '
            f'gridline-color: {T.border.subtle}; border: none; font-size: {T.size.sm}px; }} '
            f'QTableWidget::item:selected {{ background: {T.border.active}; color: {T.brand.white}; }} '
            f'QHeaderView::section {{ background: {T.surface.elevated}; color: {T.text.muted}; '
            f'border: none; padding: 4px 6px; font-weight: bold; }}')
        ll.addWidget(self._list, 1)
        split.addWidget(left)

        # right: detail + per-snapshot edit
        right = QWidget(); rl = QVBoxLayout(right)
        rl.setContentsMargins(T.spacing.px8, T.spacing.px12, T.spacing.px12, T.spacing.px12)
        rl.setSpacing(T.spacing.px8)
        edit = QHBoxLayout(); edit.setSpacing(T.spacing.px8)
        edit.addWidget(QLabel('Status'))
        self._status = QComboBox(); self._status.addItems(_STATUS)
        self._status.setStyleSheet(
            f'QComboBox {{ background: {T.surface.card}; color: {T.text.secondary}; '
            f'border: 1px solid {T.border.default}; border-radius: 3px; padding: 2px 8px; }}')
        edit.addWidget(self._status)
        self._notes = QLineEdit(); self._notes.setPlaceholderText('Investigation notes…')
        self._notes.setStyleSheet(
            f'QLineEdit {{ background: {T.surface.card}; color: {T.text.primary}; '
            f'border: 1px solid {T.border.default}; border-radius: 3px; padding: 3px 8px; }}')
        edit.addWidget(self._notes, 1)
        self._b_delete = _btn('Delete')
        edit.addWidget(self._b_delete)
        rl.addLayout(edit)
        self._detail = QTextBrowser()
        self._detail.setStyleSheet(
            f'QTextBrowser {{ background: {T.surface.base}; color: {T.text.data}; '
            f'border: 1px solid {T.border.subtle}; }}')
        rl.addWidget(self._detail, 1)
        split.addWidget(right)
        split.setSizes([360, 640])

        # wiring
        self._b_capture.clicked.connect(lambda: self._app.capture_snapshot())
        self._b_clear.clicked.connect(self._app.clear_snapshots)
        self._b_json.clicked.connect(lambda: self._export('json'))
        self._b_md.clicked.connect(lambda: self._export('md'))
        self._b_pdf.clicked.connect(lambda: self._export('pdf'))
        self._b_delete.clicked.connect(self._delete_selected)
        self._list.itemSelectionChanged.connect(self._on_select)
        self._status.currentTextChanged.connect(self._on_status_changed)
        self._notes.editingFinished.connect(self._on_notes_changed)
        self._refresh_list()

    # ── list / detail ───────────────────────────────────────────────────────

    def _snaps(self):
        return self._app.snapshots.all()

    def _refresh_list(self):
        snaps = self._snaps()
        self._count.setText(f'{len(snaps)} snapshot{"s" if len(snaps) != 1 else ""}')
        self._list.setRowCount(len(snaps))
        for r, s in enumerate(snaps):
            n = QTableWidgetItem(str(s.index)); n.setForeground(QColor(T.text.muted))
            tm = QTableWidgetItem(f'{s.cursor_time:.2f}')
            ev = QTableWidgetItem(s.title())
            stt = QTableWidgetItem(s.status); stt.setForeground(QColor(_STATUS_COLOR[s.status]))
            f = QFont(T.font.brand, T.size.xs); f.setWeight(T.weight.bold); stt.setFont(f)
            for c, it in ((0, n), (1, tm), (2, ev), (3, stt)):
                it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self._list.setItem(r, c, it)
        has = bool(snaps)
        for b in (self._b_json, self._b_md, self._b_pdf, self._b_clear):
            b.setEnabled(has)
        if not has:
            self._detail.clear()
        else:
            self._list.selectRow(min(self._list.currentRow() if self._list.currentRow() >= 0 else 0,
                                     len(snaps) - 1))

    def _selected_index(self):
        rows = self._list.selectionModel().selectedRows()
        return rows[0].row() if rows else -1

    def _on_select(self):
        i = self._selected_index()
        snaps = self._snaps()
        if not (0 <= i < len(snaps)):
            return
        s = snaps[i]
        self._detail.setMarkdown(ex.to_markdown([s], self._app.evidence_meta()))
        self._status.blockSignals(True); self._status.setCurrentText(s.status); self._status.blockSignals(False)
        self._notes.blockSignals(True); self._notes.setText(s.notes); self._notes.blockSignals(False)
        # re-investigate: return the shared cursor to this moment
        self._app.set_cursor_time(s.cursor_time)

    def _on_status_changed(self, status: str):
        i = self._selected_index(); snaps = self._snaps()
        if 0 <= i < len(snaps):
            snaps[i].status = status
            self._refresh_list_keep(i)

    def _on_notes_changed(self):
        i = self._selected_index(); snaps = self._snaps()
        if 0 <= i < len(snaps):
            snaps[i].notes = self._notes.text()

    def _refresh_list_keep(self, i):
        self._refresh_list()
        if 0 <= i < self._list.rowCount():
            self._list.selectRow(i)

    def _delete_selected(self):
        i = self._selected_index()
        if i >= 0:
            self._app.remove_snapshot(i)

    # ── export ────────────────────────────────────────────────────────────────

    def _export(self, kind: str):
        snaps = self._snaps()
        if not snaps:
            return
        meta = self._app.evidence_meta()
        base = os.path.splitext(os.path.basename(meta.get('log_path') or 'flight'))[0]
        default = f'{base}_evidence.{ "md" if kind=="md" else kind }'
        filt = {'json': 'JSON (*.json)', 'md': 'Markdown (*.md)', 'pdf': 'PDF (*.pdf)'}[kind]
        path, _ = QFileDialog.getSaveFileName(self, f'Export evidence ({kind.upper()})',
                                              default, filt)
        if not path:
            return
        if kind == 'json':
            with open(path, 'w') as f:
                f.write(ex.to_json(snaps, meta))
        elif kind == 'md':
            with open(path, 'w') as f:
                f.write(ex.to_markdown(snaps, meta))
        else:
            export_pdf(ex.to_markdown(snaps, meta), path,
                       title=f'TARAlytics Evidence — {base}')
        self._count.setText(f'{len(snaps)} snapshots · exported {os.path.basename(path)}')
