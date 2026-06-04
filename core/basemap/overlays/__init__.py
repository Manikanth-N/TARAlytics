"""
Overlay registry for the Map basemap (M3).

Each overlay is a self-contained layer drawn above the raster backdrop and below
the flight track. The registry + manager are the extensibility seam: future layers
(power lines, railways, restricted areas, military zones, airspace) implement the
same OverlayLayer contract and append to OVERLAY_REGISTRY — the toolbar toggles and
build/clear plumbing pick them up with no change to the Map widget.

Contract (OverlayLayer):
  id              stable key (also the QSettings key + toggle id)
  label           toolbar text
  default_visible
  z_value         draw order (backdrop = -1, track = 0; overlays sit between)
  build(aviation, origin, bbox)   create ENU-placed pyqtgraph items
  set_visible(on)
  clear()
  report_facts(track)             optional DGCA report lines (M6)
"""
from __future__ import annotations

from core.basemap import projection as P


class OverlayLayer:
    """Base class. Subclasses build pyqtgraph items into the host ViewBox."""

    id: str = ''
    label: str = ''
    default_visible: bool = True
    z_value: float = -0.5

    def __init__(self, vb):
        self._vb = vb
        self._items: list = []
        self._visible = self.default_visible

    # -- to override ----------------------------------------------------------
    def build(self, aviation, origin: tuple[float, float], bbox) -> None:
        raise NotImplementedError

    def report_facts(self, track) -> list[str]:
        return []

    # -- shared ---------------------------------------------------------------
    def _add(self, item) -> None:
        item.setZValue(self.z_value)
        item.setVisible(self._visible)
        self._vb.addItem(item, ignoreBounds=True)
        self._items.append(item)

    def set_visible(self, on: bool) -> None:
        self._visible = bool(on)
        for it in self._items:
            it.setVisible(self._visible)

    def clear(self) -> None:
        for it in self._items:
            self._vb.removeItem(it)
        self._items.clear()

    @staticmethod
    def _enu(lat, lon, origin):
        return P.lla_to_enu(lat, lon, origin[0], origin[1])


class OverlayManager:
    """Owns the registered overlays for one Map view."""

    def __init__(self, plot):
        self._vb = plot.getViewBox()
        self._layers: dict[str, OverlayLayer] = {
            cls.id: cls(self._vb) for cls in OVERLAY_REGISTRY
        }

    @property
    def layers(self) -> dict[str, OverlayLayer]:
        return self._layers

    def set_data(self, aviation, lat0: float, lon0: float, bbox) -> None:
        """(Re)build every overlay for the given home origin + lat/lon bbox."""
        for layer in self._layers.values():
            layer.clear()
            if aviation is not None:
                layer.build(aviation, (lat0, lon0), bbox)

    def set_visible(self, layer_id: str, on: bool) -> None:
        layer = self._layers.get(layer_id)
        if layer is not None:
            layer.set_visible(on)

    def reset(self) -> None:
        """Forget items after the host PlotWidget was cleared (refs only)."""
        for layer in self._layers.values():
            layer._items.clear()

    def clear(self) -> None:
        for layer in self._layers.values():
            layer.clear()

    def report_facts(self, track) -> list[str]:
        facts: list[str] = []
        for layer in self._layers.values():
            facts.extend(layer.report_facts(track))
        return facts


# Imported after OverlayLayer is defined so the overlay modules can subclass it
# (resolvable circular import: OverlayLayer already exists on this module here).
from core.basemap.overlays.runways import RunwaysOverlay      # noqa: E402
from core.basemap.overlays.airports import AirportsOverlay    # noqa: E402

# Order = draw order (runways under airport markers). Future layers append here.
OVERLAY_REGISTRY: list = [RunwaysOverlay, AirportsOverlay]
