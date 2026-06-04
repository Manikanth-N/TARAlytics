"""
RCModel — turns raw RC PWM channels into semantic pilot intent.

The investigation surfaces must speak in Roll/Pitch/Yaw/Throttle, not C1/C2/C3/C4.
RCModel reads the vehicle's own parameters (RCMAP_* + RC{n}_MIN/MAX/TRIM/REVERSED/DZ)
so the mapping and normalization match what the autopilot actually used, then
produces normalized intent:

  roll / pitch / yaw  -> -1.0 .. +1.0   (0 at trim, sign = stick direction)
  throttle            ->  0.0 .. +1.0

Outputs feed: RC stick visualization, pilot-vs-controller analysis, investigation
snapshots, and the values-at-cursor table. Pure core, no Qt.

Defensive: missing or malformed parameters fall back to documented defaults
(map 1/2/3/4, MIN 1000 / TRIM 1500 / MAX 2000, not reversed, no deadzone).
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


AXES = ('roll', 'pitch', 'yaw', 'throttle')
_DEFAULT_MAP = {'roll': 1, 'pitch': 2, 'throttle': 3, 'yaw': 4}
_DEF_MIN, _DEF_TRIM, _DEF_MAX = 1000.0, 1500.0, 2000.0


@dataclass(frozen=True)
class ChannelCfg:
    ch: int
    pmin: float
    pmax: float
    ptrim: float
    dz: float
    reversed: bool


@dataclass(frozen=True)
class StickState:
    """Semantic pilot intent (or servo output) at a moment.
    roll/pitch/yaw in -1..+1, throttle in 0..1; None when unavailable."""
    roll: Optional[float] = None
    pitch: Optional[float] = None
    yaw: Optional[float] = None
    throttle: Optional[float] = None

    def as_dict(self) -> dict:
        return {'roll': self.roll, 'pitch': self.pitch,
                'yaw': self.yaw, 'throttle': self.throttle}


def params_from_data(data: dict) -> dict:
    """Extract a {param_name: float} dict from the PARM message."""
    out: dict = {}
    parm = (data or {}).get('PARM')
    if parm is None or parm.empty:
        return out
    name_col = next((c for c in ('Name', 'name') if c in parm.columns), None)
    val_col = next((c for c in ('Value', 'value') if c in parm.columns), None)
    if name_col is None or val_col is None:
        return out
    for n, v in zip(parm[name_col], parm[val_col]):
        try:
            out[str(n)] = float(v)
        except (TypeError, ValueError):
            continue
    return out


class RCModel:
    def __init__(self, params: Optional[dict] = None):
        self._p = params or {}
        self._map = self._build_map()
        self._cfg: dict[str, ChannelCfg] = {}

    @classmethod
    def from_data(cls, data: dict) -> 'RCModel':
        return cls(params_from_data(data))

    # ── mapping / config ────────────────────────────────────────────────────

    def _num(self, name: str) -> Optional[float]:
        v = self._p.get(name)
        if v is None:
            return None
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return f if f == f else None   # reject NaN

    def _build_map(self) -> dict:
        m = dict(_DEFAULT_MAP)
        for axis in AXES:
            v = self._num(f'RCMAP_{axis.upper()}')
            if v is not None and 1 <= int(v) <= 16:
                m[axis] = int(v)
        return m

    def channel_for(self, axis: str) -> int:
        return self._map[axis]

    def config_for(self, axis: str) -> ChannelCfg:
        if axis in self._cfg:
            return self._cfg[axis]
        ch = self._map[axis]
        pmin = self._num(f'RC{ch}_MIN')
        pmax = self._num(f'RC{ch}_MAX')
        ptrim = self._num(f'RC{ch}_TRIM')
        dz = self._num(f'RC{ch}_DZ')
        # REVERSED (0/1, new) preferred; fall back to REV (-1/+1, legacy)
        rev_new = self._num(f'RC{ch}_REVERSED')
        rev_old = self._num(f'RC{ch}_REV')
        if rev_new is not None:
            is_rev = int(rev_new) == 1
        elif rev_old is not None:
            is_rev = rev_old < 0
        else:
            is_rev = False
        # defensive defaults + sanity (malformed -> defaults)
        if pmin is None:
            pmin = _DEF_MIN
        if pmax is None:
            pmax = _DEF_MAX
        if ptrim is None:
            ptrim = _DEF_TRIM
        if pmin >= pmax:
            pmin, pmax = _DEF_MIN, _DEF_MAX
        if not (pmin <= ptrim <= pmax):
            ptrim = (pmin + pmax) / 2.0
        if dz is None or dz < 0:
            dz = 0.0
        cfg = ChannelCfg(ch, pmin, pmax, ptrim, dz, is_rev)
        self._cfg[axis] = cfg
        return cfg

    # ── normalization ──────────────────────────────────────────────────────

    def normalize(self, axis: str, pwm: Optional[float]) -> Optional[float]:
        """PWM -> semantic intent. roll/pitch/yaw in -1..1, throttle in 0..1."""
        if pwm is None:
            return None
        c = self.config_for(axis)
        if axis == 'throttle':
            span = c.pmax - c.pmin
            n = 0.0 if span <= 0 else (pwm - c.pmin) / span
            n = min(1.0, max(0.0, n))
            return 1.0 - n if c.reversed else n
        # centered axes
        d = pwm - c.ptrim
        ad = abs(d)
        if ad <= c.dz:
            return 0.0
        half = (c.pmax - c.ptrim) if d > 0 else (c.ptrim - c.pmin)
        eff = half - c.dz
        n = 1.0 if eff <= 0 else min(1.0, (ad - c.dz) / eff)
        n = n if d > 0 else -n
        return -n if c.reversed else n

    # ── time-resolved intent (via SampleService) ───────────────────────────

    def _state_from(self, svc, t: float, msg: str) -> StickState:
        def axis_val(axis):
            ch = self._map[axis]
            return self.normalize(axis, svc.value_at(msg, f'C{ch}', t))
        return StickState(roll=axis_val('roll'), pitch=axis_val('pitch'),
                          yaw=axis_val('yaw'), throttle=axis_val('throttle'))

    def pilot_input(self, svc, t: float) -> StickState:
        """Pilot stick intent from RCIN at time t."""
        return self._state_from(svc, t, 'RCIN')

    def servo_output(self, svc, t: float) -> StickState:
        """Servo/motor output from RCOU at time t (same map + normalization),
        for pilot-vs-output comparison."""
        return self._state_from(svc, t, 'RCOU')
