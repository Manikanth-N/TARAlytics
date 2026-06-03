"""
Central application state for TARAlytics.

AppState is the single source of truth. Modules read state from it and connect
to its signals; no module holds a direct reference to another module. This
replaces the previous pattern of direct cross-tab attribute access
(`self._mw._tab_plotter...`).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal


@dataclass
class FlightMeta:
    serial_number: str = '—'
    device_id:     str = '—'
    firmware:      str = '—'
    frame_type:    str = '—'
    log_counter:   int = 0
    file_path:     str = ''
    file_size:     int = 0
    t_min:         float = 0.0
    t_max:         float = 0.0
    duration_s:    float = 0.0
    max_alt_m:     float = 0.0


@dataclass
class VerifyResult:
    state:         str = 'NOT_LOADED'
    detail:        str = ''
    structure_ok:  bool = False
    chain_chunks:  int = 0
    chain_ok:      bool = False
    algo_name:     str = '—'
    key_id:        str = '—'
    sha256_signed: str = '—'
    sha256_full:   str = '—'
    fingerprint:   str = '—'
    header_info:   dict = field(default_factory=dict)


class AppState(QObject):
    """Single source of truth; modules communicate only through these signals."""

    data_changed         = pyqtSignal(dict)     # full parsed data dict
    verification_changed = pyqtSignal(object)   # VerifyResult
    meta_changed         = pyqtSignal(object)   # FlightMeta
    cursor_time_changed  = pyqtSignal(float)    # absolute time
    event_jumped         = pyqtSignal(float)    # absolute time (event click)
    module_requested     = pyqtSignal(int)      # nav rail / module switch
    parse_progress       = pyqtSignal(int)      # 0-100
    parse_started        = pyqtSignal()
    parse_error          = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data:       dict          = {}
        self._raw_bytes:  bytes         = b''
        self._pubkey_str: Optional[str] = None
        self._key_path:   str           = ''
        self._bin_path:   str           = ''
        self._meta:       FlightMeta    = FlightMeta()
        self._verify:     VerifyResult  = VerifyResult()

    # ── Read-only properties ───────────────────────────────────────────────

    @property
    def data(self) -> dict:              return self._data
    @property
    def raw_bytes(self) -> bytes:        return self._raw_bytes
    @property
    def pubkey_str(self) -> Optional[str]: return self._pubkey_str
    @property
    def key_path(self) -> str:           return self._key_path
    @property
    def bin_path(self) -> str:           return self._bin_path
    @property
    def meta(self) -> FlightMeta:        return self._meta
    @property
    def verification(self) -> VerifyResult: return self._verify
    @property
    def has_data(self) -> bool:          return bool(self._data)

    # ── Mutators (emit signals) ────────────────────────────────────────────

    def set_parsed_data(self, data: dict, raw_bytes: bytes, bin_path: str):
        self._data = data
        self._raw_bytes = raw_bytes
        self._bin_path = bin_path
        self._meta = self._extract_meta(data, raw_bytes, bin_path)
        self.meta_changed.emit(self._meta)
        self.data_changed.emit(data)

    def set_verification(self, result: dict):
        h = result.get('hashes', {}) or {}
        ki = h.get('key_id', '')
        if ki:
            ki = ' '.join(ki[i:i + 2] for i in range(0, len(ki), 2))
        self._verify = VerifyResult(
            state=result.get('state', 'ERROR'),
            detail=result.get('detail', ''),
            structure_ok=result.get('structure_ok', False),
            chain_chunks=result.get('chain_chunks', 0),
            chain_ok=result.get('chain_ok', False),
            algo_name=result.get('algo_name', '—'),
            key_id=ki or '—',
            sha256_signed=h.get('sha256_signed', '—'),
            sha256_full=h.get('sha256_full', '—'),
            fingerprint=result.get('fingerprint', '—'),
            header_info=result.get('header_info', {}) or {},
        )
        self.verification_changed.emit(self._verify)

    def set_pubkey(self, pubkey_str: Optional[str], key_path: str):
        self._pubkey_str = pubkey_str
        self._key_path = key_path

    def set_cursor_time(self, t_absolute: float):
        self.cursor_time_changed.emit(t_absolute)

    def jump_to_event(self, t_absolute: float):
        self.event_jumped.emit(t_absolute)

    def request_module(self, index: int):
        self.module_requested.emit(index)

    # ── Metadata extraction ────────────────────────────────────────────────

    def _extract_meta(self, data: dict, raw_bytes: bytes, bin_path: str) -> FlightMeta:
        import os
        import numpy as np
        from core import signature_verifier
        from core.flight_metrics import FlightMetrics
        from core.health_analyzer import HealthAnalyzer

        meta = FlightMeta()
        meta.file_path = bin_path
        meta.file_size = os.path.getsize(bin_path) if os.path.isfile(bin_path) else len(raw_bytes)

        dur, _ = FlightMetrics.duration(data)
        alt, _ = FlightMetrics.max_altitude(data)
        meta.duration_s = dur
        meta.max_alt_m = alt

        all_t = []
        for df in data.values():
            if 'TimeS' in df.columns:
                all_t.extend(df['TimeS'].dropna().tolist())
        if all_t:
            meta.t_min = float(np.min(all_t))
            meta.t_max = float(np.max(all_t))

        if raw_bytes[:2] == bytes([0xA5, 0x01]):
            info = signature_verifier.parse_header(raw_bytes)
            meta.firmware    = info.get('fw_ver', '—')
            meta.device_id   = info.get('device_id', '—')
            meta.log_counter = info.get('log_ctr', 0)

        fw = HealthAnalyzer.firmware(data)
        if fw['text'] and fw['text'] != 'UNKNOWN':
            meta.firmware = fw['text']
        veh = HealthAnalyzer.vehicle(data)
        if veh['frame'] and veh['frame'] != 'UNKNOWN':
            meta.frame_type = veh['frame']

        # Serial number: Sprint-1 has no fleet registry; fall back to device_id.
        meta.serial_number = meta.device_id

        return meta
