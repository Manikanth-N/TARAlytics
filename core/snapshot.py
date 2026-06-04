"""
Investigation Snapshot system (P2).

An InvestigationSnapshot is a structured, provenance-bearing capture of one cursor
moment — everything an engineer needs to record a finding: the event, flight window,
time, position, altitude, phase, mode, the pilot/controller/aircraft control triple,
diagnostic aids (vertical speed, EKF health, position divergence), verification
state, notes and status.

`build_snapshot` is pure: it takes the shared services (SampleService / TimelineModel
/ RCModel) and resolves every field at the cursor time, so the snapshot reflects
exactly what the live surfaces show. `SnapshotStore` holds a session's captures.

No Qt here — exporters (JSON / Markdown / PDF) consume `to_dict()`.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional
import math

from core.health_analyzer import GPS_FIX_NAMES
from core import diagnostics

_AGL_SOURCES = [('POS', 'RelHomeAlt'), ('BARO[0]', 'Alt'), ('BARO', 'Alt'), ('POS', 'Alt')]
_GPS_KEYS = ('GPS[0]', 'GPS')
_AXES = ('roll', 'pitch', 'yaw')
_DES_COL = {'roll': 'DesRoll', 'pitch': 'DesPitch', 'yaw': 'DesYaw'}
_ACT_COL = {'roll': 'Roll', 'pitch': 'Pitch', 'yaw': 'Yaw'}


def _angle_diff(a: float, b: float) -> float:
    return ((a - b + 180.0) % 360.0) - 180.0


@dataclass
class InvestigationSnapshot:
    # Not frozen: notes and status are edited after capture (in the Evidence module).
    index: int                       # 1-based within the session
    captured_at: str                 # wall-clock ISO time of capture
    cursor_time: float               # absolute flight time (s)
    log_path: str

    event: Optional[dict]            # {time, severity, type, message} or None
    flight_index: Optional[int]      # 0-based armed flight, or None (not armed)
    flight_total: int

    phase: Optional[str]
    mode: Optional[str]
    position: Optional[dict]         # {lat, lng} when available
    altitude_agl: Optional[float]
    altitude_source: Optional[str]
    vertical_speed: Optional[float]
    vertical_speed_source: Optional[str]
    ground_speed: Optional[float]
    gps_fix: Optional[str]
    gps_sats: Optional[int]

    pilot: dict                      # {roll,pitch,yaw,throttle}
    demand: dict                     # {roll,pitch,yaw,throttle}
    response: dict                   # {roll,pitch,yaw,throttle}
    divergence: dict                 # {roll,pitch,yaw} deg

    ekf: dict                        # diagnostics.ekf_status_at output
    position_divergence: dict        # diagnostics.position_divergence_at output

    verification_state: str
    notes: str = ''
    status: str = 'OPEN'

    # Provenance for every value that originates from SampleService (P2.1):
    # {logical_field: {msg, col, value, sample_timestamp, interpolated, bracket}}.
    provenance: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def title(self) -> str:
        if self.event and self.event.get('message'):
            return f"{self.event['type']}: {self.event['message']}"
        return f'Cursor @ {self.cursor_time:.2f} s'


def _gps_msg(data):
    return next((k for k in _GPS_KEYS if k in data), None)


def _agl_source(data):
    return next(((m, c) for m, c in _AGL_SOURCES if m in data), (None, None))


class _Provenance:
    """Records the source of every SampleService-derived value: source message +
    field, the resolved value, the sample timestamp, whether it was interpolated,
    and (when interpolated) the bracketing sample times."""

    def __init__(self, svc):
        self._svc = svc
        self.records: dict = {}

    def cont(self, key: str, msg: str, col: str, t: float):
        """Continuous read (sample_at) with full interpolation provenance."""
        s = self._svc.sample_at(msg, col, t)
        self.records[key] = {
            'msg': msg, 'col': col, 'value': s.value,
            'sample_timestamp': s.sample_t, 'interpolated': s.interpolated,
            'bracket': list(s.bracket) if s.bracket else None}
        return s.value

    def disc(self, key: str, msg: str, col: str, t: float):
        """Discrete / held read (latest_at); records the held sample's timestamp."""
        v = self._svc.latest_at(msg, col, t)
        self.records[key] = {
            'msg': msg, 'col': col, 'value': v,
            'sample_timestamp': self._svc.sample_time(msg, t),
            'interpolated': False, 'bracket': None}
        return v


def _nearest_event(tm, t: float, window: float = 5.0) -> Optional[dict]:
    """Nearest event within `window` seconds of t, as a dict (or None)."""
    best, best_dt = None, window
    for ts, sev, ty, msg in tm.event_regions():
        dt = abs(ts - t)
        if dt <= best_dt:
            best, best_dt = (ts, sev, ty, msg), dt
    if best is None:
        return None
    ts, sev, ty, msg = best
    return {'time': float(ts), 'severity': sev, 'type': ty, 'message': msg}


def build_snapshot(*, index: int, svc, tm, rc, data: dict, t: float,
                   verification_state: str, log_path: str = '',
                   event: Optional[dict] = None, notes: str = '',
                   status: str = 'OPEN') -> InvestigationSnapshot:
    """Resolve every snapshot field at cursor time t through the shared services."""
    # event (explicit selection, else nearest)
    if event is None and tm is not None:
        event = _nearest_event(tm, t)

    # flight window
    flight_index, flight_total = None, 0
    if tm is not None:
        flights = tm.flight_windows()
        flight_total = len(flights)
        flight_index = next((f.index for f in flights if f.contains(t)), None)

    phase = mode = None
    if tm is not None:
        ph = tm.phase_at(t); phase = ph.kind if ph else None
        mode = tm.mode_at(t)

    prov = _Provenance(svc)

    # control triple (every SampleService read recorded with provenance)
    pilot = rc.pilot_input(svc, t).as_dict() if rc is not None else {}
    servo = rc.servo_output(svc, t).as_dict() if rc is not None else {}
    if rc is not None:
        for a in ('roll', 'pitch', 'yaw', 'throttle'):
            ch = rc.channel_for(a)
            prov.cont(f'pilot_{a}', 'RCIN', f'C{ch}', t)
            prov.cont(f'servo_{a}', 'RCOU', f'C{ch}', t)
    demand = {a: prov.cont(f'demand_{a}', 'ATT', _DES_COL[a], t) for a in _AXES}
    demand['throttle'] = prov.cont('demand_throttle', 'CTUN', 'ThO', t)
    response = {a: prov.cont(f'response_{a}', 'ATT', _ACT_COL[a], t) for a in _AXES}
    response['throttle'] = servo.get('throttle')
    divergence = {}
    for a in _AXES:
        d, r = demand[a], response[a]
        divergence[a] = abs(_angle_diff(r, d)) if (d is not None and r is not None) else None

    # altitude (with the chosen source field)
    alt_msg, alt_col = _agl_source(data)
    if alt_msg is not None:
        alt = prov.cont('altitude_agl', alt_msg, alt_col, t)
        alt_src = f'{alt_msg}.{alt_col}'
    else:
        alt, alt_src = None, None

    # vertical speed (record provenance for the direct-field sources; the
    # derivative fallback is computed, not a single sample)
    vs = diagnostics.vertical_speed_at(svc, data, t)
    if vs['value'] is not None and '.' in vs['source'] and ' ' not in vs['source']:
        vmsg, vcol = vs['source'].split('.', 1)
        prov.cont('vertical_speed', vmsg, vcol, t)

    # ground speed / gps
    gmsg = _gps_msg(data)
    speed = prov.cont('ground_speed', gmsg, 'Spd', t) if gmsg else None
    fix = sats = position = None
    if gmsg:
        st = prov.disc('gps_status', gmsg, 'Status', t)
        ns = prov.disc('gps_sats', gmsg, 'NSats', t)
        fix = GPS_FIX_NAMES.get(int(st), f'FIX_{int(st)}') if st is not None else None
        sats = int(ns) if ns is not None else None
        lat = prov.cont('position_lat', gmsg, 'Lat', t)
        lng = prov.cont('position_lng', gmsg, 'Lng', t)
        if lat is not None and lng is not None:
            position = {'lat': lat, 'lng': lng}
    if position is None and 'POS' in data:
        lat = prov.cont('position_lat', 'POS', 'Lat', t)
        lng = prov.cont('position_lng', 'POS', 'Lng', t)
        if lat is not None and lng is not None:
            position = {'lat': lat, 'lng': lng}

    # diagnostics + their source-field provenance
    ekf = diagnostics.ekf_status_at(svc, data, t)
    if ekf.get('ratio') is not None and ekf.get('source') not in (None, 'none'):
        prov.cont('ekf_worst', ekf['source'], ekf['worst'], t)
    posdiv = diagnostics.position_divergence_at(svc, data, t)
    if posdiv.get('value') is not None and posdiv.get('source') not in (None, 'none'):
        prov.cont('posdiv_ipn', posdiv['source'], 'IPN', t)
        prov.cont('posdiv_ipe', posdiv['source'], 'IPE', t)

    return InvestigationSnapshot(
        index=index, captured_at=datetime.now().isoformat(timespec='seconds'),
        cursor_time=float(t), log_path=log_path,
        event=event, flight_index=flight_index, flight_total=flight_total,
        phase=phase, mode=mode, position=position,
        altitude_agl=alt, altitude_source=alt_src,
        vertical_speed=vs['value'], vertical_speed_source=vs['source'],
        ground_speed=speed, gps_fix=fix, gps_sats=sats,
        pilot=pilot, demand=demand, response=response, divergence=divergence,
        ekf=ekf, position_divergence=posdiv,
        verification_state=verification_state, notes=notes, status=status,
        provenance=prov.records)


class SnapshotStore:
    """A session's captured snapshots (held by AppState). Cleared on log reload."""

    def __init__(self):
        self._items: list[InvestigationSnapshot] = []

    def add(self, snap: InvestigationSnapshot) -> InvestigationSnapshot:
        self._items.append(snap)
        return snap

    def remove(self, index_in_list: int):
        if 0 <= index_in_list < len(self._items):
            del self._items[index_in_list]

    def clear(self):
        self._items.clear()

    def all(self) -> list:
        return list(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, i) -> InvestigationSnapshot:
        return self._items[i]
