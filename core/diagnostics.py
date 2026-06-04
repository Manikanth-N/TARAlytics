"""
Cursor-time diagnostic aids (P2): vertical speed, EKF health, and position
divergence, resolved through the shared SampleService at a given time.

These are investigation aids, not cosmetics: each returns a value plus a state
(OK / CAUTION / CRITICAL) and the source field, so the Context panel, the
Situation surfaces, and the Investigation Snapshot all read the same numbers with
provenance. Pure core: no Qt. Never fabricates — returns None when the source is
absent.
"""
from __future__ import annotations
from typing import Optional
import math

# state thresholds (documented, conservative)
_EKF_WARN, _EKF_CRIT = 0.5, 1.0       # XKF4 normalised test ratios (1.0 = reject)
_POSDIV_WARN, _POSDIV_CRIT = 0.5, 2.0  # metres of EKF position innovation
_OK, _CAUTION, _CRITICAL = 'OK', 'CAUTION', 'CRITICAL'

_VSPEED_SOURCES = [('BARO[0]', 'CRt', 1.0), ('BARO', 'CRt', 1.0),
                   ('CTUN', 'CRt', 1.0), ('GPS[0]', 'VZ', -1.0), ('GPS', 'VZ', -1.0)]
_XKF4 = ['XKF4[0]', 'XKF4', 'NKF4[0]', 'NKF4']
_XKF3 = ['XKF3[0]', 'XKF3', 'NKF3[0]', 'NKF3']


def _first_present(data: dict, candidates) -> Optional[str]:
    for k in candidates:
        df = data.get(k)
        if df is not None and not getattr(df, 'empty', True):
            return k
    return None


def _state(value: Optional[float], warn: float, crit: float) -> str:
    if value is None:
        return _OK
    if value >= crit:
        return _CRITICAL
    if value >= warn:
        return _CAUTION
    return _OK


def vertical_speed_at(svc, data: dict, t: float) -> dict:
    """Climb rate (m/s, +up) at t using BARO.CRt → CTUN.CRt → -GPS.VZ →
    POS.RelHomeAlt derivative. {'value', 'source'} (value None if unavailable)."""
    for msg, col, sign in _VSPEED_SOURCES:
        if msg in data:
            v = svc.value_at(msg, col, t)
            if v is not None:
                return {'value': sign * v, 'source': f'{msg}.{col}'}
    # finite-difference fallback on relative altitude
    pos = data.get('POS')
    if pos is not None and {'TimeS', 'RelHomeAlt'}.issubset(getattr(pos, 'columns', [])):
        dt = 0.5
        a0 = svc.value_at('POS', 'RelHomeAlt', t - dt)
        a1 = svc.value_at('POS', 'RelHomeAlt', t + dt)
        if a0 is not None and a1 is not None:
            return {'value': (a1 - a0) / (2 * dt), 'source': 'POS.RelHomeAlt d/dt'}
    return {'value': None, 'source': 'none'}


def ekf_status_at(svc, data: dict, t: float) -> dict:
    """EKF health from XKF4 normalised test ratios (SV/SP/SH/SM; 1.0 = measurement
    rejected) plus the fault bitmask FS. {'ratio', 'worst', 'faults', 'state',
    'source'}."""
    key = _first_present(data, _XKF4)
    if key is None:
        return {'ratio': None, 'worst': None, 'faults': None,
                'state': _OK, 'source': 'none'}
    ratios = {}
    for col in ('SV', 'SP', 'SH', 'SM'):
        v = svc.value_at(key, col, t)
        if v is not None:
            ratios[col] = v
    faults = svc.value_at(key, 'FS', t)
    if not ratios:
        return {'ratio': None, 'worst': None, 'faults': faults,
                'state': _OK, 'source': key}
    worst_col = max(ratios, key=ratios.get)
    ratio = ratios[worst_col]
    state = _state(ratio, _EKF_WARN, _EKF_CRIT)
    if faults is not None and int(faults) != 0:
        state = _CRITICAL
    return {'ratio': ratio, 'worst': worst_col, 'faults': int(faults) if faults is not None else None,
            'state': state, 'source': key}


def position_divergence_at(svc, data: dict, t: float) -> dict:
    """Horizontal EKF position innovation magnitude (m) from XKF3 IPN/IPE — how far
    the filter's position estimate sits from its measurements. {'value', 'vertical',
    'state', 'source'}."""
    key = _first_present(data, _XKF3)
    if key is None:
        return {'value': None, 'vertical': None, 'state': _OK, 'source': 'none'}
    ipn = svc.value_at(key, 'IPN', t)
    ipe = svc.value_at(key, 'IPE', t)
    ipd = svc.value_at(key, 'IPD', t)
    if ipn is None or ipe is None:
        return {'value': None, 'vertical': ipd, 'state': _OK, 'source': key}
    horiz = math.hypot(ipn, ipe)
    return {'value': horiz, 'vertical': ipd,
            'state': _state(horiz, _POSDIV_WARN, _POSDIV_CRIT), 'source': key}
