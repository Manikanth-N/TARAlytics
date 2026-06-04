"""
ModuleVisibilityDialog — show/hide and reorder navigation modules.

A preset selector (Minimal / Flight Test / Full / Custom) sits on top of a checkable,
drag-reorderable list of all modules. Checked = visible; list order = rail order.
Custom layouts can be saved / renamed / deleted; "Restore Defaults" returns to Full.

Pure-UI: the dialog only reads/returns id lists + a saved-layouts dict; persistence is
the caller's job (MainWindow → QSettings).
"""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QListWidget,
    QListWidgetItem, QPushButton, QInputDialog, QMessageBox, QDialogButtonBox,
    QAbstractItemView,
)
from PyQt6.QtCore import Qt

from ui import nav_modules as NM


class ModuleVisibilityDialog(QDialog):
    def __init__(self, visible_ids, saved_layouts=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Customize Navigation')
        self.setMinimumWidth(380)
        self._saved = dict(saved_layouts or {})
        self._updating = False

        root = QVBoxLayout(self)
        root.addWidget(QLabel('Choose which modules appear in the navigation rail. '
                              'Drag to reorder; check to show.'))

        # ── Preset selector ──────────────────────────────────────────────────
        prow = QHBoxLayout()
        prow.addWidget(QLabel('Preset:'))
        self._preset = QComboBox()
        for key, label in NM.PRESET_LABELS:
            self._preset.addItem(label, key)
        self._preset.activated.connect(self._on_preset_chosen)
        prow.addWidget(self._preset, 1)
        root.addLayout(prow)

        # ── Module list (checkable + drag reorder) ───────────────────────────
        self._list = QListWidget()
        self._list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.itemChanged.connect(self._on_item_changed)
        self._list.model().rowsMoved.connect(lambda *_: self._sync_preset())
        root.addWidget(self._list, 1)

        # ── Saved layouts ────────────────────────────────────────────────────
        srow = QHBoxLayout()
        srow.addWidget(QLabel('Saved:'))
        self._saved_combo = QComboBox()
        self._saved_combo.activated.connect(self._on_load_saved)
        srow.addWidget(self._saved_combo, 1)
        b_save = QPushButton('Save as…');  b_save.clicked.connect(self._save_as)
        b_ren  = QPushButton('Rename');    b_ren.clicked.connect(self._rename_saved)
        b_del  = QPushButton('Delete');    b_del.clicked.connect(self._delete_saved)
        for b in (b_save, b_ren, b_del):
            srow.addWidget(b)
        root.addLayout(srow)

        b_restore = QPushButton('Restore Defaults (show all)')
        b_restore.clicked.connect(lambda: self._set_selection(NM.PRESETS['full']))
        root.addWidget(b_restore)

        # ── OK / Cancel ──────────────────────────────────────────────────────
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                              QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

        self._set_selection(visible_ids)
        self._refresh_saved_combo()

    # ── Public API ──────────────────────────────────────────────────────────
    def selected_ids(self) -> list:
        """Checked modules, in current list order (validated/deduped, may be empty —
        the never-empty guarantee is enforced by the guard and by the caller's
        sanitize())."""
        out, seen = [], set()
        for i in range(self._list.count()):
            it = self._list.item(i)
            if it.checkState() == Qt.CheckState.Checked:
                mid = it.data(Qt.ItemDataRole.UserRole)
                if mid in NM.BY_ID and mid not in seen:
                    out.append(mid)
                    seen.add(mid)
        return out

    def saved_layouts(self) -> dict:
        return dict(self._saved)

    # ── List construction ─────────────────────────────────────────────────────
    def _set_selection(self, ids):
        """Lay out checked modules (in given order) first, then hidden ones."""
        ids = NM.sanitize(ids)
        ordered = ids + NM.hidden_ids(ids)
        self._updating = True
        self._list.clear()
        for mid in ordered:
            m = NM.BY_ID[mid]
            it = QListWidgetItem(f'{m.title}   —   {m.description}')
            it.setData(Qt.ItemDataRole.UserRole, mid)
            it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable |
                        Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsDragEnabled)
            it.setCheckState(Qt.CheckState.Checked if mid in ids else Qt.CheckState.Unchecked)
            self._list.addItem(it)
        self._updating = False
        self._sync_preset()

    def _on_item_changed(self, item):
        if self._updating:
            return
        # Guard: never allow zero visible modules — revert the last uncheck.
        if not self.selected_ids():
            self._updating = True
            item.setCheckState(Qt.CheckState.Checked)
            self._updating = False
            QMessageBox.information(self, 'At least one module',
                                   'At least one module must stay visible.')
            return
        self._sync_preset()

    def _sync_preset(self):
        if self._updating:
            return
        name = NM.detect_preset(self.selected_ids())
        idx = self._preset.findData(name)
        if idx < 0:
            idx = self._preset.findData('custom')
        self._updating = True
        self._preset.setCurrentIndex(idx)
        self._updating = False

    def _on_preset_chosen(self, _idx):
        key = self._preset.currentData()
        if key in NM.PRESETS:
            self._set_selection(NM.PRESETS[key])

    # ── Saved layouts ────────────────────────────────────────────────────────
    def _refresh_saved_combo(self):
        self._updating = True
        self._saved_combo.clear()
        self._saved_combo.addItem('—', '')
        for name in sorted(self._saved):
            self._saved_combo.addItem(name, name)
        self._updating = False

    def _on_load_saved(self, _idx):
        if self._updating:
            return
        name = self._saved_combo.currentData()
        if name and name in self._saved:
            self._set_selection(self._saved[name])

    def _save_as(self):
        name, ok = QInputDialog.getText(self, 'Save layout', 'Layout name:')
        name = (name or '').strip()
        if ok and name:
            self._saved[name] = self.selected_ids()
            self._refresh_saved_combo()
            self._saved_combo.setCurrentIndex(self._saved_combo.findData(name))

    def _rename_saved(self):
        old = self._saved_combo.currentData()
        if not old or old not in self._saved:
            return
        name, ok = QInputDialog.getText(self, 'Rename layout', 'New name:', text=old)
        name = (name or '').strip()
        if ok and name and name != old:
            self._saved[name] = self._saved.pop(old)
            self._refresh_saved_combo()
            self._saved_combo.setCurrentIndex(self._saved_combo.findData(name))

    def _delete_saved(self):
        name = self._saved_combo.currentData()
        if name and name in self._saved:
            del self._saved[name]
            self._refresh_saved_combo()
