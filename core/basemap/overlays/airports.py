"""Airports overlay — aerodrome markers + idents from OurAirports (M3)."""
from __future__ import annotations

import pyqtgraph as pg
from PyQt6.QtGui import QFont

from core.basemap.overlays import OverlayLayer

_COLOR = '#7fd1ff'
# Only label/keep "real" aerodromes — skip heliports/closed/seaplane clutter.
_KINDS = {'small_airport', 'medium_airport', 'large_airport'}


class AirportsOverlay(OverlayLayer):
    id = 'airports'
    label = 'Airports'
    default_visible = True
    z_value = -0.4              # above runways (-0.5), below the track (0)

    def build(self, aviation, origin, bbox) -> None:
        lat0, lat1, lon0, lon1 = bbox
        airports = [a for a in aviation.airports_in_bbox(lat0, lat1, lon0, lon1)
                    if a.kind in _KINDS]
        if not airports:
            return
        xs, ys = [], []
        for a in airports:
            e, n = self._enu(a.lat, a.lon, origin)
            xs.append(e); ys.append(n)
            label = pg.TextItem(a.ident or a.name, color=_COLOR, anchor=(0.0, 1.2))
            label.setFont(QFont('', 8))
            label.setPos(e, n)
            self._add(label)
        markers = pg.ScatterPlotItem(
            x=xs, y=ys, size=12, symbol='s',
            pen=pg.mkPen('#0d0d1a', width=1), brush=pg.mkBrush(_COLOR))
        self._add(markers)

    def report_facts(self, track) -> list[str]:
        # M6 fills nearest-airport facts via aviation.nearest_airport directly;
        # the overlay keeps report_facts available for the registry contract.
        return []
