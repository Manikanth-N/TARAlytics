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
    state:         str = 'UNKNOWN'
    detail:        str = ''
    structure_ok:  bool = False
    chain_chunks:  int = 0
    chain_ok:      bool = False
    chain_valid:   bool = False   # keyless hash-chain integrity for chunks present
    closed:        bool = False   # END record present (log closed cleanly)
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
    snapshots_changed    = pyqtSignal()         # investigation snapshot store changed
    plot_request         = pyqtSignal(str)      # request plotter load a preset/category
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

        # ── shared cursor backbone ──────────────────────────────────────────
        self._cursor_time: float = 0.0
        self._broadcasting: bool = False      # loop-prevention guard
        self._cursor_subscribers: list[str] = []   # named, for debug/introspection
        # lazy services, rebuilt on data_changed; shared by every cursor surface
        self._sample_service = None
        self._timeline_model = None
        self._rc_model = None
        self._flight_report = None     # whole-flight analytics (P3)
        self._playback = None          # single playback controller (lazy)

        # investigation snapshots (P2) — per-log session, cleared on reload
        from core.snapshot import SnapshotStore
        self._snapshots = SnapshotStore()

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
        # Invalidate lazy services and reset the cursor for the new log.
        self._sample_service = None
        self._timeline_model = None
        self._rc_model = None
        self._flight_report = None
        self._cursor_time = 0.0
        # Snapshots reference this log; clear them on reload.
        self._snapshots.clear()
        self.meta_changed.emit(self._meta)
        self.data_changed.emit(data)
        self.snapshots_changed.emit()

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
            chain_valid=result.get('chain_valid', False),
            closed=result.get('closed', False),
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
        """
        Move the one shared cursor and broadcast it to every subscriber.

        Loop-prevention: a subscriber whose cursor_time_changed handler calls
        set_cursor_time again (e.g. a widget that snaps the value) is ignored
        while a broadcast is in flight, so there is no feedback loop. The store
        is updated and the signal emitted exactly once per user interaction.
        """
        if self._broadcasting:
            return
        self._cursor_time = float(t_absolute)
        self._broadcasting = True
        try:
            self.cursor_time_changed.emit(self._cursor_time)
        finally:
            self._broadcasting = False

    @property
    def cursor_time(self) -> float:
        """Last cursor time — for surfaces that subscribe late or need to read
        the current position without waiting for the next move."""
        return self._cursor_time

    def jump_to_event(self, t_absolute: float):
        """Event selection: record + emit event_jumped and move the shared cursor
        in one operation, so all surfaces update from a single user action."""
        self.event_jumped.emit(float(t_absolute))
        self.set_cursor_time(t_absolute)

    # ── Investigation snapshots (P2) ────────────────────────────────────────

    @property
    def snapshots(self):
        """The session's SnapshotStore (Evidence module reads this)."""
        return self._snapshots

    def capture_snapshot(self, event: Optional[dict] = None,
                         notes: str = '', status: str = 'OPEN'):
        """Build an InvestigationSnapshot at the current cursor from the shared
        services and append it to the store. Returns the snapshot, or None if no
        data is loaded."""
        if not self._data:
            return None
        from core.snapshot import build_snapshot
        snap = build_snapshot(
            index=len(self._snapshots) + 1,
            svc=self.sample_service, tm=self.timeline_model, rc=self.rc_model,
            data=self._data, t=self._cursor_time,
            verification_state=self._verify.state,
            log_path=self._bin_path, event=event, notes=notes, status=status)
        self._snapshots.add(snap)
        self.snapshots_changed.emit()
        return snap

    def remove_snapshot(self, index_in_list: int):
        self._snapshots.remove(index_in_list)
        self.snapshots_changed.emit()

    def clear_snapshots(self):
        self._snapshots.clear()
        self.snapshots_changed.emit()

    def evidence_meta(self) -> dict:
        """Report metadata for the evidence exporters."""
        v = self._verify
        return {
            'log_path': self._bin_path,
            'serial_number': self._meta.serial_number,
            'firmware': self._meta.firmware,
            'frame_type': self._meta.frame_type,
            'verification_state': v.state,
            'verification': {
                'state': v.state,
                'algo_name': v.algo_name,
                'chain_chunks': v.chain_chunks,
                'chain_valid': v.chain_valid,
                'chain_ok': v.chain_ok,
                'closed': v.closed,
            },
        }

    def connect_cursor(self, slot, name: str):
        """Subscribe a surface to the shared cursor and register it by name.

        Equivalent to ``cursor_time_changed.connect(slot)`` but also records a
        human-readable name so ``cursor_debug_info()`` can list who is wired to
        the cursor — used purely for synchronization debugging.
        """
        self.cursor_time_changed.connect(slot)
        self._cursor_subscribers.append(name)

    def cursor_debug_info(self) -> dict:
        """Lightweight introspection of the shared-cursor backbone.

        For synchronization debugging only — reports the live cursor time, the
        broadcasting guard state, how many slots are wired to the cursor signal
        (Qt's own count, incl. anonymous direct connects), and the names of the
        subscribers registered via ``connect_cursor``.
        """
        try:
            qt_count = self.receivers(self.cursor_time_changed)
        except Exception:
            qt_count = -1
        return {
            'cursor_time':      self._cursor_time,
            'broadcasting':     self._broadcasting,
            'subscriber_count': qt_count,
            'named_count':      len(self._cursor_subscribers),
            'subscribers':      list(self._cursor_subscribers),
        }

    def request_module(self, index: int):
        self.module_requested.emit(index)

    def request_plot(self, preset_or_category: str):
        """Ask the Signal Plotter to load the signals for a preset / finding category
        (event-to-signal linking)."""
        self.plot_request.emit(str(preset_or_category))

    # ── Lazy shared services (built once per log, on first access) ───────────

    @property
    def sample_service(self):
        """Shared SampleService over the current data (value-at-cursor engine)."""
        if self._sample_service is None and self._data:
            from core.sample_service import SampleService
            self._sample_service = SampleService(self._data)
        return self._sample_service

    @property
    def playback(self):
        """The single PlaybackController for this window — the one timer / play
        state / speed that drives the shared cursor. Lazy and persistent across log
        reloads (it is a controller, not data). Added in Phase A; not yet wired to the
        transport/replay views (no behavior change until a later phase)."""
        if self._playback is None:
            from ui.playback_controller import PlaybackController
            self._playback = PlaybackController(self)
        return self._playback

    @property
    def timeline_model(self):
        """Shared TimelineModel over the current data (phases/modes/flights/etc.)."""
        if self._timeline_model is None and self._data:
            from core.timeline_model import TimelineModel
            self._timeline_model = TimelineModel(self._data)
        return self._timeline_model

    @property
    def rc_model(self):
        """Shared RCModel over the current data (semantic pilot intent)."""
        if self._rc_model is None and self._data:
            from core.rc_model import RCModel
            self._rc_model = RCModel.from_data(self._data)
        return self._rc_model

    @property
    def flight_report(self):
        """Whole-flight analytics (P3) — 'was this a good flight?'. Built once per
        log over the shared TimelineModel, cached."""
        if self._flight_report is None and self._data:
            from core.flight_analytics import FlightAnalytics
            self._flight_report = FlightAnalytics(self._data, self.timeline_model).report()
        return self._flight_report

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
