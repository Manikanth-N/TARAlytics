import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox, QCheckBox,
)
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QPainter, QColor, QLinearGradient, QPen, QFont

from core.gps_converter import best_trajectory
from core.colors import altitude_rgb
from core.event_extractor import EventExtractor
from core.basemap.projection import enu_to_lla
from core.basemap.aviation import AviationData
from core.basemap.overlays import OverlayManager
from ui.widgets.map_basemap import MapBasemap
from ui.widgets.map_decorations import MapDecorations

_MAX_TRACK_PTS = 3000

# Map event markers to colours by severity (operationally interesting only).
_EVT_MAP_COLOR = {'CRITICAL': '#FF3D3D', 'ERROR': '#E67E22', 'WARNING': '#FFB300'}


class _AltitudeLegend(QWidget):
    """Vertical altitude colour bar (red = high → blue = low) with min/mid/max metres."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(70)
        self._lo = 0.0
        self._hi = 1.0
        self._has = False

    def set_range(self, lo: float, hi: float):
        self._lo, self._hi, self._has = lo, hi, True
        self.update()

    def clear(self):
        self._has = False
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor('#0d0d1a'))
        p.setPen(QPen(QColor('#aaaacc')))
        f = QFont(); f.setPointSize(8); p.setFont(f)
        p.drawText(6, 14, 'Alt')
        if not self._has:
            p.end(); return
        bar_x, bar_w = 8, 16
        top, bottom = 26, self.height() - 18
        grad = QLinearGradient(0, top, 0, bottom)   # top = high = red
        for stop, t in [(0.0, 1.0), (0.25, 0.75), (0.5, 0.5), (0.75, 0.25), (1.0, 0.0)]:
            r, g, b = altitude_rgb(t)
            grad.setColorAt(stop, QColor(r, g, b))
        p.fillRect(bar_x, top, bar_w, bottom - top, grad)
        p.setPen(QPen(QColor('#3a3a5a')))
        p.drawRect(bar_x, top, bar_w, bottom - top)
        p.setPen(QPen(QColor('#ccccdd')))
        mid = (self._lo + self._hi) / 2.0
        tx = bar_x + bar_w + 4
        p.drawText(tx, top + 5, f'{self._hi:.0f} m')
        p.drawText(tx, (top + bottom) // 2 + 4, f'{mid:.0f} m')
        p.drawText(tx, bottom, f'{self._lo:.0f} m')
        p.end()


class MapTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._traj = None
        self._pos_item = None
        self._evt_highlight = None
        self._events = []
        self._event_times = np.array([])
        self._alt_min = 0.0
        self._alt_max = 0.0
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

        # ── Basemap controls (Phase 1) ──────────────────────────────────────
        # Basemap style + layer toggles. Airports/Runways are wired to the overlay
        # registry in M3; Labels is a Phase-1 placeholder (Streets=labels visible,
        # Minimal=labels hidden) whose internal implementation Phase 2 replaces
        # without changing this UI.
        self._settings = QSettings('TARAlyticsAnalyzer', 'Map')
        tb.addWidget(self._lbl('Basemap'))
        self._basemap_cb = QComboBox()
        self._basemap_cb.addItems(['Streets', 'Minimal', 'Off'])
        self._basemap_cb.setStyleSheet(
            'QComboBox { background: #495057; color: white; border-radius: 3px; '
            'padding: 2px 6px; font-size: 11px; }')
        tb.addWidget(self._basemap_cb)
        self._cb_labels = self._toggle('Labels', True)
        self._cb_airports = self._toggle('Airports', True)
        self._cb_runways = self._toggle('Runways', True)
        for w in (self._cb_labels, self._cb_airports, self._cb_runways):
            tb.addWidget(w)
        self._restore_basemap_settings()
        self._basemap_cb.currentTextChanged.connect(self._on_basemap_style)
        self._cb_labels.toggled.connect(self._on_labels_toggled)

        legend = QLabel(
            '<span style="color:#ffd700">★</span> Home  '
            '<span style="color:#28a745">●</span> Start  '
            '<span style="color:#dc3545">✕</span> End  '
            '<span style="color:#ff6600">▲</span> Aircraft  '
            '| Track coloured by altitude (blue = low → red = high)'
        )
        legend.setStyleSheet('color: #aaaacc; font-size: 11px;')
        tb.addWidget(legend)
        tb.addStretch()

        self._cursor_alt_lbl = QLabel('Alt @ cursor: — m')
        self._cursor_alt_lbl.setStyleSheet('color: #e8e8e8; font-size: 11px; font-weight: 600;')
        tb.addWidget(self._cursor_alt_lbl)
        self._src_lbl = QLabel('')
        self._src_lbl.setStyleSheet('color: #7a8fa8; font-size: 11px;')
        tb.addWidget(self._src_lbl)
        layout.addWidget(toolbar)

        # Plot + altitude legend side by side
        body = QWidget()
        body_l = QHBoxLayout(body)
        body_l.setContentsMargins(0, 0, 0, 0)
        body_l.setSpacing(0)

        self._plot = pg.PlotWidget()
        self._plot.setBackground('#0d0d1a')
        self._plot.setAspectLocked(True)
        self._plot.showGrid(x=True, y=True, alpha=0.15)
        self._plot.getAxis('bottom').setLabel('East (m)')
        self._plot.getAxis('left').setLabel('North (m)')
        body_l.addWidget(self._plot, 1)

        self._alt_legend = _AltitudeLegend()
        body_l.addWidget(self._alt_legend)
        layout.addWidget(body, 1)

        self._placeholder = pg.TextItem(
            'Load a log file to see the 2D GPS track.',
            color='#555577', anchor=(0.5, 0.5),
        )
        self._plot.addItem(self._placeholder)

        # Basemap backdrop (z = -1, beneath everything). Built lazily on data load.
        self._basemap = MapBasemap(self._plot)
        self._apply_basemap_style()

        # Overlay layers (airports/runways now; registry-extensible) above the
        # backdrop, below the track. Built from OurAirports on data load.
        self._overlays = OverlayManager(self._plot)
        self._cb_airports.toggled.connect(
            lambda on: self._set_overlay('airports', 'show_airports', on))
        self._cb_runways.toggled.connect(
            lambda on: self._set_overlay('runways', 'show_runways', on))

        # Metric scale bar + north arrow (overlay child of the plot, so it is
        # captured by grab() for PNG/PDF export too).
        self._decorations = MapDecorations(self._plot)

    def _set_overlay(self, layer_id, setting_key, on):
        self._overlays.set_visible(layer_id, on)
        self._settings.setValue(setting_key, on)

    # ── basemap toolbar helpers ─────────────────────────────────────────────
    def _lbl(self, text):
        l = QLabel(text)
        l.setStyleSheet('color: #aaaacc; font-size: 11px;')
        return l

    def _toggle(self, text, checked):
        cb = QCheckBox(text)
        cb.setChecked(checked)
        cb.setStyleSheet('QCheckBox { color: #cfd6e4; font-size: 11px; }')
        return cb

    def _restore_basemap_settings(self):
        style = self._settings.value('basemap_style', 'Streets')
        if style not in ('Streets', 'Minimal', 'Off'):
            style = 'Streets'
        self._basemap_cb.setCurrentText(style)
        self._cb_labels.setChecked(style != 'Minimal')
        self._cb_airports.setChecked(
            self._settings.value('show_airports', True, type=bool))
        self._cb_runways.setChecked(
            self._settings.value('show_runways', True, type=bool))

    def _on_basemap_style(self, _text):
        # keep the Labels placeholder in sync with Streets/Minimal (Phase 1)
        style = self._basemap_cb.currentText()
        self._cb_labels.blockSignals(True)
        self._cb_labels.setChecked(style == 'Streets')
        self._cb_labels.blockSignals(False)
        self._settings.setValue('basemap_style', style)
        self._apply_basemap_style()

    def _on_labels_toggled(self, on):
        # Phase 1: Labels drives Streets/Minimal; the dropdown follows.
        if self._basemap_cb.currentText() != 'Off':
            self._basemap_cb.blockSignals(True)
            self._basemap_cb.setCurrentText('Streets' if on else 'Minimal')
            self._basemap_cb.blockSignals(False)
            self._settings.setValue('basemap_style', self._basemap_cb.currentText())
            self._apply_basemap_style()

    def _apply_basemap_style(self):
        self._basemap.set_style(self._basemap_cb.currentText().lower())

    def _build_overlays(self, traj, lat0, lon0):
        """Rebuild airports/runways overlays for this flight's lat/lon bbox."""
        if abs(lat0) < 1e-3 and abs(lon0) < 1e-3:
            self._overlays.clear()                 # SIM / non-geographic
            return
        east, north = traj['east'], traj['north']
        margin = 2000.0                            # +2 km context around the track
        lat_a, lon_a = enu_to_lla(float(east.min()) - margin,
                                  float(north.min()) - margin, lat0, lon0)
        lat_b, lon_b = enu_to_lla(float(east.max()) + margin,
                                  float(north.max()) + margin, lat0, lon0)
        bbox = (lat_a, lat_b, lon_a, lon_b)
        av = AviationData.load()
        self._overlays.set_data(av, lat0, lon0, bbox)
        self._overlays.set_visible('airports', self._cb_airports.isChecked())
        self._overlays.set_visible('runways', self._cb_runways.isChecked())

    def update_data(self, data: dict):
        self._plot.clear()
        self._basemap.reset()          # plot.clear() removed backdrop items; drop refs
        self._overlays.reset()
        self._pos_item = None
        self._evt_highlight = None
        self._alt_legend.clear()
        self._cursor_alt_lbl.setText('Alt @ cursor: — m')
        self._src_lbl.setText('')
        self._placeholder = pg.TextItem(
            'No GPS / position data in this log.',
            color='#555577', anchor=(0.5, 0.5),
        )
        self._events = EventExtractor.collect(data)
        self._event_times = np.array([e[0] for e in self._events], dtype=float)

        traj = best_trajectory(data)
        self._traj = traj
        if traj is None:
            self._basemap.set_origin(0.0, 0.0)      # no geographic backdrop
            self._plot.addItem(self._placeholder)
            return

        # Position the basemap backdrop on this flight's home origin.
        lat0 = float(traj.get('origin_lat', 0.0))
        lon0 = float(traj.get('origin_lon', 0.0))
        self._basemap.set_origin(lat0, lon0)
        self._build_overlays(traj, lat0, lon0)

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

        self._alt_min = float(up.min())
        self._alt_max = float(up.max())
        alt_rng = self._alt_max - self._alt_min if self._alt_max > self._alt_min else 1.0
        fracs   = (up_s - self._alt_min) / alt_rng

        # Per-point brushes: blue (low) → red (high)
        brushes = []
        for fr in fracs:
            r, g, b = altitude_rgb(float(fr))
            brushes.append(pg.mkBrush(r, g, b, 230))

        track = pg.ScatterPlotItem(
            x=east_s.tolist(), y=north_s.tolist(),
            size=4, pen=None, brush=brushes,
        )
        self._plot.addItem(track)

        # Altitude legend + source readout
        self._alt_legend.set_range(self._alt_min, self._alt_max)
        self._src_lbl.setText(f'Altitude source: {traj.get("alt_source", "—")}')

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

        # Event markers — white outline keeps them readable over any track colour.
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
                    x=xs, y=ys, size=13, symbol='d',
                    pen=pg.mkPen('#ffffff', width=1.4), brush=pg.mkBrush(col)))

        # Jumped-event highlight ring (hidden until an event is selected).
        self._evt_highlight = pg.ScatterPlotItem(
            x=[], y=[], size=22, symbol='o',
            pen=pg.mkPen('#22AADF', width=2), brush=pg.mkBrush(34, 170, 223, 40))
        self._plot.addItem(self._evt_highlight)

        # Aircraft position marker (live)
        self._pos_item = pg.ScatterPlotItem(
            x=[float(east[0])], y=[float(north[0])], size=14, symbol='t1',
            pen=pg.mkPen('#ffffff', width=2), brush=pg.mkBrush('#ff6600'),
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

    def _alt_at_time(self, t_abs: float):
        """Altitude (m) on the track at absolute time t, or None."""
        traj = self._traj
        if traj is None or len(traj['times']) == 0:
            return None
        idx = int(np.searchsorted(traj['times'], t_abs))
        idx = min(max(idx, 0), len(traj['up']) - 1)
        return float(traj['up'][idx])

    def set_time(self, t_abs: float):
        if self._pos_item is None:
            return
        ex, ey = self._pos_at_time(t_abs)
        if ex is not None:
            self._pos_item.setData(x=[ex], y=[ey])
        alt = self._alt_at_time(t_abs)
        if alt is not None:
            self._cursor_alt_lbl.setText(f'Alt @ cursor: {alt:.1f} m')

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
