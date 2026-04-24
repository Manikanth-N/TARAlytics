from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSplitter
from PyQt6.QtCore import Qt

from core import signature_verifier
from ui.widgets.health_cards import HealthCardsWidget
from ui.widgets.signature_panel import SignaturePanel
from ui.widgets.event_table import EventTable
from ui.widgets.event_timeline import EventTimeline


class VerificationTab(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self._mw = main_window
        self._data = {}
        self._raw = b''
        self._pubkey = None
        self._key_path = ''
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet('background: #13131f;')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 4)
        layout.setSpacing(8)

        self._cards = HealthCardsWidget()
        layout.addWidget(self._cards)

        self._sig_panel = SignaturePanel()
        self._sig_panel.key_changed.connect(self._on_key_changed)
        layout.addWidget(self._sig_panel)

        self._event_table = EventTable()
        layout.addWidget(self._event_table, 1)

        self._timeline = EventTimeline()
        self._timeline.timeline_clicked.connect(self._on_timeline_click)
        layout.addWidget(self._timeline)

    def update_data(self, data: dict, raw: bytes):
        self._data = data
        self._raw = raw
        self._event_table.populate(data)
        events = self._event_table.get_events()
        if events:
            t_min = min(e[0] for e in events)
            t_max = max(e[0] for e in events)
            self._timeline.set_events(events, t_min, t_max)

        self._cards.update_firmware(data)
        self._cards.update_vehicle(data)
        self._cards.update_ekf(data)
        self._cards.update_gps(data)

        if self._raw:
            result = signature_verifier.full_verify(self._raw, self._pubkey)
            self._apply_verification(result)

    def set_pubkey(self, pubkey_str, key_path: str):
        self._pubkey = pubkey_str
        self._key_path = key_path
        self._sig_panel.set_key_file(key_path)
        if self._raw:
            result = signature_verifier.full_verify(self._raw, self._pubkey)
            self._apply_verification(result)

    def update_verification(self, result: dict, key_path: str = ''):
        self._apply_verification(result)
        if key_path:
            self._key_path = key_path

    def _apply_verification(self, result: dict):
        state = result.get('state', 'UNVERIFIED')
        hashes = result.get('hashes', {})
        key_id = ''
        if hashes:
            ki = hashes.get('key_id', '')
            if ki:
                key_id = ' '.join(ki[i:i+2] for i in range(0, len(ki), 2))
        self._cards.update_signature(state, key_id)
        self._sig_panel.update_verification(result, self._key_path)

    def _on_key_changed(self, path: str):
        self._mw.set_key_path_from_panel(path)

    def _on_timeline_click(self, t: float):
        self._event_table.scroll_to_time(t)
        try:
            self._mw._tab_plotter.set_crosshair(t)
        except Exception:
            pass
