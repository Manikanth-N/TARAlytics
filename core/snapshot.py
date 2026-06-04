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

    def to_dict(self) -> dict:
        return asdict(self)

    def title(self) -> str:
        if self.event and self.event.get('message'):
            return f"{self.event['type']}: {self.event['message']}"
        return f'Cursor @ {self.cursor_time:.2f} s'


def _agl_at(svc, data, t):
    for msg, col in _AGL_SOURCES:
        if msg in data:
            v = svc.value_at(msg, col, t)
            if v is not None:
                return v, f'{msg}.{col}'
    return None, None


def _gps_msg(data):
    return next((k for k in _GPS_KEYS if k in data), None)


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

    # control triple
    pilot = rc.pilot_input(svc, t).as_dict() if rc is not None else {}
    servo = rc.servo_output(svc, t).as_dict() if rc is not None else {}
    demand = {a: svc.value_at('ATT', _DES_COL[a], t) for a in _AXES}
    demand['throttle'] = svc.value_at('CTUN', 'ThO', t)
    response = {a: svc.value_at('ATT', _ACT_COL[a], t) for a in _AXES}
    response['throttle'] = servo.get('throttle')
    divergence = {}
    for a in _AXES:
        d, r = demand[a], response[a]
        divergence[a] = abs(_angle_diff(r, d)) if (d is not None and r is not None) else None

    # position / altitude / speed / gps
    alt, alt_src = _agl_at(svc, data, t)
    vs = diagnostics.vertical_speed_at(svc, data, t)
    gmsg = _gps_msg(data)
    speed = svc.value_at(gmsg, 'Spd', t) if gmsg else None
    fix = sats = position = None
    if gmsg:
        st = svc.latest_at(gmsg, 'Status', t)
        ns = svc.latest_at(gmsg, 'NSats', t)
        fix = GPS_FIX_NAMES.get(int(st), f'FIX_{int(st)}') if st is not None else None
        sats = int(ns) if ns is not None else None
        lat = svc.latest_at(gmsg, 'Lat', t); lng = svc.latest_at(gmsg, 'Lng', t)
        if lat is not None and lng is not None:
            position = {'lat': lat, 'lng': lng}
    if position is None and 'POS' in data:
        lat = svc.value_at('POS', 'Lat', t); lng = svc.value_at('POS', 'Lng', t)
        if lat is not None and lng is not None:
            position = {'lat': lat, 'lng': lng}

    return InvestigationSnapshot(
        index=index, captured_at=datetime.now().isoformat(timespec='seconds'),
        cursor_time=float(t), log_path=log_path,
        event=event, flight_index=flight_index, flight_total=flight_total,
        phase=phase, mode=mode, position=position,
        altitude_agl=alt, altitude_source=alt_src,
        vertical_speed=vs['value'], vertical_speed_source=vs['source'],
        ground_speed=speed, gps_fix=fix, gps_sats=sats,
        pilot=pilot, demand=demand, response=response, divergence=divergence,
        ekf=diagnostics.ekf_status_at(svc, data, t),
        position_divergence=diagnostics.position_divergence_at(svc, data, t),
        verification_state=verification_state, notes=notes, status=status)


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
