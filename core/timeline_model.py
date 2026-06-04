"""
TimelineModel — derives the temporal structure of a flight for the shared-cursor
investigation surfaces (Timeline view, Replay, Event Investigation, Verification
highlighting).

Pure core: no Qt. All outputs are plain dataclasses suitable for any consumer.

Derives:
  - arm/disarm regions   (from ARM, fallback EV armed/disarmed)
  - mode segments        (from MODE)
  - altitude profile      (AGL hierarchy: RelHomeAlt -> BARO -> SIM2 -> POS.Alt)
  - flight phases        (PRE_ARM / TAKEOFF / CLIMB / HOVER / DESCENT / RTL / LAND /
                          POST), altitude-rate driven with mode overrides
  - event regions        (from EventExtractor — single authoritative source)

Defensive by design: missing ARM, sparse MODE, truncated logs, and missing altitude
all degrade to a sensible partial timeline rather than raising.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import numpy as np

from core.event_extractor import EventExtractor, MODE_NAMES


# ── Data structures ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Segment:
    t_start: float
    t_end: float

    @property
    def duration(self) -> float:
        return self.t_end - self.t_start

    def contains(self, t: float) -> bool:
        return self.t_start <= t <= self.t_end


@dataclass(frozen=True)
class Phase(Segment):
    kind: str = 'FLIGHT'   # PRE_ARM/TAKEOFF/CLIMB/HOVER/DESCENT/RTL/LAND/POST/FLIGHT


@dataclass(frozen=True)
class ModeSegment(Segment):
    mode: str = '?'
    mode_num: int = -1


@dataclass(frozen=True)
class ArmRegion(Segment):
    source: str = 'ARM'    # 'ARM' or 'EV'


@dataclass(frozen=True)
class AltitudeProfile:
    times: np.ndarray            # seconds
    agl: np.ndarray              # metres above home/ground
    source: str                  # which field supplied it

    @property
    def empty(self) -> bool:
        return self.times.size == 0


@dataclass(frozen=True)
class Timeline:
    t_start: float
    t_end: float
    arm_regions: list            # [ArmRegion]
    modes: list                  # [ModeSegment]
    phases: list                 # [Phase]
    altitude: AltitudeProfile
    events: list                 # [(t, severity, type, message)]


# ── Phase classification thresholds (documented, conservative) ───────────────
_GROUND_AGL_M = 1.0       # below this is "on/near ground"
_VRATE_THRESH = 0.3       # m/s, climb/descent vs hold
_RESAMPLE_DT = 0.5        # s, altitude resample step for rate estimation
_SMOOTH_WIN = 3           # samples, moving-average smoothing of vertical rate
_RTL_MODES = {'RTL', 'SMART_RTL', 'AUTO_RTL'}
_LAND_MODES = {'LAND'}
_MIN_PHASE_S = 0.05       # drop float-precision slivers; merge into neighbour


class TimelineModel:
    def __init__(self, data: dict):
        self._data = data or {}
        self._t_start, self._t_end = self._log_span()

    # ── public API ────────────────────────────────────────────────────────────

    def log_span(self) -> tuple[float, float]:
        return self._t_start, self._t_end

    def arm_regions(self) -> list:
        """Armed windows. From ARM state transitions; falls back to EV armed/disarmed.
        For a truncated log (armed but never disarmed) the region extends to log end."""
        arm = self._data.get('ARM')
        regions = []
        if arm is not None and not arm.empty and {'TimeS'}.issubset(arm.columns):
            state_col = next((c for c in ('ArmState', 'Armed', 'State')
                              if c in arm.columns), None)
            ts = arm['TimeS'].to_numpy(dtype=float)
            if state_col is not None:
                states = arm[state_col].to_numpy()
                start = None
                for t, s in zip(ts, states):
                    armed = int(s) == 1
                    if armed and start is None:
                        start = float(t)
                    elif not armed and start is not None:
                        regions.append(ArmRegion(start, float(t), 'ARM'))
                        start = None
                if start is not None:           # truncated: never disarmed
                    regions.append(ArmRegion(start, self._t_end, 'ARM'))
            else:
                # ARM rows without a clear state column: pair sequentially
                for i in range(0, len(ts) - 1, 2):
                    regions.append(ArmRegion(float(ts[i]), float(ts[i + 1]), 'ARM'))
                if len(ts) % 2 == 1:
                    regions.append(ArmRegion(float(ts[-1]), self._t_end, 'ARM'))
            if regions:
                return regions

        # Fallback: EV armed(10/15) / disarmed(11)
        ev = self._data.get('EV')
        if ev is not None and not ev.empty and {'TimeS', 'Id'}.issubset(ev.columns):
            start = None
            for _, r in ev.sort_values('TimeS').iterrows():
                eid = int(r['Id'])
                t = float(r['TimeS'])
                if eid in (10, 15) and start is None:
                    start = t
                elif eid == 11 and start is not None:
                    regions.append(ArmRegion(start, t, 'EV'))
                    start = None
            if start is not None:
                regions.append(ArmRegion(start, self._t_end, 'EV'))
        return regions

    def mode_segments(self) -> list:
        """Contiguous flight-mode regions from MODE changes."""
        mode = self._data.get('MODE')
        if mode is None or mode.empty or 'TimeS' not in mode.columns:
            return []
        mcol = next((c for c in ('Mode', 'ModeNum') if c in mode.columns), None)
        if mcol is None:
            return []
        m = mode.sort_values('TimeS')
        ts = m['TimeS'].to_numpy(dtype=float)
        nums = m[mcol].to_numpy()
        segs = []
        for i in range(len(ts)):
            num = int(nums[i])
            start = float(ts[i])
            end = float(ts[i + 1]) if i + 1 < len(ts) else self._t_end
            name = MODE_NAMES.get(num, f'MODE_{num}')
            # merge consecutive identical modes
            if segs and segs[-1].mode_num == num:
                prev = segs[-1]
                segs[-1] = ModeSegment(prev.t_start, end, prev.mode, num)
            else:
                segs.append(ModeSegment(start, end, name, num))
        return segs

    def altitude_profile(self, max_points: int = 2000) -> AltitudeProfile:
        """AGL profile from the source hierarchy, decimated to <= max_points."""
        t, agl, src = self._agl_series()
        if t.size == 0:
            return AltitudeProfile(np.array([]), np.array([]), 'none')
        if t.size > max_points:
            idx = np.linspace(0, t.size - 1, max_points).astype(int)
            t, agl = t[idx], agl[idx]
        return AltitudeProfile(t, agl, src)

    def phases(self) -> list:
        """
        Flight phases. PRE_ARM before first arm, POST after last disarm, and within
        each armed window a vertical-rate state machine yields TAKEOFF/CLIMB/HOVER/
        DESCENT/LAND, with RTL/LAND mode segments overriding the label.
        """
        regions = self.arm_regions()
        modes = self.mode_segments()
        phases: list = []

        if not regions:
            # No arm info: one generic FLIGHT phase over the whole log.
            if self._t_end > self._t_start:
                phases.append(Phase(self._t_start, self._t_end, 'FLIGHT'))
            return phases

        first_arm = regions[0].t_start
        last_disarm = regions[-1].t_end
        if first_arm > self._t_start:
            phases.append(Phase(self._t_start, first_arm, 'PRE_ARM'))

        for reg in regions:
            phases.extend(self._phases_within(reg, modes))

        if last_disarm < self._t_end:
            phases.append(Phase(last_disarm, self._t_end, 'POST'))
        return self._dedupe(phases)

    @staticmethod
    def _dedupe(phases: list) -> list:
        """Drop near-zero slivers and merge adjacent same-kind phases so the band
        is clean and contiguous."""
        out: list = []
        for p in phases:
            if p.duration < _MIN_PHASE_S and out:
                # extend previous phase over the sliver (keep contiguity)
                prev = out[-1]
                out[-1] = Phase(prev.t_start, p.t_end, prev.kind)
                continue
            if out and out[-1].kind == p.kind:
                prev = out[-1]
                out[-1] = Phase(prev.t_start, p.t_end, prev.kind)
            else:
                out.append(p)
        return out

    def event_regions(self) -> list:
        """Events as point markers (single authoritative source)."""
        return EventExtractor.collect(self._data)

    def build(self) -> Timeline:
        return Timeline(
            t_start=self._t_start, t_end=self._t_end,
            arm_regions=self.arm_regions(),
            modes=self.mode_segments(),
            phases=self.phases(),
            altitude=self.altitude_profile(),
            events=self.event_regions(),
        )

    # ── consumer helpers (snapshot / verification highlighting) ────────────────

    def phase_at(self, t: float) -> Optional[Phase]:
        for p in self.phases():
            if p.contains(t):
                return p
        return None

    def mode_at(self, t: float) -> Optional[str]:
        for s in self.mode_segments():
            if s.contains(t):
                return s.mode
        return None

    # ── internals ──────────────────────────────────────────────────────────────

    def _log_span(self) -> tuple[float, float]:
        t_min, t_max = None, None
        for df in self._data.values():
            if 'TimeS' not in getattr(df, 'columns', []):
                continue
            ts = df['TimeS'].dropna()
            if ts.empty:
                continue
            mn, mx = float(ts.min()), float(ts.max())
            t_min = mn if t_min is None else min(t_min, mn)
            t_max = mx if t_max is None else max(t_max, mx)
        if t_min is None:
            return 0.0, 0.0
        return t_min, t_max

    def _agl_series(self) -> tuple[np.ndarray, np.ndarray, str]:
        """(times, agl, source) using the documented hierarchy."""
        d = self._data
        pos = d.get('POS')
        if pos is not None and not pos.empty and 'RelHomeAlt' in pos.columns \
                and 'TimeS' in pos.columns:
            return (pos['TimeS'].to_numpy(float),
                    pos['RelHomeAlt'].to_numpy(float), 'POS.RelHomeAlt')
        for b in ('BARO[0]', 'BARO', 'BARO[1]'):
            df = d.get(b)
            if df is not None and not df.empty and {'TimeS', 'Alt'}.issubset(df.columns):
                return df['TimeS'].to_numpy(float), df['Alt'].to_numpy(float), f'{b}.Alt'
        sim2 = d.get('SIM2')
        if sim2 is not None and not sim2.empty and {'TimeS', 'PD'}.issubset(sim2.columns):
            return sim2['TimeS'].to_numpy(float), -sim2['PD'].to_numpy(float), 'SIM2.-PD'
        if pos is not None and not pos.empty and {'TimeS', 'Alt'}.issubset(pos.columns):
            return pos['TimeS'].to_numpy(float), pos['Alt'].to_numpy(float), 'POS.Alt'
        return np.array([]), np.array([]), 'none'

    def _mode_label_at(self, modes: list, t: float) -> Optional[str]:
        for s in modes:
            if s.contains(t):
                return s.mode
        return None

    def _phases_within(self, reg: ArmRegion, modes: list) -> list:
        """Vertical-rate phase classification inside one armed window, with RTL/LAND
        mode override. Falls back to a single FLIGHT phase if altitude is unavailable."""
        a, d = reg.t_start, reg.t_end
        t_raw, agl_raw, _ = self._agl_series()
        if t_raw.size < 2 or d <= a:
            return [Phase(a, d, 'FLIGHT')]

        # resample AGL uniformly within the window
        n = max(2, int((d - a) / _RESAMPLE_DT) + 1)
        ts = np.linspace(a, d, n)
        # ensure source is sorted for interp
        order = np.argsort(t_raw)
        agl = np.interp(ts, t_raw[order], agl_raw[order])

        # vertical rate, smoothed
        vrate = np.gradient(agl, ts)
        if vrate.size >= _SMOOTH_WIN:
            kernel = np.ones(_SMOOTH_WIN) / _SMOOTH_WIN
            vrate = np.convolve(vrate, kernel, mode='same')

        # per-sample state
        def state(i):
            if vrate[i] > _VRATE_THRESH:
                return 'CLIMB'
            if vrate[i] < -_VRATE_THRESH:
                return 'DESCENT'
            return 'HOVER'

        # merge into raw segments
        segs = []
        cur = state(0)
        seg_start = ts[0]
        for i in range(1, n):
            s = state(i)
            if s != cur:
                segs.append([cur, seg_start, ts[i]])
                cur = s
                seg_start = ts[i]
        segs.append([cur, seg_start, ts[-1]])

        # boundary relabel: first climb from ground -> TAKEOFF; last descent to ground -> LAND
        if segs and segs[0][0] == 'CLIMB' and agl[0] < _GROUND_AGL_M:
            segs[0][0] = 'TAKEOFF'
        if segs and segs[-1][0] == 'DESCENT' and agl[-1] < _GROUND_AGL_M * 3:
            segs[-1][0] = 'LAND'

        # mode override (RTL/LAND) by majority mode within each segment
        phases = []
        for kind, s0, s1 in segs:
            mid = 0.5 * (s0 + s1)
            mlabel = self._mode_label_at(modes, mid)
            if mlabel in _RTL_MODES:
                kind = 'RTL'
            elif mlabel in _LAND_MODES and kind in ('DESCENT', 'HOVER'):
                kind = 'LAND'
            # merge consecutive same-kind
            if phases and phases[-1].kind == kind:
                prev = phases[-1]
                phases[-1] = Phase(prev.t_start, s1, kind)
            else:
                phases.append(Phase(s0, s1, kind))
        return phases
