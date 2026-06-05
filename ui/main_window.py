import os
import json
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QTabWidget, QProgressBar,
    QFileDialog, QSizePolicy, QToolBar, QFrame, QLineEdit,
    QApplication,
)
from PyQt6.QtCore import Qt, QSettings, QThreadPool, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QIcon, QPalette, QColor, QKeySequence, QShortcut

from core.log_parser import DataFlashParser, ParseRunnable, ParserSignals, VerifyRunnable, VerifySignals
from core import signature_verifier

from ui.app_state import AppState
from ui.widgets.navigation import NavigationRail
from ui import nav_modules
from ui.widgets.flight_header import FlightIdentityBar


def _dark_palette() -> QPalette:
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window,          QColor('#1e1e2e'))
    p.setColor(QPalette.ColorRole.WindowText,      QColor('#e0e0e0'))
    p.setColor(QPalette.ColorRole.Base,            QColor('#13131f'))
    p.setColor(QPalette.ColorRole.AlternateBase,   QColor('#1a1a2e'))
    p.setColor(QPalette.ColorRole.ToolTipBase,     QColor('#2a2a3e'))
    p.setColor(QPalette.ColorRole.ToolTipText,     QColor('#e0e0e0'))
    p.setColor(QPalette.ColorRole.Text,            QColor('#e0e0e0'))
    p.setColor(QPalette.ColorRole.Button,          QColor('#2a2a3e'))
    p.setColor(QPalette.ColorRole.ButtonText,      QColor('#e0e0e0'))
    p.setColor(QPalette.ColorRole.BrightText,      QColor('#ffffff'))
    p.setColor(QPalette.ColorRole.Link,            QColor('#4a90d9'))
    p.setColor(QPalette.ColorRole.Highlight,       QColor('#0d6efd'))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor('#ffffff'))
    return p


def _light_palette() -> QPalette:
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window,          QColor('#f0f2f5'))
    p.setColor(QPalette.ColorRole.WindowText,      QColor('#212529'))
    p.setColor(QPalette.ColorRole.Base,            QColor('#ffffff'))
    p.setColor(QPalette.ColorRole.AlternateBase,   QColor('#e9ecef'))
    p.setColor(QPalette.ColorRole.ToolTipBase,     QColor('#ffffff'))
    p.setColor(QPalette.ColorRole.ToolTipText,     QColor('#212529'))
    p.setColor(QPalette.ColorRole.Text,            QColor('#212529'))
    p.setColor(QPalette.ColorRole.Button,          QColor('#dee2e6'))
    p.setColor(QPalette.ColorRole.ButtonText,      QColor('#212529'))
    p.setColor(QPalette.ColorRole.BrightText,      QColor('#000000'))
    p.setColor(QPalette.ColorRole.Link,            QColor('#0d6efd'))
    p.setColor(QPalette.ColorRole.Highlight,       QColor('#0d6efd'))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor('#ffffff'))
    return p


def _trunc(path: str, max_len: int = 35) -> str:
    if not path:
        return '(none)'
    base = os.path.basename(path)
    if len(base) <= max_len:
        return base
    return '...' + base[-(max_len - 3):]


class MainWindow(QMainWindow):
    data_ready             = pyqtSignal(dict)
    time_cursor_changed    = pyqtSignal(float)   # absolute time → any tab
    event_selected         = pyqtSignal(float)   # Tab1 → Tab2: center on event
    plotter_cursor_moved   = pyqtSignal(float)   # Tab2 → Tab3: sync replay

    def __init__(self):
        super().__init__()
        self.setWindowTitle('TARAlytics Log Analyzer')
        self.resize(1400, 900)

        self._bin_path = ''
        self._key_path = ''
        self._parsed_data = {}
        self._raw_bytes = b''
        self._pubkey_str = None
        self._verify_signals: list = []
        self._is_dark = True

        # Central state hub — feeds the Debrief module and FlightIdentityBar.
        # Existing cross-tab wiring is left intact; AppState is additive.
        self._app_state = AppState(self)

        self._settings = QSettings('TARAlyticsAnalyzer', 'MainWindow')
        self._bin_path = self._settings.value('bin_path', '')
        self._key_path = self._settings.value('key_path', '')
        self._is_dark  = self._settings.value('is_dark', True, type=bool)

        self._setup_ui()
        self._update_toolbar_labels()
        # Load a previously-selected key at startup so the Verify tab reflects it
        # immediately (verification then runs automatically on the next parse).
        if self._key_path and os.path.isfile(self._key_path):
            self._load_key()

    def _setup_ui(self):
        toolbar = QToolBar('Main Toolbar')
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setStyleSheet('QToolBar { spacing: 6px; padding: 4px; }')
        self.addToolBar(toolbar)

        _path_style = (
            'QLineEdit { color: #e8e8e8; background-color: #2a2a2a; '
            'border: 1px solid #555555; border-radius: 3px; '
            'padding: 2px 6px; font-size: 12px; } '
            'QLineEdit:focus { border: 1px solid #4a90d9; } '
            'QLineEdit::placeholder { color: #888888; }'
        )

        self._bin_label = QLineEdit()
        self._bin_label.setReadOnly(True)
        self._bin_label.setMinimumWidth(240)
        self._bin_label.setPlaceholderText('Select .BIN log file...')
        self._bin_label.setStyleSheet(_path_style)

        bin_btn = QPushButton('📂')
        bin_btn.setFixedWidth(32)
        bin_btn.setToolTip('Load .BIN log file')
        bin_btn.clicked.connect(self._browse_bin)

        self._key_label = QLineEdit()
        self._key_label.setReadOnly(True)
        self._key_label.setMinimumWidth(240)
        self._key_label.setPlaceholderText('Select public key .dat...')
        self._key_label.setStyleSheet(_path_style)

        key_btn = QPushButton('📂')
        key_btn.setFixedWidth(32)
        key_btn.setToolTip('Load .dat public key file')
        key_btn.clicked.connect(self._browse_key)

        self._parse_btn = QPushButton('▶ Parse Log')
        self._parse_btn.setStyleSheet(
            'QPushButton { background: #0d6efd; color: white; border-radius: 4px; '
            'padding: 4px 14px; font-weight: bold; }'
            'QPushButton:hover { background: #0b5ed7; }'
            'QPushButton:disabled { background: #6c757d; }'
        )
        self._parse_btn.clicked.connect(self._start_parse)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setFixedWidth(200)
        self._progress.setFormat('Parsing: %p%')
        self._progress.setVisible(False)

        toolbar.addWidget(QLabel('BIN:'))
        toolbar.addWidget(self._bin_label)
        toolbar.addWidget(bin_btn)
        toolbar.addSeparator()
        toolbar.addWidget(QLabel('Key:'))
        toolbar.addWidget(self._key_label)
        toolbar.addWidget(key_btn)
        toolbar.addSeparator()
        toolbar.addWidget(self._parse_btn)
        toolbar.addWidget(self._progress)

        # ── Theme toggle ──────────────────────────────────────────────────────
        toolbar.addSeparator()
        self._theme_btn = QPushButton('☀' if self._is_dark else '🌙')
        self._theme_btn.setFixedWidth(34)
        self._theme_btn.setToolTip('Toggle light / dark theme')
        self._theme_btn.setStyleSheet(
            'QPushButton { background: #3a3a4e; color: #e0e0e0; border-radius: 4px; '
            'padding: 4px; font-size: 14px; }'
            'QPushButton:hover { background: #4a4a6e; }'
        )
        self._theme_btn.clicked.connect(self._toggle_theme)
        toolbar.addWidget(self._theme_btn)
        # Module visibility is customised exclusively from the navigation-rail gear
        # (⚙); the former toolbar button and View-menu entry were removed as
        # redundant.

        from ui.tab_verification import VerificationTab
        from ui.tab_plotter import PlotterTab
        from ui.tab_3d_view import View3DTab
        from ui.tab_map_view import MapTab
        from ui.modules.mod_debrief import DebriefModule
        from ui.modules.mod_timeline import TimelineModule
        from ui.modules.mod_events import EventsModule
        from ui.modules.mod_situation import SituationModule
        from ui.modules.mod_evidence import EvidenceModule

        self._tab_verify  = VerificationTab(self)
        self._tab_plotter = PlotterTab(self)
        self._tab_3d      = View3DTab(self)
        self._tab_map     = MapTab(self)
        self._mod_debrief = DebriefModule(self._app_state)
        self._mod_timeline = TimelineModule(self._app_state)
        self._mod_events = EventsModule(self._app_state)
        self._mod_situation = SituationModule(self._app_state)
        self._mod_evidence = EvidenceModule(self._app_state)

        # QTabWidget with a hidden tab bar acts as the page stack; the
        # NavigationRail drives page switching. Keeping QTabWidget preserves
        # all existing references and tests. The investigation surfaces
        # (Timeline / Events / Situation) lead the stack.
        self._tabs = QTabWidget()
        self._tabs.addTab(self._mod_debrief,   'Debrief')           # index 0
        self._tabs.addTab(self._mod_timeline,  'Timeline')          # index 1
        self._tabs.addTab(self._mod_events,    'Events')            # index 2
        self._tabs.addTab(self._mod_situation, 'Situation')         # index 3
        self._tabs.addTab(self._tab_plotter,   'Signal Plotter')    # index 4
        self._tabs.addTab(self._tab_3d,        '3D Flight View')    # index 5
        self._tabs.addTab(self._tab_verify,    'Log Verification')  # index 6
        self._tabs.addTab(self._tab_map,       '2D Map')            # index 7
        self._tabs.addTab(self._mod_evidence,  'Evidence')          # index 8

        from ui.modules.mod_workspace import WorkspaceModule
        self._mod_workspace = WorkspaceModule(self._app_state, self)
        self._tabs.addTab(self._mod_workspace, 'Workspace')         # index 9
        self._tabs.tabBar().hide()

        self._visible_modules = self._load_visible_modules()
        self._nav_rail = NavigationRail(
            nav_modules.order_to_navitems(self._visible_modules)
        )
        self._nav_rail.module_requested.connect(self._on_module_requested)
        self._nav_rail.customize_requested.connect(self._open_module_manager)

        self._flight_bar = FlightIdentityBar(self._app_state)

        from ui.widgets.cursor_dock import CursorDock
        self._cursor_dock = CursorDock(self._app_state)

        from ui.widgets.timeline_transport import TimelineTransport
        self._transport = TimelineTransport(self._app_state)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        body_layout.addWidget(self._nav_rail)
        body_layout.addWidget(self._tabs, 1)
        body_layout.addWidget(self._cursor_dock)   # persistent right context dock

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._flight_bar)
        layout.addWidget(body, 1)
        layout.addWidget(self._transport)          # persistent bottom timeline transport
        self.setCentralWidget(central)

        from ui.widgets.mission_overlay import MissionProcessingOverlay
        self._overlay = MissionProcessingOverlay(central)
        self._overlay.hide()

        self._nav_rail.set_active(0)

        # Debrief module can request navigation to other modules.
        self._mod_debrief.nav_requested.connect(self._on_module_requested)

        self.data_ready.connect(self._on_data_ready)

        # Cross-tab synchronisation via the shared cursor (AppState).
        # The plotter crosshair drives the one cursor; every surface follows it.
        # The broadcast guard in AppState prevents feedback loops.
        self._tab_plotter.crosshair_moved.connect(self._app_state.set_cursor_time)
        self._tab_plotter.crosshair_moved.connect(self.plotter_cursor_moved)  # legacy passthrough
        # Named subscribers so AppState.cursor_debug_info() can list who follows
        # the cursor (TimelineCanvas registers itself in its constructor).
        self._app_state.connect_cursor(self._tab_3d.set_time, 'View3D')
        self._app_state.connect_cursor(self._tab_map.set_time, 'MapTab')
        self._app_state.connect_cursor(self._tab_plotter.set_crosshair, 'Plotter')
        # Event selection highlights its position on the map (flight-path context).
        self._app_state.event_jumped.connect(self._tab_map.highlight_event)
        self.event_selected.connect(self._on_event_selected)

        # Keyboard shortcuts → the bottom transport (the single playback controller):
        # Space = play/pause, [ / ] = step ∓0.5 s.
        QShortcut(QKeySequence(Qt.Key.Key_Space), self).activated.connect(
            self._transport.toggle_play
        )
        QShortcut(QKeySequence('['), self).activated.connect(
            lambda: self._transport.step(-0.5)
        )
        QShortcut(QKeySequence(']'), self).activated.connect(
            lambda: self._transport.step(0.5)
        )

    def _on_module_requested(self, index: int):
        # The page always exists even if its module is hidden from the rail (e.g. a
        # Debrief quick-jump to a hidden module) — navigate regardless; the rail simply
        # shows no active item for a hidden page.
        self._tabs.setCurrentIndex(index)
        self._nav_rail.set_active(index)

    # ── Module visibility ─────────────────────────────────────────────────────
    def _load_visible_modules(self) -> list:
        """Resolve the visible module id list. Honours a saved selection; otherwise
        existing installs default to Full (no surprise disappearance on upgrade) and
        fresh installs default to Minimal."""
        saved = self._settings.value('nav/visible_modules', None)
        if saved:
            try:
                return nav_modules.sanitize(json.loads(saved))
            except (ValueError, TypeError):
                pass
        # No saved selection yet → decide by whether this is a pre-existing install.
        existing = any(not k.startswith('nav/') for k in self._settings.allKeys())
        ids = nav_modules.PRESETS['full'] if existing else nav_modules.PRESETS['minimal']
        self._settings.setValue('nav/visible_modules', json.dumps(ids))
        self._settings.setValue('nav/active_preset', 'full' if existing else 'minimal')
        return list(ids)

    def _load_saved_layouts(self) -> dict:
        raw = self._settings.value('nav/saved_layouts', '')
        try:
            d = json.loads(raw) if raw else {}
            return {k: nav_modules.sanitize(v) for k, v in d.items()} if isinstance(d, dict) else {}
        except (ValueError, TypeError):
            return {}

    def _open_module_manager(self):
        from ui.widgets.module_visibility import ModuleVisibilityDialog
        dlg = ModuleVisibilityDialog(self._visible_modules, self._load_saved_layouts(), self)
        if dlg.exec():
            self._save_saved_layouts(dlg.saved_layouts())
            self._apply_visible_modules(dlg.selected_ids())

    def _save_saved_layouts(self, layouts: dict):
        self._settings.setValue('nav/saved_layouts', json.dumps(layouts))

    def _apply_visible_modules(self, ids: list):
        ids = nav_modules.sanitize(ids)
        self._visible_modules = ids
        self._settings.setValue('nav/visible_modules', json.dumps(ids))
        self._settings.setValue('nav/active_preset', nav_modules.detect_preset(ids))
        self._nav_rail.set_modules(nav_modules.order_to_navitems(ids))
        # If the page we're on is no longer visible, fall back to the first visible one.
        visible_pages = self._nav_rail.visible_pages()
        if self._tabs.currentIndex() not in visible_pages and visible_pages:
            self._on_module_requested(visible_pages[0])
        else:
            self._nav_rail.set_active(self._tabs.currentIndex())

    def _update_toolbar_labels(self):
        self._bin_label.setText(_trunc(self._bin_path))
        self._key_label.setText(_trunc(self._key_path))

    def _browse_bin(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Open BIN Log', '', 'Log Files (*.bin *.BIN *.log *.tlog);;All Files (*)'
        )
        if path:
            self._bin_path = path
            self._settings.setValue('bin_path', path)
            self._update_toolbar_labels()

    def _browse_key(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Open Public Key', '', 'Key Files (*.dat);;All Files (*)'
        )
        if path:
            self._key_path = path
            self._settings.setValue('key_path', path)
            self._update_toolbar_labels()
            self._load_key()

    def _autodiscover_key(self):
        """If no public key is selected, look for one beside the log so signature
        verification runs without the user manually loading a key each session.

        Searches the BIN's directory, its parent, and the working directory for a
        ``*public_key*.dat`` (then any ``*.dat``). First match wins; a key the user
        explicitly selected is never overridden.
        """
        if self._key_path and os.path.isfile(self._key_path):
            return
        if not self._bin_path:
            return
        import glob
        bin_dir = os.path.dirname(os.path.abspath(self._bin_path))
        search_dirs = [bin_dir, os.path.dirname(bin_dir), os.getcwd()]
        seen = set()
        for d in search_dirs:
            if not d or d in seen:
                continue
            seen.add(d)
            for pattern in ('*public_key*.dat', '*pubkey*.dat', '*.dat'):
                hits = sorted(glob.glob(os.path.join(d, pattern)))
                if hits:
                    self._key_path = hits[0]
                    self._settings.setValue('key_path', self._key_path)
                    self._update_toolbar_labels()
                    self._status(f'Auto-loaded public key: {os.path.basename(self._key_path)}')
                    return

    def _load_key(self):
        if self._key_path:
            self._pubkey_str = signature_verifier.load_pubkey_file(self._key_path)
            self._tab_verify.set_pubkey(self._pubkey_str, self._key_path)
            self._app_state.set_pubkey(self._pubkey_str, self._key_path)
            if self._raw_bytes:
                self._run_verification()

    def _start_parse(self):
        if not self._bin_path or not os.path.isfile(self._bin_path):
            self._status('No valid BIN file selected.')
            return

        self._parse_btn.setEnabled(False)
        self._parse_btn.setText('⏳ Parsing...')
        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._status('Reading log file...')

        try:
            with open(self._bin_path, 'rb') as f:
                self._raw_bytes = f.read()
        except Exception as e:
            self._status(f'Failed to read file: {e}')
            self._parse_btn.setEnabled(True)
            self._progress.setVisible(False)
            return

        self._autodiscover_key()
        self._load_key()

        self._overlay.start()      # branded mission-processing overlay

        signals = ParserSignals()
        signals.progress.connect(self._progress.setValue)
        signals.progress.connect(self._overlay.set_progress)
        signals.stage.connect(self._overlay.set_stage)
        signals.stage.connect(self._status)
        signals.finished.connect(self._on_parse_done)
        signals.error.connect(self._on_parse_error)

        runnable = ParseRunnable(self._bin_path, signals)
        QThreadPool.globalInstance().start(runnable)

    def _on_parse_done(self, data: dict):
        self._parsed_data = data
        self._progress.setVisible(False)
        self._parse_btn.setEnabled(True)
        self._parse_btn.setText('▶ Parse Log')
        self._status(f'Parsed {len(data)} message types.')
        self.data_ready.emit(data)
        self._overlay.mission_ready()      # holds, then fades to reveal the loaded UI

    def _on_parse_error(self, msg: str):
        self._progress.setVisible(False)
        self._parse_btn.setEnabled(True)
        self._parse_btn.setText('▶ Parse Log')
        self._status(f'Parse error: {msg}')
        self._overlay.fail()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if getattr(self, '_overlay', None) is not None and self._overlay.isVisible():
            self._overlay.resize(self._overlay.parent().size())

    def _on_data_ready(self, data: dict):
        self._tab_verify.update_data(data, self._raw_bytes)
        self._tab_plotter.update_data(data)
        self._tab_3d.update_data(data)
        self._tab_map.update_data(data)
        # Feed the central state hub so the Debrief module and FlightIdentityBar
        # update. Existing tabs above keep their own direct wiring.
        self._app_state.set_parsed_data(data, self._raw_bytes, self._bin_path)
        self._run_verification()

    def _toggle_theme(self):
        self._is_dark = not self._is_dark
        self._settings.setValue('is_dark', self._is_dark)
        QApplication.instance().setPalette(_dark_palette() if self._is_dark else _light_palette())
        self._theme_btn.setText('☀' if self._is_dark else '🌙')

    def _run_verification(self):
        if not self._raw_bytes:
            return
        sigs = VerifySignals()
        self._verify_signals.append(sigs)
        sigs.finished.connect(
            lambda result, kp, s=sigs: self._on_verify_done(result, kp, s)
        )
        runnable = VerifyRunnable(self._raw_bytes, self._pubkey_str, self._key_path, sigs)
        QThreadPool.globalInstance().start(runnable)

    def _on_verify_done(self, result: dict, key_path: str, sigs: object):
        self._tab_verify.update_verification(result, key_path)
        self._app_state.set_verification(result)
        if sigs in self._verify_signals:
            self._verify_signals.remove(sigs)

    def _on_event_selected(self, t_abs: float):
        """Tab 1 event click → center Tab 2 view on that time."""
        try:
            rel = t_abs - self._tab_plotter._t_offset
            xr = self._tab_plotter._vb.viewRange()[0]
            half_width = (xr[1] - xr[0]) / 2
            self._tab_plotter._plot.setXRange(rel - half_width, rel + half_width, padding=0)
            self._tab_plotter.set_crosshair(t_abs)
        except Exception:
            pass

    def _status(self, msg: str):
        self.statusBar().showMessage(msg, 5000)

    def get_raw_bytes(self) -> bytes:
        return self._raw_bytes

    def get_pubkey_str(self):
        return self._pubkey_str

    def get_key_path(self) -> str:
        return self._key_path

    def set_key_path_from_panel(self, path: str):
        self._key_path = path
        self._settings.setValue('key_path', path)
        self._update_toolbar_labels()
        self._load_key()
