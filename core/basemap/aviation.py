"""
OurAirports data access for the Airports/Runways overlays and DGCA report facts (M3).

OurAirports (https://ourairports.com/data/, public domain) is the authoritative
source for aerodromes and runways — far more reliable than OSM aeroway tags. We
bundle the two CSVs (airports.csv, runways.csv) and expose:

  * airports/runways within a lat/lon bbox      → overlay drawing
  * nearest aerodrome / nearest runway to a point → evidence (M6)

Offline-first: if the CSVs are absent or malformed, every call returns empty /
None and nothing raises — the overlays simply draw nothing, the map still works.
"""
from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from core.basemap import projection as P
from core.basemap.sources import default_base_dir


@dataclass(frozen=True)
class Airport:
    ident: str
    name: str
    lat: float
    lon: float
    kind: str
    elevation_ft: Optional[float]


@dataclass(frozen=True)
class Runway:
    airport_ident: str
    designator: str          # e.g. "10/28"
    le_lat: float
    le_lon: float
    he_lat: float
    he_lon: float
    surface: str
    length_ft: Optional[float]


def _ourairports_dir(base_dir: Optional[str]) -> str:
    return os.path.join(base_dir or default_base_dir(), 'ourairports')


# cache parsed frames by directory (read-mostly, shared)
_CACHE: dict[str, 'AviationData'] = {}


class AviationData:
    """Parsed, bbox-queryable OurAirports tables. Use AviationData.load()."""

    def __init__(self, airports: pd.DataFrame, runways: pd.DataFrame):
        self._ap = airports
        self._rw = runways

    # -- loading --------------------------------------------------------------
    @classmethod
    def load(cls, base_dir: Optional[str] = None) -> 'AviationData':
        d = _ourairports_dir(base_dir)
        cached = _CACHE.get(d)
        if cached is not None:
            return cached
        ap = cls._read_csv(os.path.join(d, 'airports.csv'),
                           ['ident', 'name', 'latitude_deg', 'longitude_deg',
                            'type', 'elevation_ft'])
        rw = cls._read_csv(os.path.join(d, 'runways.csv'),
                           ['airport_ident', 'le_ident', 'he_ident',
                            'le_latitude_deg', 'le_longitude_deg',
                            'he_latitude_deg', 'he_longitude_deg',
                            'surface', 'length_ft'])
        inst = cls(ap, rw)
        _CACHE[d] = inst
        return inst

    @staticmethod
    def _read_csv(path: str, cols: list[str]) -> pd.DataFrame:
        if not os.path.isfile(path):
            return pd.DataFrame(columns=cols)
        try:
            df = pd.read_csv(path, usecols=lambda c: c in cols, low_memory=False)
        except Exception:
            return pd.DataFrame(columns=cols)
        for c in cols:
            if c not in df.columns:
                df[c] = np.nan
        return df

    @property
    def available(self) -> bool:
        return not self._ap.empty

    # -- bbox queries ---------------------------------------------------------
    def airports_in_bbox(self, lat0, lat1, lon0, lon1) -> list[Airport]:
        df = self._ap
        if df.empty:
            return []
        la, lo = df['latitude_deg'], df['longitude_deg']
        m = (la >= min(lat0, lat1)) & (la <= max(lat0, lat1)) & \
            (lo >= min(lon0, lon1)) & (lo <= max(lon0, lon1))
        out = []
        for _, r in df[m].iterrows():
            if not (np.isfinite(r['latitude_deg']) and np.isfinite(r['longitude_deg'])):
                continue
            out.append(Airport(
                ident=str(r.get('ident', '') or ''),
                name=str(r.get('name', '') or ''),
                lat=float(r['latitude_deg']), lon=float(r['longitude_deg']),
                kind=str(r.get('type', '') or ''),
                elevation_ft=_f(r.get('elevation_ft'))))
        return out

    def runways_in_bbox(self, lat0, lat1, lon0, lon1) -> list[Runway]:
        df = self._rw
        if df.empty:
            return []
        la = df['le_latitude_deg']
        lo = df['le_longitude_deg']
        m = (la >= min(lat0, lat1)) & (la <= max(lat0, lat1)) & \
            (lo >= min(lon0, lon1)) & (lo <= max(lon0, lon1))
        out = []
        for _, r in df[m].iterrows():
            le_lat, le_lon = _f(r.get('le_latitude_deg')), _f(r.get('le_longitude_deg'))
            he_lat, he_lon = _f(r.get('he_latitude_deg')), _f(r.get('he_longitude_deg'))
            if None in (le_lat, le_lon, he_lat, he_lon):
                continue
            le = str(r.get('le_ident', '') or '')
            he = str(r.get('he_ident', '') or '')
            out.append(Runway(
                airport_ident=str(r.get('airport_ident', '') or ''),
                designator=f'{le}/{he}' if le or he else '',
                le_lat=le_lat, le_lon=le_lon, he_lat=he_lat, he_lon=he_lon,
                surface=str(r.get('surface', '') or ''),
                length_ft=_f(r.get('length_ft'))))
        return out

    # -- nearest (for evidence, M6) ------------------------------------------
    def nearest_airport(self, lat, lon) -> Optional[tuple[Airport, float]]:
        best = None
        for a in self.airports_in_bbox(lat - 1.0, lat + 1.0, lon - 1.0, lon + 1.0):
            d = _dist_m(lat, lon, a.lat, a.lon)
            if best is None or d < best[1]:
                best = (a, d)
        return best

    def nearest_runway(self, lat, lon) -> Optional[tuple[Runway, float]]:
        best = None
        for r in self.runways_in_bbox(lat - 1.0, lat + 1.0, lon - 1.0, lon + 1.0):
            d = min(_dist_m(lat, lon, r.le_lat, r.le_lon),
                    _dist_m(lat, lon, r.he_lat, r.he_lon))
            if best is None or d < best[1]:
                best = (r, d)
        return best


def _f(v) -> Optional[float]:
    try:
        f = float(v)
        return f if np.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _dist_m(lat0, lon0, lat1, lon1) -> float:
    e, n = P.lla_to_enu(lat1, lon1, lat0, lon0)
    return float(np.hypot(e, n))
