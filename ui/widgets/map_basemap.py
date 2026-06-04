"""
Basemap backdrop layer for the 2D Map view (M2).

Renders offline raster basemap tiles as a backdrop *beneath* the existing flight
track, at z = -1, inside the same pyqtgraph PlotWidget. The canvas stays in local
ENU metres — tiles are reprojected into ENU per-tile, so they register pixel-for-
pixel with the altitude-coloured track, markers and shared cursor (all untouched).

Design points:
  * Pure QImage/QPixmap raster path — no Chromium, no GPU requirement, renders
    headless (so it is covered by the offscreen test harness).
  * Tiles are added with ignoreBounds=True so the backdrop never affects "Fit View".
  * `best_tile()` is used so a missing high-zoom tile falls back to a coarser
    parent — the backdrop is never blank.
  * Overlay layers (airports/runways, M3) are managed separately and drawn above
    this backdrop; this class only owns the raster tiles.
"""
from __future__ import annotations
from typing import Optional

import pyqtgraph as pg
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap, QTransform
from PyQt6.QtWidgets import QGraphicsPixmapItem

from core.basemap.sources import BasemapSources
from core.basemap import projection as P

_Z_BACKDROP = -1
_MAX_TILES = 120          # hard cap on tiles drawn per refresh (bounds work)
_REFRESH_MS = 80          # coalesce pan/zoom range changes


class MapBasemap:
    """Owns the raster backdrop for a PlotWidget. One per MapTab."""

    def __init__(self, plot: pg.PlotWidget, sources: Optional[BasemapSources] = None):
        self._plot = plot
        self._vb = plot.getViewBox()
        self._sources = sources if sources is not None else BasemapSources()
        self._origin: Optional[tuple[float, float]] = None   # (lat0, lon0)
        self._items: dict[tuple[int, int, int], QGraphicsPixmapItem] = {}
        self._style = 'streets'          # 'streets' | 'minimal' | 'off'
        self._export_mode = False

        self._timer = QTimer(plot)
        self._timer.setSingleShot(True)
        self._timer.setInterval(_REFRESH_MS)
        self._timer.timeout.connect(self.refresh)
        self._vb.sigRangeChanged.connect(self._on_range)

    # -- configuration --------------------------------------------------------
    @property
    def has_data(self) -> bool:
        return self._sources.available and self._origin is not None

    def set_origin(self, lat0: float, lon0: float) -> None:
        """Set the ENU home origin (from the trajectory). (0,0) → no geo basemap."""
        if abs(lat0) < 1e-3 and abs(lon0) < 1e-3:
            self._origin = None            # SIM / non-geographic log
        else:
            self._origin = (lat0, lon0)
        self.refresh()

    def set_style(self, style: str) -> None:
        """'streets' (labels), 'minimal' (no labels) or 'off' (clear backdrop)."""
        self._style = style
        if style == 'off':
            self.clear()
        else:
            self.refresh()

    @property
    def style(self) -> str:
        return self._style

    # -- export ---------------------------------------------------------------
    def ensure_ready(self) -> None:
        """Synchronously build the backdrop for the current view (cache-only).
        Used by the deterministic exporter before grabbing the scene (M5)."""
        self._export_mode = True
        try:
            self.refresh()
        finally:
            self._export_mode = False

    # -- rendering ------------------------------------------------------------
    def _on_range(self, *_):
        if self._style == 'off' or not self.has_data:
            return
        self._timer.start()

    def refresh(self) -> None:
        if self._style == 'off' or not self.has_data:
            self.clear()
            return
        lat0, lon0 = self._origin
        (xmin, xmax), (ymin, ymax) = self._vb.viewRange()
        if xmax <= xmin or ymax <= ymin:
            return

        # view corners (ENU) → lat/lon
        lat_n, lon_w = P.enu_to_lla(xmin, ymax, lat0, lon0)
        lat_s, lon_e = P.enu_to_lla(xmax, ymin, lat0, lon0)

        px = max(self._vb.width(), 1.0)
        z = P.pick_zoom(xmax - xmin, px, lat0, max_z=self._sources.max_zoom)
        tiles = P.tiles_covering(lon_w, lat_s, lon_e, lat_n, z)
        if len(tiles) > _MAX_TILES:                 # too many → step out a zoom
            z = max(self._sources.min_zoom, z - 1)
            tiles = P.tiles_covering(lon_w, lat_s, lon_e, lat_n, z)

        wanted: set[tuple[int, int, int]] = set()
        for tx, ty in tiles[:_MAX_TILES]:
            key = self._place_tile(z, tx, ty, lat0, lon0)
            if key is not None:
                wanted.add(key)

        # drop tiles no longer in view
        for key in list(self._items):
            if key not in wanted:
                self._vb.removeItem(self._items.pop(key))

    def _place_tile(self, z, tx, ty, lat0, lon0):
        res = self._sources.best_tile(z, tx, ty, style=self._style,
                                      min_z=self._sources.min_zoom)
        if res is None:
            return None
        key = (res.z, res.x, res.y)             # may be a coarser parent
        if key in self._items:
            return key
        pix = self._decode(res.data)
        if pix is None:
            return None
        b = P.tile_bounds(res.x, res.y, res.z)
        e_w, n_n = P.lla_to_enu(b.lat_n, b.lon_w, lat0, lon0)   # NW corner
        e_e, n_s = P.lla_to_enu(b.lat_s, b.lon_e, lat0, lon0)   # SE corner
        w, h = pix.width(), pix.height()
        if w == 0 or h == 0:
            return None
        item = QGraphicsPixmapItem(pix)
        item.setZValue(_Z_BACKDROP)
        item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        # map local pixel space (0..w, 0..h, top-left = NW) into ENU
        tr = QTransform()
        tr.translate(e_w, n_n)
        tr.scale((e_e - e_w) / w, (n_s - n_n) / h)             # y scale negative
        item.setTransform(tr)
        self._vb.addItem(item, ignoreBounds=True)
        self._items[key] = item
        return key

    @staticmethod
    def _decode(data: bytes) -> Optional[QPixmap]:
        img = QImage()
        if not img.loadFromData(data):
            return None
        return QPixmap.fromImage(img)

    def clear(self) -> None:
        for item in self._items.values():
            self._vb.removeItem(item)
        self._items.clear()

    def reset(self) -> None:
        """Forget tile items after the host PlotWidget was cleared (plot.clear()
        already removed them from the scene; only drop our stale references)."""
        self._items.clear()

    def close(self) -> None:
        self.clear()
        self._sources.close()
