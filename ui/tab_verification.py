from PyQt6.QtWidgets import QWidget, QVBoxLayout

from core import signature_verifier
from ui.widgets.signature_panel import SignaturePanel


class VerificationTab(QWidget):
    """Verify answers exactly one question: *can I trust this log?*

    It reports integrity and authenticity only — signature status, hash-chain
    status, key information and the operational verification classification.
    It deliberately carries NO flight-analysis content: no automatic faults,
    no analytics warnings, no scores, no oscillation/vibration/pilot findings.
    Those live in Debrief (verification and analytics are separate concerns).
    """

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
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self._sig_panel = SignaturePanel()
        self._sig_panel.key_changed.connect(self._on_key_changed)
        layout.addWidget(self._sig_panel)
        layout.addStretch(1)

    def update_data(self, data: dict, raw: bytes):
        # Verify keeps the bytes for (re)verification but injects no analytics,
        # events or faults — integrity/authenticity only.
        self._data = data
        self._raw = raw

    def set_pubkey(self, pubkey_str, key_path: str):
        self._pubkey = pubkey_str
        self._key_path = key_path
        self._sig_panel.set_key_file(key_path)
        if self._raw:
            result = signature_verifier.full_verify(self._raw, self._pubkey)
            self._apply_verification(result)

    def update_verification(self, result: dict, key_path: str = ''):
        if key_path:
            self._key_path = key_path
        self._apply_verification(result)

    def _apply_verification(self, result: dict):
        self._sig_panel.update_verification(result, self._key_path)

    def _on_key_changed(self, path: str):
        self._mw.set_key_path_from_panel(path)
