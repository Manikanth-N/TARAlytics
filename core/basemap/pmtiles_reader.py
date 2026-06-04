"""
Minimal, dependency-free PMTiles v3 reader (M1).

PMTiles is a single-file, serverless tile archive — ideal for shipping the bundled
offline world base and for drop-in region packs (no SQLite, no tile server, no
network). This reader implements exactly the slice we need:

  * parse the 127-byte v3 header
  * Hilbert (z, x, y) → tile_id  (matches go-pmtiles / pmtiles-js ZxyToId)
  * directory deserialization + binary search, following leaf directories
  * gzip / none internal+tile compression

It reads from a local file via byte-range seeks; nothing here ever touches the
network. Produced files come from the standard `pmtiles` / go-pmtiles tooling.

Spec: https://github.com/protomaps/PMTiles/blob/main/spec/v3/spec.md
"""
from __future__ import annotations
import gzip
import struct
from dataclasses import dataclass
from typing import BinaryIO, Optional

# internal_compression / tile_compression enum
_C_NONE = 1
_C_GZIP = 2

# tile_type enum (informational)
TILETYPE_MVT = 1
TILETYPE_PNG = 2
TILETYPE_JPEG = 3
TILETYPE_WEBP = 4


@dataclass
class _Entry:
    tile_id: int
    offset: int
    length: int
    run_length: int


@dataclass
class _Header:
    root_offset: int
    root_length: int
    leaf_offset: int
    tile_data_offset: int
    internal_compression: int
    tile_compression: int
    tile_type: int
    min_zoom: int
    max_zoom: int


def zxy_to_tileid(z: int, x: int, y: int) -> int:
    """(z, x, y) → PMTiles Hilbert tile id. Mirrors go-pmtiles ZxyToId exactly."""
    acc = 0
    for t in range(z):
        acc += (1 << t) * (1 << t)
    n = 1 << z
    rx = ry = 0
    d = 0
    tx, ty = x, y
    s = n >> 1
    while s > 0:
        rx = 1 if (tx & s) > 0 else 0
        ry = 1 if (ty & s) > 0 else 0
        d += s * s * ((3 * rx) ^ ry)
        # rotate (go-pmtiles rotate(s, ...): uses s-1)
        if ry == 0:
            if rx == 1:
                tx = s - 1 - tx
                ty = s - 1 - ty
            tx, ty = ty, tx
        s >>= 1
    return acc + d


def _read_uvarint(buf: bytes, pos: int) -> tuple[int, int]:
    """LEB128 unsigned varint → (value, new_pos)."""
    result = 0
    shift = 0
    while True:
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return result, pos


def _decompress(data: bytes, compression: int) -> bytes:
    if compression == _C_GZIP:
        return gzip.decompress(data)
    return data                     # _C_NONE / unknown → treat as raw


def _deserialize_directory(data: bytes) -> list[_Entry]:
    """Deserialize a PMTiles directory blob (already decompressed)."""
    pos = 0
    num, pos = _read_uvarint(data, pos)
    entries: list[_Entry] = [_Entry(0, 0, 0, 0) for _ in range(num)]

    tile_id = 0
    for i in range(num):
        delta, pos = _read_uvarint(data, pos)
        tile_id += delta
        entries[i].tile_id = tile_id
    for i in range(num):
        rl, pos = _read_uvarint(data, pos)
        entries[i].run_length = rl
    for i in range(num):
        ln, pos = _read_uvarint(data, pos)
        entries[i].length = ln
    for i in range(num):
        val, pos = _read_uvarint(data, pos)
        if i > 0 and val == 0:
            entries[i].offset = entries[i - 1].offset + entries[i - 1].length
        else:
            entries[i].offset = val - 1
    return entries


def _find_tile(entries: list[_Entry], tile_id: int) -> Optional[_Entry]:
    """Binary-search a directory. Returns a tile entry, a leaf entry, or None."""
    lo, hi = 0, len(entries) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if tile_id < entries[mid].tile_id:
            hi = mid - 1
        elif tile_id > entries[mid].tile_id:
            lo = mid + 1
        else:
            return entries[mid]
    # not an exact hit — candidate is the entry just below (hi)
    if hi >= 0:
        e = entries[hi]
        if e.run_length == 0:                       # leaf-directory pointer
            return e
        if tile_id - e.tile_id < e.run_length:      # within a run of tiles
            return e
    return None


class PMTilesReader:
    """Read raster/vector tiles from a local PMTiles v3 archive.

    Open once, query many times. Thread-safe for reads is NOT guaranteed (shares a
    file handle); the basemap layer uses one reader per source on the GUI thread.
    """

    def __init__(self, path: str):
        self.path = path
        self._f: BinaryIO = open(path, 'rb')
        self._hdr = self._read_header()
        # cache decompressed directories by (offset, length)
        self._dir_cache: dict[tuple[int, int], list[_Entry]] = {}

    # -- public ---------------------------------------------------------------
    @property
    def min_zoom(self) -> int:
        return self._hdr.min_zoom

    @property
    def max_zoom(self) -> int:
        return self._hdr.max_zoom

    @property
    def tile_type(self) -> int:
        return self._hdr.tile_type

    def get(self, z: int, x: int, y: int) -> Optional[bytes]:
        """Return decompressed tile bytes for (z, x, y), or None if absent."""
        if z < self._hdr.min_zoom or z > self._hdr.max_zoom:
            return None
        tile_id = zxy_to_tileid(z, x, y)
        dir_offset = self._hdr.root_offset
        dir_length = self._hdr.root_length
        for _ in range(4):              # root + up to 3 leaf levels (ample)
            entries = self._directory(dir_offset, dir_length)
            entry = _find_tile(entries, tile_id)
            if entry is None:
                return None
            if entry.run_length > 0:
                raw = self._read(self._hdr.tile_data_offset + entry.offset, entry.length)
                return _decompress(raw, self._hdr.tile_compression)
            # leaf directory
            dir_offset = self._hdr.leaf_offset + entry.offset
            dir_length = entry.length
        return None

    def close(self) -> None:
        try:
            self._f.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- internals ------------------------------------------------------------
    def _read(self, offset: int, length: int) -> bytes:
        self._f.seek(offset)
        return self._f.read(length)

    def _directory(self, offset: int, length: int) -> list[_Entry]:
        key = (offset, length)
        cached = self._dir_cache.get(key)
        if cached is not None:
            return cached
        raw = _decompress(self._read(offset, length), self._hdr.internal_compression)
        entries = _deserialize_directory(raw)
        self._dir_cache[key] = entries
        return entries

    def _read_header(self) -> _Header:
        self._f.seek(0)
        buf = self._f.read(127)
        if len(buf) < 127 or buf[:7] != b'PMTiles':
            raise ValueError(f'{self.path}: not a PMTiles archive')
        if buf[7] != 3:
            raise ValueError(f'{self.path}: unsupported PMTiles version {buf[7]}')
        root_offset, root_length = struct.unpack_from('<QQ', buf, 8)
        leaf_offset, _leaf_length = struct.unpack_from('<QQ', buf, 40)
        tile_data_offset, _tile_data_length = struct.unpack_from('<QQ', buf, 56)
        internal_compression = buf[97]
        tile_compression = buf[98]
        tile_type = buf[99]
        min_zoom = buf[100]
        max_zoom = buf[101]
        return _Header(
            root_offset=root_offset, root_length=root_length,
            leaf_offset=leaf_offset, tile_data_offset=tile_data_offset,
            internal_compression=internal_compression,
            tile_compression=tile_compression, tile_type=tile_type,
            min_zoom=min_zoom, max_zoom=max_zoom,
        )
