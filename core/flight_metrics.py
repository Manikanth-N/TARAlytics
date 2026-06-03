"""
Flight metric extraction from parsed log data.

Logic moved from ui/widgets/flight_summary.py _update_* methods into pure
functions returning (value, formatted_string) tuples.
"""
from __future__ import annotations
import numpy as np

from core.gps_converter import best_trajectory
from core.event_extractor import EventExtractor


class FlightMetrics:
    """Pure metric functions over parsed log data."""

    @staticmethod
    def _fmt_mmss(seconds: float) -> str:
        m, s = int(seconds // 60), int(seconds % 60)
        return f'{m}:{s:02d}'

    @staticmethod
    def log_span(data: dict) -> tuple[float, str]:
        """Full log time span (first→last TimeS across all messages)."""
        t_min, t_max = None, None
        for df in data.values():
            if 'TimeS' not in df.columns:
                continue
            ts = df['TimeS'].dropna()
            if ts.empty:
                continue
            mn, mx = float(ts.min()), float(ts.max())
            t_min = mn if t_min is None else min(t_min, mn)
            t_max = mx if t_max is None else max(t_max, mx)
        if t_min is None:
            return 0.0, '—'
        span = t_max - t_min
        return span, FlightMetrics._fmt_mmss(span)

    @staticmethod
    def duration(data: dict) -> tuple[float, str]:
        """
        Flight duration = the ARMED window (first ARM -> last ARM/disarm), which
        is what a flight-test engineer means by 'flight time'. The full log span
        (which includes pre-arm init and post-disarm logging) is available via
        log_span(). Falls back to EV armed/disarmed events, then to log span.
        """
        arm = data.get('ARM')
        if arm is not None and not arm.empty and 'TimeS' in arm.columns:
            ts = arm['TimeS'].dropna()
            if len(ts) >= 2:
                dur = float(ts.max() - ts.min())
                return dur, FlightMetrics._fmt_mmss(dur)
        # Fallback: EV armed (10/15) -> disarmed (11)
        ev = data.get('EV')
        if ev is not None and not ev.empty and {'TimeS', 'Id'}.issubset(ev.columns):
            armed = ev[ev['Id'].isin([10, 15])]['TimeS']
            disarmed = ev[ev['Id'] == 11]['TimeS']
            if len(armed) and len(disarmed):
                dur = float(disarmed.max() - armed.min())
                if dur > 0:
                    return dur, FlightMetrics._fmt_mmss(dur)
        # Last resort: full log span (clearly not flight time, but better than 0)
        return FlightMetrics.log_span(data)

    # Altitude source hierarchy, most→least authoritative for "max height".
    # Engineers mean height above takeoff (AGL), not AMSL. Evidence (log 02):
    # RelHomeAlt 10.01 m ≈ BARO 9.99 m ≈ SIM2 10.07 m (three sources agree);
    # POS.Alt 594 m is AMSL; GPS.Alt is garbage in SITL. So prefer AGL sources.
    _PLAUSIBLE_ALT_M = 60000.0   # flag anything above this as suspect

    @staticmethod
    def max_altitude(data: dict) -> tuple[float, str]:
        """
        Returns (metres_AGL, 'X.X m'). Prefers relative-to-home altitude.
        Hierarchy: POS.RelHomeAlt -> BARO.Alt -> SIM2(-PD) -> POS.Alt(AMSL).
        GPS.Alt is intentionally excluded (unreliable / SITL garbage).
        A value above _PLAUSIBLE_ALT_M is flagged, never silently clamped.
        """
        candidates = []  # (label, value)

        pos = data.get('POS')
        if pos is not None and not pos.empty and 'RelHomeAlt' in pos.columns:
            v = pos['RelHomeAlt'].dropna()
            if len(v):
                candidates.append(('AGL', float(v.max())))

        if not candidates:
            for b in ('BARO[0]', 'BARO', 'BARO[1]'):
                df = data.get(b)
                if df is not None and not df.empty and 'Alt' in df.columns:
                    v = df['Alt'].dropna()
                    if len(v):
                        candidates.append(('BARO', float(v.max())))
                        break

        if not candidates:
            sim2 = data.get('SIM2')
            if sim2 is not None and not sim2.empty and 'PD' in sim2.columns:
                candidates.append(('SIM2', float(-sim2['PD'].min())))

        if not candidates:
            if pos is not None and not pos.empty and 'Alt' in pos.columns:
                v = pos['Alt'].dropna()
                if len(v):
                    candidates.append(('AMSL', float(v.max())))

        if not candidates:
            return 0.0, '—'

        _, alt = candidates[0]
        if abs(alt) > FlightMetrics._PLAUSIBLE_ALT_M:
            return alt, f'⚠ {alt:.0f} m (suspect)'
        return alt, f'{alt:.1f} m'

    @staticmethod
    def max_speed(data: dict) -> tuple[float, str]:
        """Returns (m/s, 'X.X m/s'). (0.0, '—') if unavailable."""
        spd_max = None
        sim2 = data.get('SIM2')
        if sim2 is not None and not sim2.empty and {'VN', 'VE', 'VD'}.issubset(sim2.columns):
            spd = np.sqrt(sim2['VN'] ** 2 + sim2['VE'] ** 2 + sim2['VD'] ** 2)
            spd_max = float(spd.max())
        if spd_max is None:
            for key in ('GPS', 'GPS[0]'):
                df = data.get(key)
                if df is not None and not df.empty:
                    for col in ('Spd', 'GndSpd', 'Spd3D'):
                        if col in df.columns:
                            spd_max = float(df[col].max()); break
                    if spd_max is not None:
                        break
        if spd_max is None:
            return 0.0, '—'
        return spd_max, f'{spd_max:.1f} m/s'

    @staticmethod
    def distance(data: dict) -> tuple[float, str]:
        """Returns (metres, 'X m' or 'X.XX km'). (0.0, '—') if unavailable."""
        traj = best_trajectory(data)
        if traj is not None and len(traj['east']) > 1:
            east, north = traj['east'], traj['north']
            dist = float(np.sqrt(np.diff(east) ** 2 + np.diff(north) ** 2).sum())
            text = f'{dist / 1000:.2f} km' if dist >= 1000 else f'{dist:.0f} m'
            return dist, text
        return 0.0, '—'

    @staticmethod
    def arm_count(data: dict) -> int:
        arm_df = data.get('ARM')
        return len(arm_df) if arm_df is not None and not arm_df.empty else 0

    @staticmethod
    def event_count(data: dict) -> int:
        return len(EventExtractor.collect(data))

    @staticmethod
    def mode_change_count(data: dict) -> int:
        return sum(1 for e in EventExtractor.collect(data) if e[2] == 'MODE')
