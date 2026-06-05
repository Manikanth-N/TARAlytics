import os
import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QFileDialog, QApplication,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QColor
from core.colors import badge_style
from core import verification_model as vmodel


_DARK_PANEL  = '#1a1a2a'
_DARK_BORDER = '#2a2a3a'
_COL_DIM     = '#6a6a8a'
_COL_MID     = '#9898b8'
_COL_TEXT    = '#c8c8e0'
_COL_MONO    = '#d0d0e8'

# ── Presentation maps (UI only — no classification logic) ────────────────────
# Hero accent + card background by semantic tone (mirrors verification_model tones).
_TONE_STYLE = {
    'good':    ('#00C896', '#102320'),
    'warn':    ('#FFB300', '#2a2310'),
    'bad':     ('#FF3D3D', '#2a1414'),
    'neutral': ('#9aa6b8', '#1b1b2a'),
    'muted':   ('#9aa6b8', '#1b1b2a'),
}
_TONE_ICON = {'good': '✓', 'warn': '⚠', 'bad': '✗', 'neutral': '—', 'muted': '—'}

# Plain-language hero headline per state (presentation copy).
_HEADLINE = {
    'VERIFIED':  'Integrity Confirmed',
    'PARTIAL':   'Integrity Confirmed — Incomplete Closure',
    'UNSIGNED':  'Unsigned Log',
    'INVALID':   'Verification Failed',
    'CORRUPTED': 'Integrity Undeterminable',
    'UNKNOWN':   'Not Verified',
    'WRONG_KEY': 'Key Mismatch',
}

# "Usable For" checklist by state (approved mapping).
_USABLE_FOR = {
    'VERIFIED':  [('✓', 'Flight Review'), ('✓', 'Evidence Generation'), ('✓', 'Certification Review')],
    'PARTIAL':   [('✓', 'Flight Review'), ('✓', 'Evidence Generation'), ('⚠', 'Certification Review')],
    'UNSIGNED':  [('✓', 'Flight Review'), ('⚠', 'Evidence Generation'), ('✗', 'Certification Review')],
    'INVALID':   [('✗', 'Flight Review'), ('✗', 'Evidence Generation'), ('✗', 'Certification Review')],
    'CORRUPTED': [('✗', 'Flight Review'), ('✗', 'Evidence Generation'), ('✗', 'Certification Review')],
    'UNKNOWN':   [('⏳', 'Load Key To Confirm')],
    'WRONG_KEY': [('⏳', 'Load Correct Key')],
}
_MARK_COLOR = {'✓': '#00C896', '⚠': '#FFB300', '✗': '#FF3D3D', '⏳': '#E65100'}

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
        self.setStyleSheet('background: transparent;')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(8)

        lbl = QLabel(label)
        lbl.setFixedWidth(180)
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


def _section_title(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f'color: {_COL_DIM}; font-size: 10px; font-weight: bold; '
        f'letter-spacing: 1px; background: transparent; border: none;')
    return lbl


def _sep_line() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet(f'border: 1px solid {_DARK_BORDER}; background: transparent;')
    return f


class SignaturePanel(QFrame):
    """Verification dashboard — answers "can I trust this log?" at a glance.

    Four zones, by hierarchy: (1) hero verdict card, (2) Usable-For checklist,
    (3) Verification Details, (4) collapsible Technical Information. Pure layout —
    every value comes from verification_model / the verify result; no logic here.
    """
    key_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            f'SignaturePanel {{ background: {_DARK_PANEL}; '
            f'border: 1px solid {_DARK_BORDER}; border-radius: 8px; }}'
        )
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(pal.ColorRole.Window, QColor(_DARK_PANEL))
        self.setPalette(pal)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(7)

        root.addWidget(self._build_hero())
        root.addWidget(self._build_usable_for())
        root.addWidget(self._build_details())
        root.addWidget(self._build_technical())
        root.addStretch(1)

    # ── ZONE 1 — hero verdict card ───────────────────────────────────────────
    def _build_hero(self) -> QFrame:
        self._hero = QFrame()
        self._hero.setObjectName('hero')
        hl = QVBoxLayout(self._hero)
        hl.setContentsMargins(16, 11, 16, 11)
        hl.setSpacing(3)

        top = QHBoxLayout(); top.setSpacing(10)
        self._icon = QLabel('—')
        self._icon.setStyleSheet('font-size: 22px; font-weight: bold; background: transparent; border: none;')
        top.addWidget(self._icon)
        self._badge = QLabel(vmodel.label('UNKNOWN'))
        self._badge.setStyleSheet(
            'font-size: 21px; font-weight: bold; background: transparent; border: none;')
        top.addWidget(self._badge)
        top.addStretch()
        self._algo_lbl = QLabel('')
        self._algo_lbl.setStyleSheet(
            f'font-size: 11px; color: {_COL_DIM}; background: transparent; border: none;')
        self._algo_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(self._algo_lbl)
        hl.addLayout(top)

        self._headline = QLabel('')
        self._headline.setStyleSheet(
            'font-size: 13px; font-weight: 600; color: #e8e8f4; background: transparent; border: none;')
        hl.addWidget(self._headline)

        self._op_lbl = QLabel('')
        self._op_lbl.setWordWrap(True)
        self._op_lbl.setStyleSheet(
            f'font-size: 12px; color: {_COL_TEXT}; background: transparent; border: none;')
        hl.addWidget(self._op_lbl)

        # Verification-completed timestamp lives inside the hero (no extra row).
        self._verified_at = QLabel('')
        self._verified_at.setStyleSheet(
            f'font-size: 10px; color: {_COL_DIM}; background: transparent; border: none;')
        self._verified_at.setAlignment(Qt.AlignmentFlag.AlignRight)
        hl.addWidget(self._verified_at)

        self._apply_hero_tone('muted', '#9aa6b8')
        return self._hero

    def _apply_hero_tone(self, tone: str, accent: str):
        accent, bg = _TONE_STYLE.get(tone, (accent, _DARK_PANEL))
        self._hero.setStyleSheet(
            f'#hero {{ background: {bg}; border: 1px solid {accent}; border-radius: 8px; }}')
        self._icon.setStyleSheet(
            f'font-size: 26px; font-weight: bold; color: {accent}; background: transparent; border: none;')
        self._badge.setStyleSheet(
            f'font-size: 24px; font-weight: bold; color: {accent}; background: transparent; border: none;')

    # ── ZONE 2 — Usable-For checklist ────────────────────────────────────────
    def _build_usable_for(self) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box); v.setContentsMargins(2, 0, 2, 0); v.setSpacing(5)
        v.addWidget(_section_title('INVESTIGATOR GUIDANCE'))
        self._guidance_lbl = QLabel('')
        self._guidance_lbl.setWordWrap(True)
        self._guidance_lbl.setStyleSheet(
            f'font-size: 11px; color: {_COL_MID}; background: transparent; border: none;')
        v.addWidget(self._guidance_lbl)
        self._usable_caption = QLabel('This log can be used for:')
        self._usable_caption.setStyleSheet(
            f'font-size: 11px; color: {_COL_DIM}; background: transparent; border: none;')
        v.addWidget(self._usable_caption)
        self._usable_box = QVBoxLayout(); self._usable_box.setSpacing(3)
        v.addLayout(self._usable_box)
        return box

    def _rebuild_usable_for(self, state: str):
        while self._usable_box.count():
            item = self._usable_box.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        for mark, text in _USABLE_FOR.get(state, []):
            row = QWidget()
            rl = QHBoxLayout(row); rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(8)
            m = QLabel(mark)
            m.setFixedWidth(16)
            m.setStyleSheet(
                f'font-size: 13px; font-weight: bold; color: {_MARK_COLOR.get(mark, _COL_MID)}; '
                f'background: transparent; border: none;')
            t = QLabel(text)
            t.setStyleSheet(f'font-size: 12px; color: {_COL_TEXT}; background: transparent; border: none;')
            rl.addWidget(m); rl.addWidget(t); rl.addStretch()
            self._usable_box.addWidget(row)

    # ── ZONE 3 — Verification Details ────────────────────────────────────────
    def _build_details(self) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box); v.setContentsMargins(2, 0, 2, 0); v.setSpacing(4)
        v.addWidget(_section_title('VERIFICATION DETAILS'))
        self._range_val = self._kv(v, 'Signed range')
        self._struct_val = self._kv(v, 'Structure')
        self._chain_val = self._kv(v, 'Hash chain')
        self._sig_val = self._kv(v, 'Signature result')
        return box

    def _kv(self, layout: QVBoxLayout, title: str) -> QLabel:
        row = QHBoxLayout(); row.setSpacing(8)
        t = QLabel(title)
        t.setFixedWidth(120)
        t.setStyleSheet(f'font-size: 11px; color: {_COL_DIM}; background: transparent; border: none;')
        val = QLabel('—')
        val.setStyleSheet(f'font-size: 12px; color: {_COL_TEXT}; background: transparent; border: none;')
        val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(t); row.addWidget(val, 1)
        layout.addLayout(row)
        return val

    # ── ZONE 4 — Technical Information (collapsed by default) ─────────────────
    def _build_technical(self) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box); v.setContentsMargins(2, 0, 2, 0); v.setSpacing(6)

        self._tech_toggle = QPushButton('▸  Technical Information')
        self._tech_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tech_toggle.setStyleSheet(
            'QPushButton { text-align: left; color: #9898b8; background: transparent; '
            'border: none; font-size: 10px; font-weight: bold; letter-spacing: 1px; padding: 2px 0; }'
            'QPushButton:hover { color: #c8c8e8; }')
        self._tech_toggle.clicked.connect(self._toggle_technical)
        v.addWidget(self._tech_toggle)

        self._tech_body = QWidget()
        tv = QVBoxLayout(self._tech_body); tv.setContentsMargins(0, 0, 0, 0); tv.setSpacing(4)

        meta_row = QHBoxLayout(); meta_row.setSpacing(20)
        self._dev_lbl = self._mini('Device  —')
        self._fw_lbl = self._mini('FW  —')
        self._ts_lbl = self._mini('Signed at  —')
        self._ctr_lbl = self._mini('Log #  —')
        for w in (self._dev_lbl, self._fw_lbl, self._ts_lbl, self._ctr_lbl):
            meta_row.addWidget(w)
        meta_row.addStretch()
        tv.addLayout(meta_row)

        self._key_id_lbl = self._mini('Key ID  —')
        tv.addWidget(self._key_id_lbl)
        self._fp_lbl = self._mini('Key fingerprint  —')
        tv.addWidget(self._fp_lbl)

        self._sha_signed = HashRow('SHA256 (signed range)')
        self._sha_full = HashRow('SHA256 (full file)')
        self._header_mac = HashRow('Header MAC (H0)')
        tv.addWidget(self._sha_signed)
        tv.addWidget(self._sha_full)
        tv.addWidget(self._header_mac)

        key_row = QHBoxLayout(); key_row.setSpacing(8)
        self._key_file_lbl = self._mini('Public key file  (none)')
        key_row.addWidget(self._key_file_lbl, 1)
        self._change_key_btn = QPushButton('Change Key')
        self._change_key_btn.setStyleSheet(
            'QPushButton { background: #1a4a8a; color: #c8d8f8; border-radius: 4px; '
            'padding: 2px 10px; font-size: 11px; border: 1px solid #2a5a9a; }'
            'QPushButton:hover { background: #2a5a9a; }')
        self._change_key_btn.clicked.connect(self._browse_key)
        key_row.addWidget(self._change_key_btn)
        tv.addLayout(key_row)

        self._tech_open = False
        self._tech_body.setVisible(False)          # collapsed by default
        v.addWidget(self._tech_body)
        return box

    def _mini(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f'font-size: 11px; border: none; color: {_COL_MID}; background: transparent;')
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return lbl

    def _toggle_technical(self):
        self._tech_open = not self._tech_open
        self._tech_body.setVisible(self._tech_open)
        self._tech_toggle.setText(
            ('▾' if self._tech_open else '▸') + '  Technical Information')

    # ── key picker ───────────────────────────────────────────────────────────
    def _browse_key(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Open Public Key', '', 'Key Files (*.dat);;All Files (*)'
        )
        if path:
            self.key_changed.emit(path)

    # ── population ───────────────────────────────────────────────────────────
    def update_verification(self, result: dict, key_path: str = ''):
        state = vmodel.normalize_state(result.get('state', 'UNKNOWN'))
        vinfo = vmodel.info(state)
        fg, _bg = badge_style(state)

        # ZONE 1 — hero
        self._apply_hero_tone(vinfo.tone, vinfo.color)
        self._icon.setText(_TONE_ICON.get(vinfo.tone, '—'))
        self._badge.setText(vinfo.label)
        self._headline.setText(_HEADLINE.get(state, vinfo.short_msg))
        self._op_lbl.setText(vinfo.operational_meaning)
        self._algo_lbl.setText(result.get('algo_name', ''))
        self._verified_at.setText(
            f'Verification completed {datetime.datetime.now():%Y-%m-%d %H:%M:%S}')

        # ZONE 2 — guidance + usable-for
        self._guidance_lbl.setText(vinfo.investigator_guidance)
        self._rebuild_usable_for(state)

        # ZONE 3 — details
        hashes = result.get('hashes', {})
        if hashes:
            ds = hashes.get('data_start', 0); dl = hashes.get('data_len', 0)
            self._range_val.setText(f'{ds} → {ds + dl:,}  ({dl:,} bytes)')
        else:
            self._range_val.setText('—')
        self._struct_val.setText(
            'PASS ✓' if result.get('structure_ok')
            else (result.get('structure_message', '') or 'FAIL ✗'))
        chunks = result.get('chain_chunks', 0)
        if chunks > 0:
            ok = result.get('chain_ok', False)
            col = '#4ade80' if ok else '#f87171'
            self._chain_val.setText(
                f'<span style="color:{col};font-weight:bold">{chunks} chunks '
                f'{"✓" if ok else "✗"}</span>')
            self._chain_val.setTextFormat(Qt.TextFormat.RichText)
        else:
            self._chain_val.setText('not present')
        self._sig_val.setText(result.get('detail', '') or '—')

        # ZONE 4 — technical
        if hashes:
            self._sha_signed.set_value(hashes.get('sha256_signed', ''))
            self._sha_full.set_value(hashes.get('sha256_full', ''))
            self._header_mac.set_value(hashes.get('header_mac', ''))
            ki = hashes.get('key_id', '')
            if ki:
                ki_fmt = ' '.join(ki[i:i + 2] for i in range(0, len(ki), 2))
                self._key_id_lbl.setText(f'Key ID  {ki_fmt}')
        else:
            self._sha_signed.set_value(''); self._sha_full.set_value('')
            self._header_mac.set_value(''); self._key_id_lbl.setText('Key ID  —')

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

        # fingerprint — never show MISMATCH when VERIFIED
        if state == 'VERIFIED':
            self._fp_lbl.setText('Key fingerprint  N/A — confirmed by Ed25519')
            self._fp_lbl.setTextFormat(Qt.TextFormat.PlainText)
        else:
            fp = result.get('fingerprint', '')
            if fp:
                col = '#4ade80' if fp == 'MATCH' else '#f87171'
                self._fp_lbl.setText(
                    f'Key fingerprint  <span style="color:{col};font-weight:bold">{fp}</span>')
                self._fp_lbl.setTextFormat(Qt.TextFormat.RichText)
            else:
                self._fp_lbl.setText('Key fingerprint  —')

        if key_path:
            self._key_file_lbl.setText(f'Public key file  {os.path.basename(key_path)}')

    def set_key_file(self, path: str):
        if path:
            self._key_file_lbl.setText(f'Public key file  {os.path.basename(path)}')
