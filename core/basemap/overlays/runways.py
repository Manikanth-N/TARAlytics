"""Runways overlay — runway centrelines + designators from OurAirports (M3)."""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt6.QtGui import QFont

from core.basemap.overlays import OverlayLayer

_COLOR = '#e0e0e0'


class RunwaysOverlay(OverlayLayer):
    id = 'runways'
    label = 'Runways'
    default_visible = True
    z_value = -0.5              # above backdrop (-1), below airport markers (-0.4)

    def build(self, aviation, origin, bbox) -> None:
        lat0, lat1, lon0, lon1 = bbox
        runways = aviation.runways_in_bbox(lat0, lat1, lon0, lon1)
        for r in runways:
            e0, n0 = self._enu(r.le_lat, r.le_lon, origin)
            e1, n1 = self._enu(r.he_lat, r.he_lon, origin)
            line = pg.PlotDataItem(
                x=[e0, e1], y=[n0, n1],
                pen=pg.mkPen(_COLOR, width=3))
            self._add(line)
            if r.designator:
                mid = pg.TextItem(r.designator, color=_COLOR, anchor=(0.5, 0.5))
                mid.setFont(QFont('', 7))
                mid.setPos((e0 + e1) / 2.0, (n0 + n1) / 2.0)
                self._add(mid)

    def report_facts(self, track) -> list[str]:
        return []
