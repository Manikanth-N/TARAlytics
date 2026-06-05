#!/usr/bin/env python3
"""
Build-time generator for the bundled offline basemap assets (M7).

Populates assets/basemap/ with:
  * ourairports/airports.csv, runways.csv   (OurAirports, public domain)
  * world-base.pmtiles                       (z0–z7 OSM raster base, ODbL)

Requires network access **at build time only** — the shipped application never
needs the network to review a log. Run before PyInstaller:

    python scripts/build_basemap_assets.py            # fetch everything
    python scripts/build_basemap_assets.py --check    # verify presence only

The world base is large (~150–300 MB). Provide a prebuilt archive via
BASEMAP_PMTILES_URL to download it, or build one from an OSM extract with
Planetiler + the pmtiles CLI (see README) and drop it in place.

stdlib only — no third-party dependency for the build step.
"""
from __future__ import annotations
import argparse
import os
import sys
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
_ASSETS = os.path.join(os.path.dirname(_HERE), 'assets', 'basemap')
_OURAIRPORTS = os.path.join(_ASSETS, 'ourairports')

_OURAIRPORTS_FILES = {
    'airports.csv': 'https://ourairports.com/data/airports.csv',
    'runways.csv': 'https://ourairports.com/data/runways.csv',
}
_WORLD_BASE = os.path.join(_ASSETS, 'world-base.pmtiles')


def _download(url: str, dest: str) -> None:
    print(f'  ↓ {url}\n    → {dest}')
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    req = urllib.request.Request(url, headers={'User-Agent': 'TARAlytics-build/1.0'})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, 'wb') as f:
        f.write(r.read())
    print(f'    {os.path.getsize(dest) / 1e6:.1f} MB')


def fetch_ourairports() -> None:
    print('OurAirports CSVs:')
    for name, url in _OURAIRPORTS_FILES.items():
        _download(url, os.path.join(_OURAIRPORTS, name))


def fetch_world_base() -> None:
    url = os.environ.get('BASEMAP_PMTILES_URL')
    if not url:
        print('world-base.pmtiles: no BASEMAP_PMTILES_URL set.\n'
              '  Build one from an OSM extract, e.g.:\n'
              '    java -jar planetiler.jar --download --area=planet '
              '--minzoom=0 --maxzoom=7 --output=world-base.mbtiles\n'
              '    pmtiles convert world-base.mbtiles world-base.pmtiles\n'
              f'  then place it at {_WORLD_BASE}')
        return
    print('world-base.pmtiles:')
    _download(url, _WORLD_BASE)


def check() -> int:
    missing = []
    for name in _OURAIRPORTS_FILES:
        if not os.path.isfile(os.path.join(_OURAIRPORTS, name)):
            missing.append(f'ourairports/{name}')
    if not os.path.isfile(_WORLD_BASE):
        missing.append('world-base.pmtiles')
    if not os.path.isfile(os.path.join(_ASSETS, 'ATTRIBUTION.txt')):
        missing.append('ATTRIBUTION.txt')
    if missing:
        print('MISSING basemap assets:')
        for m in missing:
            print(f'  - {m}')
        return 1
    print('All basemap assets present.')
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description='Build offline basemap assets')
    ap.add_argument('--check', action='store_true', help='verify presence only')
    ap.add_argument('--airports-only', action='store_true',
                    help='fetch OurAirports CSVs only (skip world base)')
    args = ap.parse_args()
    if args.check:
        return check()
    fetch_ourairports()
    if not args.airports_only:
        fetch_world_base()
    return check()


if __name__ == '__main__':
    sys.exit(main())
