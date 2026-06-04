import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
)
from PyQt6.QtCore import Qt

from core.gps_converter import best_trajectory
from core.colors import viridis_rgba
from core.event_extractor import EventExtractor

_MAX_TRACK_PTS = 3000

# Map event markers to colours by severity (operationally interesting only).
_EVT_MAP_COLOR = {'CRITICAL': '#FF3D3D', 'ERROR': '#E67E22', 'WARNING': '#FFB300'}


class MapTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._traj = None
        self._pos_item = None
        self._evt_highlight = None
        self._events = []
        self._event_times = np.array([])
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        toolbar = QWidget()
        toolbar.setStyleSheet('background: #13131f;')
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(4, 3, 4, 3)
        tb.setSpacing(8)

        btn_fit = QPushButton('Fit View')
        btn_fit.setStyleSheet(
            'QPushButton { background: #495057; color: white; border-radius: 3px; '
            'padding: 3px 8px; font-size: 11px; }'
            'QPushButton:hover { background: #6c757d; }'
        )
        btn_fit.clicked.connect(self._fit_view)
        tb.addWidget(btn_fit)

        legend = QLabel(
            '<span style="color:#ffd700">★</span> Home  '
            '<span style="color:#28a745">●</span> Start  '
            '<span style="color:#dc3545">✕</span> End  '
            '<span style="color:#ff6600">▲</span> Aircraft  '
            '| Track colored by altitude (low=purple → high=yellow)'
        )
        legend.setStyleSheet('color: #aaaacc; font-size: 11px;')
        tb.addWidget(legend)
        tb.addStretch()
        layout.addWidget(toolbar)

        self._plot = pg.PlotWidget()
        self._plot.setBackground('#0d0d1a')
        self._plot.setAspectLocked(True)
        self._plot.showGrid(x=True, y=True, alpha=0.15)
        self._plot.getAxis('bottom').setLabel('East (m)')
        self._plot.getAxis('left').setLabel('North (m)')
        layout.addWidget(self._plot, 1)

        self._placeholder = pg.TextItem(
            'Load a log file to see the 2D GPS track.',
            color='#555577', anchor=(0.5, 0.5),
        )
        self._plot.addItem(self._placeholder)

    def update_data(self, data: dict):
        self._plot.clear()
        self._pos_item = None
        self._evt_highlight = None
        self._placeholder = pg.TextItem(
            'No GPS / position data in this log.',
            color='#555577', anchor=(0.5, 0.5),
        )
        self._events = EventExtractor.collect(data)
        self._event_times = np.array([e[0] for e in self._events], dtype=float)

        traj = best_trajectory(data)
        self._traj = traj
        if traj is None:
            self._plot.addItem(self._placeholder)
            return

        east  = traj['east']
        north = traj['north']
        up    = traj['up']

        # Subsample for rendering performance
        n = len(east)
        if n > _MAX_TRACK_PTS:
            step = n // _MAX_TRACK_PTS
            idx  = np.arange(0, n, step)
            east_s = east[idx];  north_s = north[idx];  up_s = up[idx]
        else:
            east_s, north_s, up_s = east, north, up

        alt_min = float(up_s.min())
        alt_max = float(up_s.max())
        alt_rng = alt_max - alt_min if alt_max > alt_min else 1.0
        fracs   = (up_s - alt_min) / alt_rng

        # Build per-point brushes (viridis 0→1 = purple→yellow)
        rgba = np.array([viridis_rgba(f) for f in fracs])
        brushes = [pg.mkBrush(int(r * 255), int(g * 255), int(b * 255), 220)
                   for r, g, b, _ in rgba]

        track = pg.ScatterPlotItem(
            x=east_s.tolist(), y=north_s.tolist(),
            size=4, pen=None, brush=brushes,
        )
        self._plot.addItem(track)

        # Home marker
        self._plot.addItem(pg.ScatterPlotItem(
            x=[0.0], y=[0.0], size=14, symbol='star',
            pen=pg.mkPen('#ffd700', width=2), brush=pg.mkBrush('#ffd700'),
        ))

        # Start / End markers
        self._plot.addItem(pg.ScatterPlotItem(
            x=[float(east[0])], y=[float(north[0])], size=13, symbol='o',
            pen=pg.mkPen('#28a745', width=2), brush=pg.mkBrush(40, 167, 69, 180),
        ))
        self._plot.addItem(pg.ScatterPlotItem(
            x=[float(east[-1])], y=[float(north[-1])], size=13, symbol='x',
            pen=pg.mkPen('#dc3545', width=2), brush=pg.mkBrush('#dc3545'),
        ))

        # Event markers (operationally interesting severities), placed on the track.
        for sev, col in _EVT_MAP_COLOR.items():
            xs, ys = [], []
            for ts, esev, _ty, _msg in self._events:
                if esev != sev:
                    continue
                ex, ey = self._pos_at_time(ts)
                if ex is not None:
                    xs.append(ex); ys.append(ey)
            if xs:
                self._plot.addItem(pg.ScatterPlotItem(
                    x=xs, y=ys, size=11, symbol='d',
                    pen=pg.mkPen(col, width=1), brush=pg.mkBrush(col)))

        # Jumped-event highlight ring (hidden until an event is selected).
        self._evt_highlight = pg.ScatterPlotItem(
            x=[], y=[], size=22, symbol='o',
            pen=pg.mkPen('#22AADF', width=2), brush=pg.mkBrush(34, 170, 223, 40))
        self._plot.addItem(self._evt_highlight)

        # Aircraft position marker (live)
        self._pos_item = pg.ScatterPlotItem(
            x=[float(east[0])], y=[float(north[0])], size=14, symbol='t1',
            pen=pg.mkPen('#ff6600', width=2), brush=pg.mkBrush('#ff6600'),
        )
        self._plot.addItem(self._pos_item)

        self._fit_view()

    def _pos_at_time(self, t_abs: float):
        """(east, north) on the track at absolute time t, or (None, None)."""
        traj = self._traj
        if traj is None:
            return None, None
        times = traj['times']
        if len(times) == 0:
            return None, None
        idx = int(np.searchsorted(times, t_abs))
        idx = min(max(idx, 0), len(traj['east']) - 1)
        return float(traj['east'][idx]), float(traj['north'][idx])

    def set_time(self, t_abs: float):
        if self._pos_item is None:
            return
        ex, ey = self._pos_at_time(t_abs)
        if ex is not None:
            self._pos_item.setData(x=[ex], y=[ey])

    def highlight_event(self, t_abs: float):
        """Ring the track position of the event nearest t — driven by event_jumped,
        so selecting an event marks where on the path it happened."""
        if self._evt_highlight is None or self._event_times.size == 0:
            return
        idx = int(np.argmin(np.abs(self._event_times - t_abs)))
        ex, ey = self._pos_at_time(self._event_times[idx])
        if ex is not None:
            self._evt_highlight.setData(x=[ex], y=[ey])

    def _fit_view(self):
        self._plot.enableAutoRange()
        self._plot.autoRange()
