"""
Health analysis from parsed flight-log data.

Logic moved from ui/widgets/health_cards.py update_* methods into pure
functions that return plain dicts, so any module can consume them without
touching widgets.
"""
from __future__ import annotations


GPS_FIX_NAMES = {
    0: 'NO_GPS', 1: 'NO_FIX', 2: '2D_FIX', 3: '3D_FIX',
    4: 'DGPS', 5: 'RTK_FLOAT', 6: 'RTK_FIXED',
}


def get_df_any_instance(data: dict, base_name: str):
    """Return the first available DataFrame for base_name (direct or [0]..[3])."""
    df = data.get(base_name)
    if df is not None:
        return df
    for i in range(4):
        df = data.get(f'{base_name}[{i}]')
        if df is not None:
            return df
    return None


def get_df_all_instances(data: dict, base_name: str) -> list:
    """Return all instance DataFrames for base_name (direct + [0]..[15])."""
    dfs = []
    direct = data.get(base_name)
    if direct is not None:
        dfs.append(direct)
    for i in range(16):
        df = data.get(f'{base_name}[{i}]')
        if df is not None:
            dfs.append(df)
    return dfs


class HealthAnalyzer:
    """Pure analysis functions returning dicts of health state."""

    @staticmethod
    def firmware(data: dict) -> dict:
        """Returns {'text': str, 'build': str}."""
        fw_str = ''
        msg_df = data.get('MSG')
        if msg_df is not None and not msg_df.empty:
            for col in msg_df.columns:
                if col in ('Message', 'Msg'):
                    for val in msg_df[col]:
                        s = str(val)
                        if 'ArduCopter' in s or 'ArduPlane' in s or 'ArduRover' in s:
                            fw_str = s
                            break
        if not fw_str:
            ver_df = data.get('VER')
            if ver_df is not None and not ver_df.empty and 'FWS' in ver_df.columns:
                fw_str = str(ver_df['FWS'].iloc[0]).strip()
        build = ''
        if fw_str and '(' in fw_str and ')' in fw_str:
            build = fw_str[fw_str.find('(') + 1: fw_str.find(')')]
            fw_str = fw_str[:fw_str.find('(')].strip()
        return {'text': fw_str or 'UNKNOWN', 'build': build}

    @staticmethod
    def vehicle(data: dict) -> dict:
        """Returns {'frame': str}."""
        frame_str = ''
        msg_df = data.get('MSG')
        if msg_df is not None and not msg_df.empty:
            for col in msg_df.columns:
                if col in ('Message', 'Msg'):
                    for val in msg_df[col]:
                        s = str(val)
                        if 'Frame:' in s:
                            frame_str = s.replace('Frame:', '').strip()
                            break
        if not frame_str:
            ver_df = data.get('VER')
            if ver_df is not None and not ver_df.empty and 'FWS' in ver_df.columns:
                fws = str(ver_df['FWS'].iloc[0])
                for vehicle in ('ArduCopter', 'ArduPlane', 'ArduRover',
                                'ArduSub', 'ArduBlimp'):
                    if vehicle in fws:
                        frame_str = vehicle
                        break
        return {'frame': frame_str or 'UNKNOWN'}

    @staticmethod
    def ekf(data: dict) -> dict:
        """Returns {'status': 'OK'|'WARN'|'NO DATA', 'detail': str}."""
        fs_values = []
        for df in get_df_all_instances(data, 'XKF4'):
            for col in ('FS', 'fs'):
                if col in df.columns:
                    fs_values.extend(df[col].dropna().astype(int).tolist())
                    break
        if not fs_values:
            return {'status': 'NO DATA', 'detail': ''}
        if any(v > 0 for v in fs_values):
            return {'status': 'WARN',
                    'detail': f'Filter status > 0 (max={max(fs_values)})'}
        return {'status': 'OK', 'detail': 'All FS = 0'}

    @staticmethod
    def gps(data: dict) -> dict:
        """
        Returns {'fix': str, 'sats': int, 'hdop': float, 'is_sitl': bool,
                 'status': 'OK'|'WARN'|'NO DATA'}.
        """
        gps_df = get_df_any_instance(data, 'GPS')
        if gps_df is None or gps_df.empty:
            is_sitl = data.get('SIM2') is not None or data.get('SIM') is not None
            return {'fix': 'SITL' if is_sitl else 'NO DATA',
                    'sats': 0, 'hdop': 0.0, 'is_sitl': is_sitl,
                    'status': 'OK' if is_sitl else 'NO DATA'}
        status, sats, hdop = 0, 0, 0.0
        for col in ('Status', 'status', 'GStatus'):
            if col in gps_df.columns:
                status = int(gps_df[col].iloc[-1]); break
        for col in ('NSats', 'NSat', 'Sats'):
            if col in gps_df.columns:
                sats = int(gps_df[col].iloc[-1]); break
        for col in ('HDop', 'Hdop', 'hdop'):
            if col in gps_df.columns:
                hdop = float(gps_df[col].iloc[-1]); break
        return {
            'fix': GPS_FIX_NAMES.get(status, f'FIX_{status}'),
            'sats': sats, 'hdop': hdop, 'is_sitl': False,
            'status': 'OK' if status >= 3 else 'WARN',
        }
