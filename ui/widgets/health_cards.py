import pandas as pd
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame, QSizePolicy
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from core.colors import badge_style


GPS_FIX_NAMES = {
    0: 'NO_GPS', 1: 'NO_FIX', 2: '2D_FIX', 3: '3D_FIX',
    4: 'DGPS', 5: 'RTK_FLOAT', 6: 'RTK_FIXED',
}


def get_df_any_instance(data: dict, base_name: str):
    """Return the first available DataFrame for base_name (direct or instanced [0]…[3])."""
    df = data.get(base_name)
    if df is not None:
        return df
    for i in range(4):
        df = data.get(f'{base_name}[{i}]')
        if df is not None:
            return df
    return None


def get_df_all_instances(data: dict, base_name: str) -> list:
    """Return all instance DataFrames for base_name (direct + [0]…[15])."""
    dfs = []
    direct = data.get(base_name)
    if direct is not None:
        dfs.append(direct)
    for i in range(16):
        df = data.get(f'{base_name}[{i}]')
        if df is not None:
            dfs.append(df)
    return dfs


class HealthCard(QFrame):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            'QFrame { background: #1e1e2e; border: 1px solid #3a3a5e; '
            'border-radius: 8px; }'
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(90)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet('color: #8888aa; font-size: 11px; font-weight: bold; border: none;')
        layout.addWidget(title_lbl)

        self._badge = QLabel('—')
        self._badge.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._badge.setStyleSheet(
            'color: #8888aa; background: #2a2a3a; border-radius: 4px; '
            'padding: 2px 8px; font-weight: bold; font-size: 13px; border: none;'
        )
        self._badge.setFixedHeight(26)
        layout.addWidget(self._badge)

        self._sub = QLabel('')
        self._sub.setStyleSheet('color: #9898b8; font-size: 11px; border: none;')
        self._sub.setWordWrap(True)
        layout.addWidget(self._sub)

    def set_state(self, state: str, sub: str = ''):
        fg, bg = badge_style(state)
        self._badge.setText(state)
        self._badge.setStyleSheet(
            f'color: {fg}; background: {bg}; border-radius: 4px; '
            f'padding: 2px 8px; font-weight: bold; font-size: 13px; border: none;'
        )
        self._sub.setText(sub)

    def set_text(self, main: str, sub: str = '', color: str = '#d0d0e8', bg: str = '#2a2a3a'):
        self._badge.setText(main)
        self._badge.setStyleSheet(
            f'color: {color}; background: {bg}; border-radius: 4px; '
            f'padding: 2px 8px; font-weight: bold; font-size: 13px; border: none;'
        )
        self._sub.setText(sub)


class HealthCardsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._sig_card = HealthCard('SIGNATURE')
        self._fw_card = HealthCard('FIRMWARE')
        self._veh_card = HealthCard('VEHICLE')
        self._ekf_card = HealthCard('EKF')
        self._gps_card = HealthCard('GPS')

        for card in (self._sig_card, self._fw_card, self._veh_card,
                     self._ekf_card, self._gps_card):
            layout.addWidget(card)

    def update_signature(self, state: str, key_id: str = ''):
        self._sig_card.set_state(state, f'Key ID: {key_id}' if key_id else '')

    def update_firmware(self, data: dict):
        msg_df = data.get('MSG')
        if msg_df is None or msg_df.empty:
            self._fw_card.set_text('NO DATA', '')
            return
        fw_str = ''
        for col in msg_df.columns:
            if col in ('Message', 'Msg'):
                for val in msg_df[col]:
                    s = str(val)
                    if 'ArduCopter' in s or 'ArduPlane' in s or 'ArduRover' in s:
                        fw_str = s
                        break
        if fw_str:
            build = ''
            if '(' in fw_str and ')' in fw_str:
                build = fw_str[fw_str.find('(') + 1: fw_str.find(')')]
                fw_str = fw_str[:fw_str.find('(')].strip()
            self._fw_card.set_text(fw_str, f'Build: {build}' if build else '', '#6ee7b7', '#1a3a2a')
        else:
            self._fw_card.set_text('UNKNOWN', '')

    def update_vehicle(self, data: dict):
        msg_df = data.get('MSG')
        if msg_df is None or msg_df.empty:
            self._veh_card.set_text('NO DATA', '')
            return
        frame_str = ''
        for col in msg_df.columns:
            if col in ('Message', 'Msg'):
                for val in msg_df[col]:
                    s = str(val)
                    if 'Frame:' in s:
                        frame_str = s.replace('Frame:', '').strip()
                        break
        if frame_str:
            self._veh_card.set_text(frame_str, '', '#6ee7b7', '#1a3a2a')
        else:
            self._veh_card.set_text('UNKNOWN', '')

    def update_ekf(self, data: dict):
        # Collect FS values from ALL XKF4 instances
        fs_values = []
        for df in get_df_all_instances(data, 'XKF4'):
            for col in ('FS', 'fs'):
                if col in df.columns:
                    fs_values.extend(df[col].dropna().astype(int).tolist())
                    break
        if not fs_values:
            self._ekf_card.set_text('NO DATA', '')
            return
        if any(v > 0 for v in fs_values):
            self._ekf_card.set_text('WARN', f'Filter status > 0 (max={max(fs_values)})', '#fcd34d', '#2a1a00')
        else:
            self._ekf_card.set_text('OK', 'All FS = 0', '#6ee7b7', '#1a3a2a')

    def update_gps(self, data: dict):
        gps_df = get_df_any_instance(data, 'GPS')
        if gps_df is None or gps_df.empty:
            if data.get('SIM2') is not None or data.get('SIM') is not None:
                self._gps_card.set_text('SITL', 'Simulated position (SIM2)', '#93c5fd', '#1a2a3a')
            else:
                self._gps_card.set_text('NO DATA', '')
            return
        status = 0
        sats = 0
        hdop = 0.0
        for col in ('Status', 'status', 'GStatus'):
            if col in gps_df.columns:
                status = int(gps_df[col].iloc[-1])
                break
        for col in ('NSats', 'NSat', 'Sats'):
            if col in gps_df.columns:
                sats = int(gps_df[col].iloc[-1])
                break
        for col in ('HDop', 'Hdop', 'hdop'):
            if col in gps_df.columns:
                hdop = float(gps_df[col].iloc[-1])
                break
        fix_name = GPS_FIX_NAMES.get(status, f'FIX_{status}')
        color = '#6ee7b7' if status >= 3 else '#fcd34d'
        bg = '#1a3a2a' if status >= 3 else '#2a1a00'
        self._gps_card.set_text(fix_name, f'Sats: {sats}  HDop: {hdop:.2f}', color, bg)

    def update_all(self, data: dict, sig_state: str = 'UNVERIFIED', key_id: str = ''):
        self.update_signature(sig_state, key_id)
        self.update_firmware(data)
        self.update_vehicle(data)
        self.update_ekf(data)
        self.update_gps(data)
