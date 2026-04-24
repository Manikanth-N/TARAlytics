import os
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QTabWidget, QProgressBar,
    QFileDialog, QSizePolicy, QToolBar, QFrame, QLineEdit,
)
from PyQt6.QtCore import Qt, QSettings, QThreadPool, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QIcon

from core.log_parser import DataFlashParser, ParseRunnable, ParserSignals
from core import signature_verifier


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
        self.setWindowTitle('ArduPilot Log Analyzer')
        self.resize(1400, 900)

        self._bin_path = ''
        self._key_path = ''
        self._parsed_data = {}
        self._raw_bytes = b''
        self._pubkey_str = None

        self._settings = QSettings('ArduPilotAnalyzer', 'MainWindow')
        self._bin_path = self._settings.value('bin_path', '')
        self._key_path = self._settings.value('key_path', '')

        self._setup_ui()
        self._update_toolbar_labels()

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
        self._progress.setFixedWidth(180)
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

        from ui.tab_verification import VerificationTab
        from ui.tab_plotter import PlotterTab
        from ui.tab_3d_view import View3DTab

        self._tab_verify = VerificationTab(self)
        self._tab_plotter = PlotterTab(self)
        self._tab_3d = View3DTab(self)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._tab_verify, 'Log Verification')
        self._tabs.addTab(self._tab_plotter, 'Signal Plotter')
        self._tabs.addTab(self._tab_3d, '3D Flight View')

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._tabs)
        self.setCentralWidget(central)

        self.data_ready.connect(self._on_data_ready)

        # Cross-tab synchronisation
        self._tab_plotter.crosshair_moved.connect(self.plotter_cursor_moved)
        self._tab_plotter.crosshair_moved.connect(self._tab_3d.set_time)
        self.event_selected.connect(self._on_event_selected)

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

    def _load_key(self):
        if self._key_path:
            self._pubkey_str = signature_verifier.load_pubkey_file(self._key_path)
            self._tab_verify.set_pubkey(self._pubkey_str, self._key_path)
            if self._raw_bytes:
                self._run_verification()

    def _start_parse(self):
        if not self._bin_path or not os.path.isfile(self._bin_path):
            self._status('No valid BIN file selected.')
            return

        self._parse_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setValue(0)

        try:
            with open(self._bin_path, 'rb') as f:
                self._raw_bytes = f.read()
        except Exception as e:
            self._status(f'Failed to read file: {e}')
            self._parse_btn.setEnabled(True)
            self._progress.setVisible(False)
            return

        self._load_key()

        signals = ParserSignals()
        signals.progress.connect(self._progress.setValue)
        signals.finished.connect(self._on_parse_done)
        signals.error.connect(self._on_parse_error)

        runnable = ParseRunnable(self._bin_path, signals)
        QThreadPool.globalInstance().start(runnable)

    def _on_parse_done(self, data: dict):
        self._parsed_data = data
        self._progress.setVisible(False)
        self._parse_btn.setEnabled(True)
        self.data_ready.emit(data)

    def _on_parse_error(self, msg: str):
        self._progress.setVisible(False)
        self._parse_btn.setEnabled(True)
        self._status(f'Parse error: {msg}')

    def _on_data_ready(self, data: dict):
        self._tab_verify.update_data(data, self._raw_bytes)
        self._tab_plotter.update_data(data)
        self._tab_3d.update_data(data)

    def _run_verification(self):
        if self._raw_bytes:
            result = signature_verifier.full_verify(self._raw_bytes, self._pubkey_str)
            self._tab_verify.update_verification(result, self._key_path)

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
