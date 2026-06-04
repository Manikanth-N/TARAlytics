import time
import numpy as np
import math
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QCheckBox, QPushButton, QFrame,
)
from PyQt6.QtCore import Qt

try:
    import pyqtgraph.opengl as gl
    GL_AVAILABLE = True
except Exception:
    GL_AVAILABLE = False

from core.gps_converter import best_trajectory
from core.colors import viridis_rgba
from ui.widgets.replay_controls import ReplayControls

MODE_NAMES = {
    0: 'STABILIZE', 1: 'ACRO', 2: 'ALT_HOLD', 3: 'AUTO', 4: 'GUIDED',
    5: 'LOITER', 6: 'RTL', 9: 'LAND', 16: 'POSHOLD', 17: 'BRAKE',
    18: 'THROW', 19: 'AVOID_ADSB', 20: 'GUIDED_NOGPS', 21: 'SMART_RTL',
}


def _interp(times, values, t):
    if len(times) == 0:
        return 0.0
    idx = np.searchsorted(times, t)
    if idx == 0:
        return float(values[0])
    if idx >= len(times):
        return float(values[-1])
    t0, t1 = times[idx - 1], times[idx]
    v0, v1 = values[idx - 1], values[idx]
    dt = t1 - t0
    return float(v0) if dt == 0 else float(v0 + (v1 - v0) * (t - t0) / dt)


class TelemetryPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFixedWidth(160)
        self.setStyleSheet(
            'QFrame#TelemetryPanel { background-color: #1a1a2e; '
            'border-left: 1px solid #3a3a5a; }'
        )
        self.setObjectName('TelemetryPanel')

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(0)

        self._labels = {}
        fields = ['Time', 'Alt', 'Speed', 'Roll', 'Pitch', 'Yaw', 'Mode', 'ESC avg']
        for f in fields:
            hdr = QLabel(f)
            hdr.setStyleSheet(
                'QLabel { color: #7a7aaa; font-size: 10px; '
                'padding: 2px 8px 0px 8px; background: transparent; }'
            )
            val = QLabel('—')
            val.setStyleSheet(
                'QLabel { color: #e8e8e8; font-size: 13px; font-weight: 600; '
                'padding: 0px 8px 6px 8px; background: transparent; }'
            )
            layout.addWidget(hdr)
            layout.addWidget(val)
            self._labels[f] = val

        layout.addStretch(1)

    def update(self, t, alt, speed, roll, pitch, yaw, mode, esc_avg):
        self._labels['Time'].setText(f'{t:.2f} s')
        self._labels['Alt'].setText(f'{alt:.1f} m')
        self._labels['Speed'].setText(f'{speed:.2f} m/s')
        self._labels['Roll'].setText(f'{roll:.2f}°')
        self._labels['Pitch'].setText(f'{pitch:.2f}°')
        self._labels['Yaw'].setText(f'{yaw:.1f}°')
        self._labels['Mode'].setText(mode)
        self._labels['ESC avg'].setText(f'{esc_avg:.0f}%')


class View3DTab(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self._mw = main_window
        self._data = {}
        self._traj = None
        self._vehicle_item = None
        self._traj_item = None
        self._ground_item = None
        self._arrow_items = []
        self._aircraft_items = []
        self._aircraft_scale = 1.0
        self._show_arrows = True
        self._follow_vehicle = True
        self._default_elevation = 30
        self._default_azimuth = 45
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)

        if GL_AVAILABLE:
            self._gl = gl.GLViewWidget()
            self._gl.setBackgroundColor('#0d0d1a')
            self._gl.opts['elevation'] = self._default_elevation
            self._gl.opts['azimuth'] = self._default_azimuth
            self._gl.opts['distance'] = 50
            center_layout.addWidget(self._gl, 1)
        else:
            placeholder = QLabel('OpenGL not available.\nInstall PyOpenGL to enable 3D view.')
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setStyleSheet('color: #adb5bd; font-size: 14px;')
            center_layout.addWidget(placeholder, 1)

        if GL_AVAILABLE:
            ctrl_bar = QFrame(self._gl)  # child of GL widget → overlays it
        else:
            ctrl_bar = QFrame(center)
        ctrl_bar.setStyleSheet(
            'QFrame { background-color: rgba(20,20,30,220); '
            'border: 1px solid #3a3a5a; border-radius: 4px; } '
            'QPushButton { color: #c8c8c8; background-color: #2a2a3a; '
            'border: 1px solid #4a4a6a; border-radius: 3px; '
            'padding: 4px 10px; font-size: 11px; } '
            'QPushButton:hover { background-color: #3a3a5a; } '
            'QCheckBox { color: #c8c8c8; font-size: 11px; padding: 2px 6px; }'
        )
        ctrl_layout = QHBoxLayout(ctrl_bar)
        ctrl_layout.setContentsMargins(6, 4, 6, 4)

        reset_cam_btn = QPushButton('Reset Camera')
        reset_cam_btn.clicked.connect(self._reset_camera)
        ctrl_layout.addWidget(reset_cam_btn)

        self._arrows_cb = QCheckBox('Show Heading')
        self._arrows_cb.setChecked(True)
        self._arrows_cb.stateChanged.connect(self._toggle_arrows)
        ctrl_layout.addWidget(self._arrows_cb)

        ctrl_bar.adjustSize()
        if GL_AVAILABLE:
            # Reposition when GL view resizes
            def _reposition():
                ctrl_bar.move(8, self._gl.height() - ctrl_bar.height() - 8)
            self._gl.resized = _reposition   # store reference; called below
            ctrl_bar.move(8, 60)  # initial position (will update on first resize)
            self._ctrl_bar = ctrl_bar
        else:
            center_layout.addWidget(ctrl_bar)

        self._replay = ReplayControls()
        self._replay.setStyleSheet('background: #13131f;')
        # Playback / scrub / step drives the SHARED cursor, so every surface
        # (Horizon, RC, Timeline, Dock, Map, Plotter) animates with the replay.
        # The shared cursor then calls View3D.set_time → _on_time_changed for the
        # 3-D update, so there is a single update path (no double-update, no loop;
        # ReplayControls.set_time does not re-emit).
        self._replay.time_changed.connect(self._on_replay_time)
        self._replay.follow_changed.connect(self._on_follow_changed)
        center_layout.addWidget(self._replay)

        layout.addWidget(center, 1)

        self._telem = TelemetryPanel()
        layout.addWidget(self._telem)

    def update_data(self, data: dict):
        self._data = data
        if not GL_AVAILABLE:
            return

        traj = best_trajectory(data)
        self._traj = traj

        for item in self._arrow_items:
            self._gl.removeItem(item)
        self._arrow_items.clear()

        for item in self._aircraft_items:
            self._gl.removeItem(item)
        self._aircraft_items.clear()

        if self._traj_item:
            self._gl.removeItem(self._traj_item)
            self._traj_item = None
        if self._ground_item:
            self._gl.removeItem(self._ground_item)
            self._ground_item = None
        if self._vehicle_item:
            self._gl.removeItem(self._vehicle_item)
            self._vehicle_item = None

        if traj is None:
            return

        east = traj['east']
        north = traj['north']
        up = traj['up']
        times = traj['times']

        pts = np.column_stack([east, north, up]).astype(np.float32)

        # Deduplicate consecutive identical points
        diffs = np.diff(pts, axis=0)
        keep = np.concatenate([[True], np.any(diffs != 0, axis=1)])
        pts_clean = pts[keep]
        if len(pts_clean) < 2:
            pts_clean = pts

        # Detect stationary SITL log (all axes < 1 m extent)
        extent_xyz = np.ptp(pts_clean, axis=0)  # [E, N, U]
        _stationary = np.all(extent_xyz < 1.0)
        if _stationary:
            pts_draw = pts_clean.copy()
            pts_draw[:, 2] *= 5.0   # exaggerate altitude ×5 for visibility
            traj_color = np.tile([0.3, 0.8, 1.0, 1.0], (len(pts_draw), 1)).astype(np.float32)
            traj_width = 4
        else:
            pts_draw = pts_clean
            alt_min = up.min()
            alt_max = up.max()
            alt_range = alt_max - alt_min if alt_max > alt_min else 1.0
            traj_color = np.array([
                viridis_rgba((u - alt_min) / alt_range) for u in pts_clean[:, 2]
            ], dtype=np.float32)
            traj_width = 2

        self._traj_item = gl.GLLinePlotItem(
            pos=pts_draw, color=traj_color, width=traj_width, antialias=True
        )
        self._gl.addItem(self._traj_item)

        # Compute scene bbox diagonal for arrow scaling
        bbox_diag = float(np.linalg.norm(extent_xyz)) if not _stationary else float(np.ptp(pts_draw[:, 2]))

        self._add_ground_plane(east, north)

        self._vehicle_item = None
        _ext = max(
            float(east.max() - east.min()) if len(east) > 0 else 1,
            float(north.max() - north.min()) if len(north) > 0 else 1,
            float(up.max() - up.min()) if len(up) > 0 else 1,
        )
        self._aircraft_scale = max(0.5, _ext * 0.025)
        self._create_aircraft_items()
        init_yaw = 0.0
        att_df = data.get('ATT')
        if att_df is not None and not att_df.empty:
            for _col in ('Yaw', 'yaw'):
                if _col in att_df.columns:
                    init_yaw = float(att_df[_col].iloc[0])
                    break
        self._update_aircraft_pose(float(east[0]), float(north[0]), float(up[0]), init_yaw)

        home = gl.GLScatterPlotItem(
            pos=np.array([[0, 0, 0]], dtype=np.float32),
            size=12, color=(1.0, 0.9, 0.0, 1.0)
        )
        self._gl.addItem(home)
        self._arrow_items.append(home)

        self._add_heading_arrows(data, east, north, up, times, bbox_diag)

        extent = max(
            float(east.max() - east.min()) if len(east) > 0 else 1,
            float(north.max() - north.min()) if len(north) > 0 else 1,
            float(up.max() - up.min()) if len(up) > 0 else 1,
        )
        dist = max(extent * 2.0, 10.0)
        cx = float(np.mean(east))
        cy = float(np.mean(north))
        cz = float(np.mean(up))
        self._gl.opts['center'] = pg_vector(cx, cy, cz)
        self._gl.opts['distance'] = dist
        self._default_dist = dist
        self._default_center = (cx, cy, cz)

        t_min = float(times[0]) if len(times) > 0 else 0.0
        t_max = float(times[-1]) if len(times) > 0 else 1.0
        self._replay.set_range(t_min, t_max)

    def _add_ground_plane(self, east, north):
        w = max(float(east.max() - east.min()) + 40, 20)
        h = max(float(north.max() - north.min()) + 40, 20)
        cx = float((east.min() + east.max()) / 2)
        cy = float((north.min() + north.max()) / 2)
        grid = gl.GLGridItem()
        grid.setSize(x=w, y=h)
        grid.setSpacing(x=10, y=10)
        grid.setColor((77, 77, 102, 77))
        grid.translate(cx, cy, 0)
        self._gl.addItem(grid)
        self._arrow_items.append(grid)

    def _add_heading_arrows(self, data, east, north, up, times, bbox_diag=1.0):
        att_df = data.get('ATT')
        if att_df is None or att_df.empty:
            return
        yaw_col = None
        for c in ('Yaw', 'yaw'):
            if c in att_df.columns:
                yaw_col = c
                break
        if yaw_col is None:
            return

        att_times = att_df['TimeS'].values.astype(float)
        yaw_vals = att_df[yaw_col].values.astype(float)

        arrow_len = max(0.5, bbox_diag * 0.15)
        subsample_dt = 2.0
        last_t = -999.0

        for i, t in enumerate(times):
            if t - last_t < subsample_dt:
                continue
            last_t = t
            yaw_deg = _interp(att_times, yaw_vals, t)
            yaw_rad = math.radians(yaw_deg)
            x0, y0, z0 = float(east[i]), float(north[i]), float(up[i])
            dx = arrow_len * math.sin(yaw_rad)
            dy = arrow_len * math.cos(yaw_rad)
            pts = np.array([[x0, y0, z0], [x0 + dx, y0 + dy, z0]], dtype=np.float32)
            arrow = gl.GLLinePlotItem(pos=pts, color=(1, 1, 1, 0.7), width=1.5)
            self._gl.addItem(arrow)
            self._arrow_items.append(arrow)

    def _create_aircraft_items(self):
        orange = (1.0, 0.45, 0.05, 1.0)
        dim    = (1.0, 0.45, 0.05, 0.75)
        zero   = np.zeros((2, 3), dtype=np.float32)
        fuselage = gl.GLLinePlotItem(pos=zero.copy(), color=orange, width=3, antialias=True)
        wings    = gl.GLLinePlotItem(pos=zero.copy(), color=orange, width=3, antialias=True)
        tail     = gl.GLLinePlotItem(pos=zero.copy(), color=dim,    width=2, antialias=True)
        for item in (fuselage, wings, tail):
            self._gl.addItem(item)
        self._aircraft_items = [fuselage, wings, tail]

    def _update_aircraft_pose(self, xe: float, xn: float, xu: float, yaw_deg: float):
        if not self._aircraft_items:
            return
        L = self._aircraft_scale
        sin_y = math.sin(math.radians(yaw_deg))
        cos_y = math.cos(math.radians(yaw_deg))

        # Aircraft body frame → ENU world: forward=North@yaw0, right=East@yaw0
        # pt(fwd, right) maps body-frame offsets to world coords
        def pt(fwd, right):
            return [xe + fwd * sin_y + right * cos_y,
                    xn + fwd * cos_y - right * sin_y,
                    xu]

        self._aircraft_items[0].setData(pos=np.array([
            pt(L, 0),          # nose
            pt(-0.5 * L, 0),   # tail
        ], dtype=np.float32))

        self._aircraft_items[1].setData(pos=np.array([
            pt(0.1 * L, -0.8 * L),   # left wing tip
            pt(0.1 * L,  0.8 * L),   # right wing tip
        ], dtype=np.float32))

        self._aircraft_items[2].setData(pos=np.array([
            pt(-0.4 * L, -0.3 * L),  # left tail fin
            pt(-0.4 * L,  0.3 * L),  # right tail fin
        ], dtype=np.float32))

    def _on_replay_time(self, t: float):
        """Replay produced a time. Drive the shared cursor so all surfaces follow;
        fall back to a direct 3-D update if no AppState is wired (standalone use)."""
        app = getattr(self._mw, '_app_state', None)
        if app is not None:
            app.set_cursor_time(t)        # → cursor_time_changed → View3D.set_time
        else:
            self._on_time_changed(t)

    def _on_time_changed(self, t: float):
        traj = self._traj
        if traj is None:
            return
        times = traj['times']
        east = traj['east']
        north = traj['north']
        up = traj['up']

        if len(times) == 0:
            return

        xe = _interp(times, east, t)
        xn = _interp(times, north, t)
        xu = _interp(times, up, t)

        if self._follow_vehicle and GL_AVAILABLE:
            self._gl.opts['center'] = pg_vector(xe, xn, xu)
            self._gl.update()

        data = self._data
        roll, pitch, yaw = 0.0, 0.0, 0.0
        att_df = data.get('ATT')
        if att_df is not None and not att_df.empty:
            att_times = att_df['TimeS'].values.astype(float)
            for col in ('Roll', 'Pitch', 'Yaw'):
                if col in att_df.columns:
                    v = _interp(att_times, att_df[col].values.astype(float), t)
                    if col == 'Roll':
                        roll = v
                    elif col == 'Pitch':
                        pitch = v
                    elif col == 'Yaw':
                        yaw = v

        self._update_aircraft_pose(xe, xn, xu, yaw)

        speed = math.sqrt(
            _interp_data(data, 'SIM2', 'VN', times, t) ** 2 +
            _interp_data(data, 'SIM2', 'VE', times, t) ** 2 +
            _interp_data(data, 'SIM2', 'VD', times, t) ** 2
        )

        mode = _current_mode(data, t)
        esc_avg = _esc_avg(data, t)

        self._telem.update(
            t=t - (times[0] if len(times) > 0 else 0),
            alt=xu,
            speed=speed,
            roll=roll,
            pitch=pitch,
            yaw=yaw,
            mode=mode,
            esc_avg=esc_avg,
        )

        try:
            self._mw._tab_plotter.set_crosshair(t)
        except Exception:
            pass

    def _on_follow_changed(self, follow: bool):
        self._follow_vehicle = follow

    def _toggle_arrows(self, state: int):
        self._show_arrows = bool(state)
        for item in self._arrow_items:
            item.setVisible(self._show_arrows)

    def set_time(self, t_abs: float):
        """Called from plotter crosshair movement to sync 3D replay."""
        now = time.monotonic()
        if now - getattr(self, '_last_set_time', 0.0) < 0.033:
            return
        self._last_set_time = now
        self._replay.set_time(t_abs)
        self._on_time_changed(t_abs)

    def _reset_camera(self):
        if not GL_AVAILABLE:
            return
        self._gl.opts['elevation'] = self._default_elevation
        self._gl.opts['azimuth'] = self._default_azimuth
        if hasattr(self, '_default_dist'):
            self._gl.opts['distance'] = self._default_dist
        if hasattr(self, '_default_center'):
            cx, cy, cz = self._default_center
            self._gl.opts['center'] = pg_vector(cx, cy, cz)
        self._gl.update()


def _interp_data(data: dict, msg: str, col: str, fallback_times, t: float) -> float:
    df = data.get(msg)
    if df is None or df.empty or col not in df.columns:
        return 0.0
    times = df['TimeS'].values.astype(float)
    vals = df[col].values.astype(float)
    return _interp(times, vals, t)


def _current_mode(data: dict, t: float) -> str:
    df = data.get('MODE')
    if df is None or df.empty:
        return '—'
    times = df['TimeS'].values.astype(float)
    idx = np.searchsorted(times, t)
    if idx == 0:
        idx = 0
    else:
        idx = idx - 1
    mode_col = None
    for c in ('Mode', 'ModeNum'):
        if c in df.columns:
            mode_col = c
            break
    if mode_col is None:
        return '—'
    m = int(df[mode_col].iloc[min(idx, len(df) - 1)])
    return MODE_NAMES.get(m, f'MODE_{m}')


def _esc_avg(data: dict, t: float) -> float:
    vals = []
    for key, df in data.items():
        if not key.startswith('ESCX[') or df.empty or 'TimeS' not in df.columns:
            continue
        col = next((c for c in ('outpct', 'Outpct', 'OutPct') if c in df.columns), None)
        if col is None:
            continue
        v = _interp(df['TimeS'].values.astype(float), df[col].values.astype(float), t)
        vals.append(v)
    return float(np.mean(vals)) if vals else 0.0


def pg_vector(x, y, z):
    try:
        from pyqtgraph.Qt import QtGui
        import pyqtgraph as pg
        return pg.Vector(x, y, z)
    except Exception:
        try:
            from PyQt6.QtGui import QVector3D
            return QVector3D(x, y, z)
        except Exception:
            return (x, y, z)
