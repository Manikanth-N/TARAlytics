"""
Coordinate projection for the offline basemap (M1).

The Map canvas stays in **local ENU metres** (true distances, home at origin) — we
never switch it to Web-Mercator, because that would scale every on-screen distance by
~sec(latitude) and corrupt the metric axes investigators rely on. Instead the basemap
tiles are reprojected *into* ENU.

This module provides the three transforms that make that possible:

  * ENU  ↔ lat/lon         (the same tangent-plane math used by core.gps_converter)
  * lat/lon → slippy tile  (Web-Mercator z/x/y) and tile → lat/lon bounds
  * a zoom picker so an on-screen tile is ~256 px

The ENU↔lat/lon pair is the exact inverse of the formulas in gps_converter.gps_df_to_enu,
so basemap tiles register pixel-for-pixel with the flight track that view produced.
"""
from __future__ import annotations
import math
from typing import NamedTuple

# Earth radius used throughout the app (matches core.gps_converter).
_R = 6378137.0
# Web-Mercator ground resolution at the equator, zoom 0 (metres / pixel for 256px tiles).
_EQUATOR_RES = 2 * math.pi * _R / 256.0       # ≈ 156543.03


# ── ENU ↔ lat/lon (local tangent plane about a home origin) ──────────────────
def lla_to_enu(lat: float, lon: float, lat0: float, lon0: float) -> tuple[float, float]:
    """(lat, lon) degrees → (east, north) metres relative to home (lat0, lon0)."""
    east = _R * math.cos(math.radians(lat0)) * math.radians(lon - lon0)
    north = _R * math.radians(lat - lat0)
    return east, north


def enu_to_lla(east: float, north: float, lat0: float, lon0: float) -> tuple[float, float]:
    """(east, north) metres → (lat, lon) degrees — exact inverse of lla_to_enu."""
    lat = lat0 + math.degrees(north / _R)
    lon = lon0 + math.degrees(east / (_R * math.cos(math.radians(lat0))))
    return lat, lon


# ── lat/lon ↔ slippy tiles (Web-Mercator XYZ) ────────────────────────────────
class TileBounds(NamedTuple):
    lon_w: float
    lat_n: float
    lon_e: float
    lat_s: float


def lonlat_to_tile(lon: float, lat: float, z: int) -> tuple[int, int]:
    """(lon, lat) degrees → integer slippy tile (x, y) at zoom z."""
    n = 1 << z
    lat = max(min(lat, 85.05112878), -85.05112878)
    lat_rad = math.radians(lat)
    xt = int((lon + 180.0) / 360.0 * n)
    yt = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return _clamp(xt, n), _clamp(yt, n)


def tile_bounds(x: int, y: int, z: int) -> TileBounds:
    """Geographic bounds (lon_w, lat_n, lon_e, lat_s) of slippy tile (x, y, z)."""
    n = 1 << z
    lon_w = x / n * 360.0 - 180.0
    lon_e = (x + 1) / n * 360.0 - 180.0
    lat_n = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * y / n))))
    lat_s = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * (y + 1) / n))))
    return TileBounds(lon_w, lat_n, lon_e, lat_s)


def _clamp(v: int, n: int) -> int:
    return 0 if v < 0 else (n - 1 if v >= n else v)


def tiles_covering(lon_w: float, lat_s: float, lon_e: float, lat_n: float,
                   z: int) -> list[tuple[int, int]]:
    """All (x, y) tiles at zoom z intersecting the given lon/lat box."""
    x0, y0 = lonlat_to_tile(lon_w, lat_n, z)        # NW corner
    x1, y1 = lonlat_to_tile(lon_e, lat_s, z)        # SE corner
    xs = range(min(x0, x1), max(x0, x1) + 1)
    ys = range(min(y0, y1), max(y0, y1) + 1)
    return [(x, y) for x in xs for y in ys]


# ── zoom selection ───────────────────────────────────────────────────────────
def pick_zoom(span_m: float, px: float, lat0: float,
              min_z: int = 0, max_z: int = 7) -> int:
    """Choose the slippy zoom whose tile resolution best matches the screen.

    span_m  – width of the current view in metres (ENU)
    px      – width of the view in pixels
    lat0    – home latitude (Web-Mercator resolution depends on latitude)
    The bundled world base is z0–z7, so max_z defaults to 7; higher-detail
    region/bbox packs raise it.
    """
    if span_m <= 0 or px <= 0:
        return min_z
    mpp_screen = span_m / px                          # metres per screen pixel
    res0 = _EQUATOR_RES * math.cos(math.radians(lat0))
    if mpp_screen <= 0 or res0 <= 0:
        return max_z
    z = math.log2(res0 / mpp_screen)
    return int(max(min_z, min(max_z, round(z))))


def tile_resolution(z: int, lat0: float) -> float:
    """Ground resolution (metres / pixel) of a tile at zoom z, latitude lat0."""
    return _EQUATOR_RES * math.cos(math.radians(lat0)) / (1 << z)
