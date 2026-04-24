import os
import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QFileDialog, QApplication,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QColor
from core.colors import badge_style


_DARK_PANEL  = '#1a1a2a'
_DARK_BORDER = '#2a2a3a'
_COL_DIM     = '#6a6a8a'
_COL_MID     = '#9898b8'
_COL_TEXT    = '#c8c8e0'
_COL_MONO    = '#d0d0e8'

_COPY_BTN_STYLE = """
    QPushButton {
        color: #8888aa;
        background-color: #252538;
        border: 1px solid #3a3a5a;
        border-radius: 3px;
        padding: 2px 6px;
        font-size: 10px;
        min-width: 40px;
    }
    QPushButton:hover {
        background-color: #303050;
        color: #c8c8e8;
        border-color: #5a5a8a;
    }
    QPushButton:pressed { background-color: #1a1a30; }
"""


def _short_hash(h: str, n: int = 12) -> str:
    if len(h) <= n * 2 + 3:
        return h
    return h[:n] + '...' + h[-n:]


class HashRow(QWidget):
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f'background: transparent;')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(8)

        lbl = QLabel(label)
        lbl.setFixedWidth(190)
        lbl.setStyleSheet(f'color: {_COL_DIM}; font-size: 11px; background: transparent;')
        layout.addWidget(lbl)

        self._value = QLabel('—')
        self._value.setStyleSheet(
            f'font-family: monospace; font-size: 11px; color: {_COL_MONO}; background: transparent;'
        )
        self._value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._value, 1)

        self._copy_btn = QPushButton('COPY')
        self._copy_btn.setFixedWidth(50)
        self._copy_btn.setFixedHeight(20)
        self._copy_btn.setStyleSheet(_COPY_BTN_STYLE)
        self._copy_btn.setEnabled(True)
        self._full_hash = ''
        self._copy_btn.clicked.connect(self._copy)
        layout.addWidget(self._copy_btn)

    def set_value(self, full_hash: str):
        self._full_hash = full_hash
        self._value.setText(_short_hash(full_hash))
        self._value.setToolTip(full_hash)

    def _copy(self):
        QApplication.clipboard().setText(self._full_hash)
        self._copy_btn.setText('✓')
        QTimer.singleShot(1500, lambda: self._copy_btn.setText('COPY'))


def _info_row(layout: QVBoxLayout, text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f'font-size: 11px; border: none; color: {_COL_MID}; background: transparent;')
    lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    layout.addWidget(lbl)
    return lbl


def _sep_line() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet(f'border: 1px solid {_DARK_BORDER}; background: transparent;')
    return f


class SignaturePanel(QFrame):
    key_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            f'SignaturePanel, QFrame {{ background: {_DARK_PANEL}; '
            f'border: 1px solid {_DARK_BORDER}; border-radius: 8px; }}'
        )
        # Force dark background via palette
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(pal.ColorRole.Window, QColor(_DARK_PANEL))
        self.setPalette(pal)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(5)

        # ── Status badge ──────────────────────────────────────────────────────
        badge_row = QHBoxLayout()
        badge_row.setSpacing(10)
        self._badge = QLabel('UNVERIFIED')
        self._badge.setStyleSheet(
            'color: #fcd34d; background: #2a1a00; border-radius: 4px; '
            'padding: 3px 12px; font-weight: bold; font-size: 14px; border: none;'
        )
        self._badge.setFixedHeight(30)
        badge_row.addWidget(self._badge)

        self._algo_lbl = QLabel('')
        self._algo_lbl.setStyleSheet(f'font-size: 11px; color: {_COL_DIM}; border: none; background: transparent;')
        badge_row.addWidget(self._algo_lbl, 1)
        layout.addLayout(badge_row)

        layout.addWidget(_sep_line())

        # ── Structure info ────────────────────────────────────────────────────
        self._range_lbl  = _info_row(layout, 'Signed range  —')
        self._struct_lbl = _info_row(layout, 'Structure  —')
        self._chain_lbl  = _info_row(layout, 'Hash chain  —')

        layout.addWidget(_sep_line())

        # ── Header metadata ───────────────────────────────────────────────────
        meta_row = QHBoxLayout()
        meta_row.setSpacing(20)
        self._dev_lbl  = QLabel('Device  —')
        self._dev_lbl.setStyleSheet(f'font-size: 11px; border: none; color: {_COL_MID}; background: transparent;')
        self._fw_lbl   = QLabel('FW  —')
        self._fw_lbl.setStyleSheet(f'font-size: 11px; border: none; color: {_COL_MID}; background: transparent;')
        self._ts_lbl   = QLabel('Signed at  —')
        self._ts_lbl.setStyleSheet(f'font-size: 11px; border: none; color: {_COL_MID}; background: transparent;')
        self._ctr_lbl  = QLabel('Log #  —')
        self._ctr_lbl.setStyleSheet(f'font-size: 11px; border: none; color: {_COL_MID}; background: transparent;')
        for w in (self._dev_lbl, self._fw_lbl, self._ts_lbl, self._ctr_lbl):
            meta_row.addWidget(w)
        meta_row.addStretch()
        layout.addLayout(meta_row)

        layout.addWidget(_sep_line())

        # ── Hash rows ─────────────────────────────────────────────────────────
        self._sha_signed  = HashRow('SHA256 (signed range)')
        self._sha_full    = HashRow('SHA256 (full file)')
        self._header_mac  = HashRow('Header MAC (H0)')
        layout.addWidget(self._sha_signed)
        layout.addWidget(self._sha_full)
        layout.addWidget(self._header_mac)

        self._key_id_lbl = _info_row(layout, 'Key ID  —')

        layout.addWidget(_sep_line())

        # ── Key picker ────────────────────────────────────────────────────────
        key_row = QHBoxLayout()
        key_row.setSpacing(8)
        self._key_file_lbl = QLabel('Public key file  (none)')
        self._key_file_lbl.setStyleSheet(
            f'font-size: 11px; border: none; color: {_COL_MID}; background: transparent;'
        )
        key_row.addWidget(self._key_file_lbl, 1)
        self._change_key_btn = QPushButton('Change Key')
        self._change_key_btn.setStyleSheet(
            'QPushButton { background: #1a4a8a; color: #c8d8f8; border-radius: 4px; '
            'padding: 2px 10px; font-size: 11px; border: 1px solid #2a5a9a; }'
            'QPushButton:hover { background: #2a5a9a; }'
        )
        self._change_key_btn.clicked.connect(self._browse_key)
        key_row.addWidget(self._change_key_btn)
        layout.addLayout(key_row)

        self._fp_lbl = _info_row(layout, 'Key fingerprint  —')
        self._ed_lbl = _info_row(layout, 'Signature result  —')

    def _browse_key(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Open Public Key', '', 'Key Files (*.dat);;All Files (*)'
        )
        if path:
            self.key_changed.emit(path)

    def update_verification(self, result: dict, key_path: str = ''):
        state = result.get('state', 'UNVERIFIED')
        fg, bg = badge_style(state)
        self._badge.setText(state)
        self._badge.setStyleSheet(
            f'color: {fg}; background: {bg}; border-radius: 4px; '
            f'padding: 3px 12px; font-weight: bold; font-size: 14px; border: none;'
        )

        algo = result.get('algo_name', '')
        self._algo_lbl.setText(algo)

        # Structure
        hashes = result.get('hashes', {})
        if hashes:
            ds = hashes.get('data_start', 0)
            dl = hashes.get('data_len', 0)
            self._range_lbl.setText(f'Signed range    {ds} → {ds + dl:,}  ({dl:,} bytes)')
            self._struct_lbl.setText(
                f'Structure       {"PASS ✔" if result.get("structure_ok") else "FAIL ✗"}'
            )
            self._sha_signed.set_value(hashes.get('sha256_signed', ''))
            self._sha_full.set_value(hashes.get('sha256_full', ''))
            self._header_mac.set_value(hashes.get('header_mac', ''))
            ki = hashes.get('key_id', '')
            if ki:
                ki_fmt = ' '.join(ki[i:i+2] for i in range(0, len(ki), 2))
                self._key_id_lbl.setText(f'Key ID   {ki_fmt}')
        else:
            struct_msg = result.get('structure_message', '')
            self._struct_lbl.setText(f'Structure   {struct_msg}')

        # Hash chain
        chain_ok = result.get('chain_ok', False)
        chunks = result.get('chain_chunks', 0)
        if chunks > 0:
            chain_icon = '✔' if chain_ok else '✗'
            chain_color = '#4ade80' if chain_ok else '#f87171'
            self._chain_lbl.setText(
                f'Hash chain   <span style="color:{chain_color};font-weight:bold">'
                f'{chunks} chunks {chain_icon}</span>'
            )
            self._chain_lbl.setTextFormat(Qt.TextFormat.RichText)
        else:
            self._chain_lbl.setText('Hash chain   not present')

        # Header metadata
        hi = result.get('header_info', {})
        if hi:
            self._dev_lbl.setText(f'Device  {hi.get("device_id", "—")}')
            self._fw_lbl.setText(f'FW  {hi.get("fw_ver", "—")}')
            ts = hi.get('timestamp', 0)
            if ts:
                try:
                    dt = datetime.datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M UTC')
                except Exception:
                    dt = str(ts)
                self._ts_lbl.setText(f'Signed at  {dt}')
            self._ctr_lbl.setText(f'Log #  {hi.get("log_ctr", "—")}')

        if key_path:
            self._key_file_lbl.setText(f'Public key file   {os.path.basename(key_path)}')

        # Key fingerprint — Fix I: never show MISMATCH when VERIFIED
        if state == 'VERIFIED':
            self._fp_lbl.setText(
                'Key fingerprint   <span style="color:#6a6a8a;font-style:italic">'
                'N/A — confirmed by Ed25519</span>'
            )
            self._fp_lbl.setTextFormat(Qt.TextFormat.RichText)
        else:
            fp = result.get('fingerprint', '')
            if fp:
                fp_color = '#4ade80' if fp == 'MATCH' else '#f87171'
                self._fp_lbl.setText(
                    f'Key fingerprint   <span style="color:{fp_color};font-weight:bold">{fp}</span>'
                )
                self._fp_lbl.setTextFormat(Qt.TextFormat.RichText)

        detail = result.get('detail', '')
        self._ed_lbl.setText(f'Signature result   {detail}')

    def set_key_file(self, path: str):
        if path:
            self._key_file_lbl.setText(f'Public key file   {os.path.basename(path)}')
