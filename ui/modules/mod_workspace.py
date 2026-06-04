"""
WorkspaceModule — the Investigation Workspace (P4.2 / P4.3 / P4.4).

One screen that shows several cursor-driven surfaces at once, so the investigator
scrubs the persistent timeline transport and watches the plot, attitude, sticks, map
and events update together — instead of tab-switching. Simple split layout (a primary
pane + two stacked secondaries), three built-in layouts, pop-out panels, and saved
layouts. No new analytics.

Each surface is a fresh instance wired to the shared AppState (the parsed DataFrames
are shared by reference, so this is cheap), so the same widget never has to live in
two places at once.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel, QPushButton, QComboBox,
    QInputDialog, QSizePolicy,
)
from PyQt6.QtCore import Qt, QSettings

from ui.design.tokens import T
from ui.app_state import AppState
from ui.widgets.module_header import ModuleHeader

# surfaces that make sense as floating windows (read-only, cursor-driven)
_POPOUTABLE = {'horizon', 'rc', 'map', 'replay'}
_TITLES = {'signals': 'Signals', 'horizon': 'Artificial Horizon', 'rc': 'RC / Pilot',
           'map': 'Map', 'events': 'Events', 'evidence': 'Evidence',
           'verify': 'Verification', 'timeline': 'Timeline'}

BUILTIN_LAYOUTS = {
    'Pilot Analysis':         ['signals', 'horizon', 'rc'],
    'Accident Investigation': ['signals', 'map', 'events'],
    'Certification':          ['evidence', 'verify', 'timeline'],
}
_LAYOUT_PRESET = {'Pilot Analysis': 'Attitude', 'Accident Investigation': 'Attitude'}


class _VerifySummary(QWidget):
    """Lightweight read-only verification status (reads AppState.verification)."""
    def __init__(self, app_state, parent=None):
        super().__init__(parent)
        self._app = app_state
        lay = QVBoxLayout(self)
        lay.setContentsMargins(T.spacing.px16, T.spacing.px12, T.spacing.px16, T.spacing.px12)
        lay.setSpacing(T.spacing.px8)
        from ui.widgets.badge import StatusBadge
        self._badge = StatusBadge('UNVERIFIED', 'UNVERIFIED')
        self._lines = {k: QLabel('—') for k in ('algo', 'chunks', 'key', 'fp', 'detail')}
        lay.addWidget(self._badge)
        for k in ('algo', 'chunks', 'key', 'fp', 'detail'):
            self._lines[k].setWordWrap(True)
            self._lines[k].setStyleSheet(f'color: {T.text.secondary}; font-size: {T.size.sm}px;')
            lay.addWidget(self._lines[k])
        lay.addStretch()
        app_state.verification_changed.connect(lambda *_: self.refresh())
        self.refresh()

    def refresh(self):
        v = self._app.verification
        self._badge.set_state(v.state, v.state)
        self._lines['algo'].setText(f'Algorithm: {v.algo_name}')
        self._lines['chunks'].setText(
            f'{v.chain_chunks:,} chunks verified' if v.chain_chunks else 'Chain: —')
        self._lines['key'].setText(f'Key ID: {v.key_id}')
        self._lines['fp'].setText(f'Fingerprint: {v.fingerprint}')
        self._lines['detail'].setText(v.detail[:120] if v.detail else '')


class PanelFrame(QWidget):
    """A titled container for one workspace surface, with an optional pop-out button."""
    def __init__(self, key: str, widget: QWidget, on_popout=None, parent=None):
        super().__init__(parent)
        self.key = key
        self.widget = widget
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        bar = QHBoxLayout()
        bar.setContentsMargins(T.spacing.px8, 2, T.spacing.px4, 2); bar.setSpacing(4)
        title = QLabel(_TITLES.get(key, key).upper())
        from PyQt6.QtGui import QFont
        f = QFont(T.font.brand, T.size.xs); f.setWeight(T.weight.bold)
        title.setFont(f); title.setStyleSheet(f'color: {T.text.muted};')
        bar.addWidget(title); bar.addStretch()
        if on_popout is not None and key in _POPOUTABLE:
            b = QPushButton('⇱')
            b.setToolTip('Pop out as a floating window'); b.setFixedSize(20, 18)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(
                f'QPushButton {{ background: transparent; color: {T.text.secondary}; '
                f'border: none; font-size: 12px; }} '
                f'QPushButton:hover {{ color: {T.brand.blue_bright}; }}')
            b.clicked.connect(lambda: on_popout(key))
            bar.addWidget(b)
        bar_w = QWidget(); bar_w.setLayout(bar)
        bar_w.setStyleSheet(f'background: {T.surface.elevated};')
        root.addWidget(bar_w)
        root.addWidget(widget, 1)


class WorkspaceModule(QWidget):
    def __init__(self, app_state: AppState, main_window, parent=None):
        super().__init__(parent)
        self._app = app_state
        self._mw = main_window
        self._panels: dict[str, QWidget] = {}   # cached surface instances
        self._floating: dict[str, QWidget] = {}  # key -> floating window
        self._current = None
        self._settings = QSettings('TARAlyticsAnalyzer', 'Workspace')
        self._custom = self._load_custom()
        self._setup_ui()
        self.set_layout('Pilot Analysis')

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        header = ModuleHeader('Workspace')
        self._layout_cb = QComboBox()
        self._refresh_layout_combo()
        self._layout_cb.setStyleSheet(
            f'QComboBox {{ background: {T.surface.card}; color: {T.text.primary}; '
            f'border: 1px solid {T.border.default}; border-radius: 3px; padding: 2px 8px; '
            f'font-size: {T.size.sm}px; }}')
        self._layout_cb.activated.connect(self._on_layout_selected)
        b_save = self._hbtn('Save…', 'Save the current layout')
        b_save.clicked.connect(self._save_layout)
        b_ren = self._hbtn('Rename…', 'Rename a saved layout')
        b_ren.clicked.connect(self._rename_layout)
        b_del = self._hbtn('Delete', 'Delete the selected saved layout')
        b_del.clicked.connect(self._delete_layout)
        header.add_action(self._layout_cb)
        header.add_action(b_save); header.add_action(b_ren); header.add_action(b_del)
        root.addWidget(header)

        self._body = QWidget()
        self._body_lay = QVBoxLayout(self._body)
        self._body_lay.setContentsMargins(T.spacing.px8, T.spacing.px8, T.spacing.px8, T.spacing.px8)
        root.addWidget(self._body, 1)

    def _hbtn(self, text, tip):
        b = QPushButton(text); b.setToolTip(tip); b.setFixedHeight(24)
        b.setStyleSheet(
            f'QPushButton {{ background: {T.surface.card}; color: {T.text.secondary}; '
            f'border: 1px solid {T.border.default}; border-radius: 3px; padding: 2px 8px; '
            f'font-family: {T.font.brand}; font-size: {T.size.sm}px; }} '
            f'QPushButton:hover {{ color: {T.brand.blue_bright}; border-color: {T.border.active}; }}')
        return b

    def _all_layouts(self) -> dict:
        return {**BUILTIN_LAYOUTS, **self._custom}

    def _refresh_layout_combo(self):
        cur = self._layout_cb.currentText() if self._layout_cb.count() else None
        self._layout_cb.blockSignals(True)
        self._layout_cb.clear()
        self._layout_cb.addItems(list(BUILTIN_LAYOUTS))
        if self._custom:
            self._layout_cb.insertSeparator(self._layout_cb.count())
            self._layout_cb.addItems(list(self._custom))
        if cur:
            i = self._layout_cb.findText(cur)
            if i >= 0:
                self._layout_cb.setCurrentIndex(i)
        self._layout_cb.blockSignals(False)

    # ── surfaces ──────────────────────────────────────────────────────────────

    def _surface(self, key: str) -> QWidget:
        w = self._panels.get(key)
        if w is not None:
            try:
                w.isVisible()          # touch the C++ object; RuntimeError if deleted
                return w
            except RuntimeError:
                self._panels.pop(key, None)
        w = self._make(key)
        self._panels[key] = w
        self._prime(key, w)
        return w

    def _make(self, key: str) -> QWidget:
        app = self._app
        if key == 'horizon':
            from ui.widgets.horizon import ArtificialHorizon
            return ArtificialHorizon(app)
        if key == 'rc':
            from ui.widgets.rc_viz import RCVisualization
            return RCVisualization(app)
        if key == 'events':
            from ui.modules.mod_events import EventsModule
            return EventsModule(app)
        if key == 'evidence':
            from ui.modules.mod_evidence import EvidenceModule
            return EvidenceModule(app)
        if key == 'timeline':
            from ui.modules.mod_timeline import TimelineModule
            return TimelineModule(app)
        if key == 'verify':
            return _VerifySummary(app)
        if key == 'map':
            from ui.tab_map_view import MapTab
            m = MapTab()
            app.data_changed.connect(m.update_data)
            app.connect_cursor(m.set_time, 'Workspace.Map')
            app.event_jumped.connect(m.highlight_event)
            return m
        if key == 'signals':
            from ui.tab_plotter import PlotterTab
            p = PlotterTab(self._mw)
            app.data_changed.connect(p.update_data)
            p.crosshair_moved.connect(app.set_cursor_time)
            app.connect_cursor(p.set_crosshair, 'Workspace.Signals')
            return p
        return QLabel(f'(unknown surface: {key})')

    def _prime(self, key: str, w: QWidget):
        """Feed a freshly-created surface the already-loaded data/cursor."""
        if not self._app.has_data:
            return
        data = self._app.data
        try:
            if key in ('horizon', 'rc'):
                w._on_data(data)
            elif key == 'events':
                w._on_data(data)
            elif key == 'evidence':
                w._refresh_list()
            elif key == 'timeline':
                w.canvas._on_data(data)
            elif key == 'map':
                w.update_data(data); w.set_time(self._app.cursor_time)
            elif key == 'signals':
                w.update_data(data); w.set_crosshair(self._app.cursor_time)
        except Exception:
            pass

    # ── layout ────────────────────────────────────────────────────────────────

    def set_layout(self, name: str):
        layout = self._all_layouts().get(name)
        if not layout:
            return
        self._current = name
        i = self._layout_cb.findText(name)
        if i >= 0:
            self._layout_cb.setCurrentIndex(i)
        # Detach cached (non-floating) surfaces first so destroying the old
        # PanelFrames doesn't delete the surfaces we want to reuse.
        for k, surf in self._panels.items():
            if k in self._floating:
                continue
            try:
                surf.setParent(None)
            except RuntimeError:
                pass
        while self._body_lay.count():
            it = self._body_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        keys = [k for k in layout if k not in self._floating]
        self._body_lay.addWidget(self._build_split(keys))
        # apply a relevant signal preset
        preset = _LAYOUT_PRESET.get(name)
        if preset and 'signals' in keys:
            try:
                self._panels['signals'].apply_preset(preset)
            except Exception:
                pass

    def _build_split(self, keys: list) -> QWidget:
        if not keys:
            lbl = QLabel('All panels are floating.')
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f'color: {T.text.muted};')
            return lbl
        frames = [PanelFrame(k, self._surface(k), on_popout=self._popout) for k in keys]
        if len(frames) == 1:
            return frames[0]
        # primary on the left, the rest stacked vertically on the right
        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(frames[0])
        if len(frames) == 2:
            split.addWidget(frames[1])
            split.setSizes([640, 420])
        else:
            right = QSplitter(Qt.Orientation.Vertical)
            for fr in frames[1:]:
                right.addWidget(fr)
            split.addWidget(right)
            split.setSizes([720, 460])
        return split

    def _on_layout_selected(self, _i):
        self.set_layout(self._layout_cb.currentText())

    # ── pop-out (P4.3) ────────────────────────────────────────────────────────

    def _popout(self, key: str):
        if key in self._floating:
            return
        surface = self._surface(key)
        win = _FloatingPanel(key, surface, on_close=lambda k=key: self._redock(k))
        self._floating[key] = win
        win.resize(420, 380)
        win.show()
        self.set_layout(self._current)   # rebuild without the popped-out panel

    def _redock(self, key: str):
        if key in self._floating:
            del self._floating[key]
            if self._current:
                self.set_layout(self._current)

    # ── saved layouts (P4.4) ──────────────────────────────────────────────────

    def _load_custom(self) -> dict:
        import json
        raw = self._settings.value('layouts', '')
        try:
            return json.loads(raw) if raw else {}
        except Exception:
            return {}

    def _store_custom(self):
        import json
        self._settings.setValue('layouts', json.dumps(self._custom))

    def _save_layout(self):
        name, ok = QInputDialog.getText(self, 'Save layout', 'Layout name:',
                                        text=self._current or 'My Layout')
        name = name.strip()
        if not (ok and name) or name in BUILTIN_LAYOUTS:
            return
        self._custom[name] = list(self._all_layouts().get(self._current, []))
        self._store_custom(); self._refresh_layout_combo(); self.set_layout(name)

    def _rename_layout(self):
        old = self._layout_cb.currentText()
        if old not in self._custom:
            return
        name, ok = QInputDialog.getText(self, 'Rename layout', 'New name:', text=old)
        name = name.strip()
        if not (ok and name) or name in self._all_layouts():
            return
        self._custom[name] = self._custom.pop(old)
        self._store_custom(); self._refresh_layout_combo(); self.set_layout(name)

    def _delete_layout(self):
        name = self._layout_cb.currentText()
        if name in self._custom:
            del self._custom[name]
            self._store_custom(); self._refresh_layout_combo()
            self.set_layout('Pilot Analysis')


class _FloatingPanel(QWidget):
    """A floating window hosting a workspace surface; closing re-docks it."""
    def __init__(self, key, surface, on_close, parent=None):
        super().__init__(parent)
        self._on_close = on_close
        self.setWindowTitle(f'TARAlytics — {_TITLES.get(key, key)}')
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(surface)

    def closeEvent(self, e):
        # detach the surface so it can be re-docked, then signal redock
        lay = self.layout()
        if lay and lay.count():
            w = lay.takeAt(0).widget()
            if w:
                w.setParent(None)
        self._on_close()
        super().closeEvent(e)
