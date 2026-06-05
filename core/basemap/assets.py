"""
Bundled basemap asset resolution (M7).

The world base (world-base.pmtiles, z0–z7) and OurAirports CSVs ship *inside* the
application (PyInstaller bundle / repo), so the map works offline on first launch
with no user download. User-imported packs and per-flight extracts live separately
in ~/.taralytics/maps and take priority over these read-only bundled assets.

Resolves to:
  * frozen (PyInstaller):  <sys._MEIPASS>/assets/basemap
  * dev / source checkout: <repo>/assets/basemap
"""
from __future__ import annotations
import os
import sys


def bundled_basemap_dir() -> str:
    """Directory holding the shipped world-base.pmtiles + ourairports/ + attribution."""
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        return os.path.join(meipass, 'assets', 'basemap')
    # core/basemap/assets.py → core/basemap → core → <repo>
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(repo, 'assets', 'basemap')


def bundled_world_base(fname: str = 'world-base.pmtiles') -> str:
    return os.path.join(bundled_basemap_dir(), fname)


def bundled_ourairports_dir() -> str:
    return os.path.join(bundled_basemap_dir(), 'ourairports')
