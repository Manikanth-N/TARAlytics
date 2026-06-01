import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame, QSizePolicy,
)
from PyQt6.QtCore import Qt
from core.gps_converter import best_trajectory


class _StatCard(QFrame):
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            'QFrame { background: #16162a; border: 1px solid #3a3a5e; border-radius: 6px; }'
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(62)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(2)

        self._lbl = QLabel(label)
        self._lbl.setStyleSheet('color: #8888aa; font-size: 10px; font-weight: bold; border: none;')
        lay.addWidget(self._lbl)

        self._val = QLabel('—')
        self._val.setStyleSheet('color: #d0d0e8; font-size: 14px; font-weight: bold; border: none;')
        lay.addWidget(self._val)

    def set_value(self, text: str, color: str = '#d0d0e8'):
        self._val.setText(text)
        self._val.setStyleSheet(
            f'color: {color}; font-size: 14px; font-weight: bold; border: none;'
        )


class FlightSummaryWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._dur  = _StatCard('DURATION')
        self._alt  = _StatCard('MAX ALTITUDE')
        self._spd  = _StatCard('MAX SPEED')
        self._dst  = _StatCard('DISTANCE')
        self._arm  = _StatCard('ARM EVENTS')

        for card in (self._dur, self._alt, self._spd, self._dst, self._arm):
            layout.addWidget(card)

    def update_data(self, data: dict):
        self._update_duration(data)
        self._update_altitude(data)
        self._update_speed(data)
        self._update_distance(data)
        self._update_arm_events(data)

    def _update_duration(self, data: dict):
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
        if t_min is not None:
            dur = t_max - t_min
            m, s = int(dur // 60), int(dur % 60)
            self._dur.set_value(f'{m}:{s:02d}', '#6ee7b7')
        else:
            self._dur.set_value('—')

    def _update_altitude(self, data: dict):
        alt_max = None
        for key in ('GPS', 'GPS[0]', 'POS'):
            df = data.get(key)
            if df is not None and not df.empty:
                alt_col = next((c for c in ('Alt', 'alt') if c in df.columns), None)
                if alt_col:
                    v = float(df[alt_col].dropna().max())
                    if alt_max is None or v > alt_max:
                        alt_max = v
                    break
        if alt_max is None:
            sim2 = data.get('SIM2')
            if sim2 is not None and not sim2.empty and 'PD' in sim2.columns:
                alt_max = float(-sim2['PD'].min())
        if alt_max is not None:
            self._alt.set_value(f'{alt_max:.1f} m', '#93c5fd')
        else:
            self._alt.set_value('—')

    def _update_speed(self, data: dict):
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
                            spd_max = float(df[col].max())
                            break
                    if spd_max is not None:
                        break
        if spd_max is not None:
            self._spd.set_value(f'{spd_max:.1f} m/s', '#fcd34d')
        else:
            self._spd.set_value('—')

    def _update_distance(self, data: dict):
        traj = best_trajectory(data)
        if traj is not None and len(traj['east']) > 1:
            east, north = traj['east'], traj['north']
            dist = float(np.sqrt(np.diff(east) ** 2 + np.diff(north) ** 2).sum())
            text = f'{dist / 1000:.2f} km' if dist >= 1000 else f'{dist:.0f} m'
            self._dst.set_value(text, '#c4b5fd')
        else:
            self._dst.set_value('—')

    def _update_arm_events(self, data: dict):
        arm_df = data.get('ARM')
        if arm_df is not None and not arm_df.empty:
            count = len(arm_df)
            self._arm.set_value(str(count), '#fb923c')
        else:
            self._arm.set_value('—')
