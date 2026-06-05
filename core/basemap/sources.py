"""
Offline-first basemap source resolver (M1).

Resolves a slippy tile (z, x, y) to bytes by consulting the available PMTiles
archives in priority order — highest detail first:

    bbox/   (per-flight extracts, optional)  →  packs/  (imported region packs)
                                              →  world-base.pmtiles (bundled)

Core guarantees (decisions: offline-first, never blank, no mandatory network):

  * Opening a log NEVER requires the network. If only the bundled coarse world
    base is present, tiles still resolve.
  * Missing / corrupt archives are skipped, never raised — the resolver degrades
    to whatever coarser source exists, and ultimately to None (the map then shows
    its plain canvas, exactly like today).
  * `best_tile()` walks UP the zoom pyramid so a requested high zoom with no tile
    falls back to a coarser parent tile instead of a blank — "never blank".

Network fetching (optional higher-detail downloads) is intentionally NOT wired in
M1; `allow_network` is reserved and defaults to False so the contract above holds.
"""
from __future__ import annotations
import os
import glob
from typing import NamedTuple, Optional

from core.basemap.pmtiles_reader import PMTilesReader
from core.basemap.assets import bundled_basemap_dir


def default_base_dir() -> str:
    """~/.taralytics/maps — the shared, read-mostly basemap cache."""
    return os.path.join(os.path.expanduser('~'), '.taralytics', 'maps')

# Style → bundled base archive filename.
_STYLE_BASE = {
    'streets': 'world-base.pmtiles',       # labelled
    'minimal': 'world-minimal.pmtiles',    # unlabelled (falls back to base if absent)
}


class ResolvedTile(NamedTuple):
    data: bytes
    z: int
    x: int
    y: int


class BasemapSources:
    """Priority-ordered collection of PMTiles archives, resolved offline-first."""

    def __init__(self, base_dir: Optional[str] = None, allow_network: bool = False):
        self.base_dir = base_dir or default_base_dir()
        self.allow_network = allow_network          # reserved; unused in M1
        self._readers: list[PMTilesReader] = []     # detail-first order
        self._bases: dict[str, PMTilesReader] = {}  # style → base reader
        self._open_all()

    # -- discovery ------------------------------------------------------------
    def _open_all(self) -> None:
        # bbox extracts (highest detail), then region packs
        for sub in ('bbox', 'packs'):
            d = os.path.join(self.base_dir, sub)
            for path in sorted(glob.glob(os.path.join(d, '*.pmtiles'))):
                self._open(path)
        # bundled world bases (lowest detail, always last) — prefer a user copy in
        # base_dir, else fall back to the read-only asset shipped with the app.
        bdir = bundled_basemap_dir()
        for style, fname in _STYLE_BASE.items():
            r = self._open(os.path.join(self.base_dir, fname))
            if r is None:
                r = self._open(os.path.join(bdir, fname))
            if r is not None:
                self._bases[style] = r

    def _open(self, path: str) -> Optional[PMTilesReader]:
        if not os.path.isfile(path):
            return None
        try:
            r = PMTilesReader(path)
        except Exception:
            return None                              # corrupt / wrong format → skip
        self._readers.append(r)
        return r

    # -- queries --------------------------------------------------------------
    @property
    def available(self) -> bool:
        return bool(self._readers)

    @property
    def max_zoom(self) -> int:
        return max((r.max_zoom for r in self._readers), default=0)

    @property
    def min_zoom(self) -> int:
        return min((r.min_zoom for r in self._readers), default=0)

    def _order_for_style(self, style: str) -> list[PMTilesReader]:
        """Detail sources first, then the chosen style's base (streets if missing)."""
        base = self._bases.get(style) or self._bases.get('streets')
        detail = [r for r in self._readers if r not in self._bases.values()]
        out = list(detail)
        if base is not None:
            out.append(base)
        return out

    def tile(self, z: int, x: int, y: int, style: str = 'streets') -> Optional[bytes]:
        """Exact tile bytes at (z, x, y), or None if no source has it."""
        for r in self._order_for_style(style):
            data = r.get(z, x, y)
            if data is not None:
                return data
        return None

    def best_tile(self, z: int, x: int, y: int, style: str = 'streets',
                  min_z: int = 0) -> Optional[ResolvedTile]:
        """Tile at (z, x, y); if absent, walk UP to a coarser parent tile so the
        backdrop is never blank. Returns the resolved (possibly coarser) tile."""
        zz, xx, yy = z, x, y
        while zz >= min_z:
            data = self.tile(zz, xx, yy, style)
            if data is not None:
                return ResolvedTile(data, zz, xx, yy)
            zz -= 1
            xx >>= 1
            yy >>= 1
        return None

    def close(self) -> None:
        for r in self._readers:
            r.close()
        self._readers.clear()
        self._bases.clear()
