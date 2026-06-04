"""
Deterministic Map snapshot export (M5).

Produces a PNG of the Map view (basemap backdrop + airports/runways overlays +
altitude track + markers + scale bar + north arrow) for embedding in evidence
reports and PDFs (M6).

Determinism contract:
  * cache-only — the basemap is built synchronously from the local tile cache;
    no network is ever touched (BasemapSources.allow_network is False in Phase 1).
  * the same view renders byte-identical PNGs across repeated calls (Qt's PNG
    encoder is deterministic for identical pixels; no timestamp chunk is written).

The capture is a QWidget.grab() of the plot, so the decorations overlay (a child
of the plot) is included automatically.
"""
from __future__ import annotations
from typing import Optional

from PyQt6.QtCore import QByteArray, QBuffer
from PyQt6.QtGui import QImage


def render_map_png(map_tab, path: Optional[str] = None) -> bytes:
    """Render the Map view to deterministic PNG bytes (and optionally to `path`)."""
    map_tab.prepare_export()
    pix = map_tab.export_pixmap()
    img: QImage = pix.toImage()

    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QBuffer.OpenModeFlag.WriteOnly)
    img.save(buf, 'PNG')
    buf.close()
    data = bytes(ba)
    if path:
        with open(path, 'wb') as f:
            f.write(data)
    return data
