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
    def duration(data: dict) -> tuple[float, str]:
        """Returns (seconds, 'M:SS'). (0.0, '—') if no time data."""
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
        dur = t_max - t_min
        m, s = int(dur // 60), int(dur % 60)
        return dur, f'{m}:{s:02d}'

    @staticmethod
    def max_altitude(data: dict) -> tuple[float, str]:
        """Returns (metres, 'X.X m'). (0.0, '—') if unavailable."""
        alt_max = None
        for key in ('GPS', 'GPS[0]', 'POS'):
            df = data.get(key)
            if df is not None and not df.empty:
                alt_col = next((c for c in ('Alt', 'alt') if c in df.columns), None)
                if alt_col:
                    alt_max = float(df[alt_col].dropna().max())
                    break
        if alt_max is None:
            sim2 = data.get('SIM2')
            if sim2 is not None and not sim2.empty and 'PD' in sim2.columns:
                alt_max = float(-sim2['PD'].min())
        if alt_max is None:
            return 0.0, '—'
        return alt_max, f'{alt_max:.1f} m'

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
