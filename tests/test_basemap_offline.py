"""M1 gate — PMTiles reader + offline-first source resolution.

Includes a tiny in-test PMTiles v3 writer so the reader/resolver are exercised
against real archive bytes (no network, no external tooling, no fixtures on disk).
"""
import gzip
import os
import struct

import pytest

from core.basemap.pmtiles_reader import PMTilesReader, zxy_to_tileid
from core.basemap.sources import BasemapSources


# ── minimal PMTiles v3 writer (single root directory, no leaves) ─────────────
def _uvarint(v: int) -> bytes:
    out = bytearray()
    while True:
        b = v & 0x7F
        v >>= 7
        if v:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)


def _serialize_directory(entries):
    """entries: list of (tile_id, offset, length, run_length) sorted by tile_id."""
    out = bytearray()
    out += _uvarint(len(entries))
    prev = 0
    for tid, _o, _l, _r in entries:
        out += _uvarint(tid - prev)
        prev = tid
    for _t, _o, _l, r in entries:
        out += _uvarint(r)
    for _t, _o, l, _r in entries:
        out += _uvarint(l)
    for i, (_t, o, _l, _r) in enumerate(entries):
        if i > 0 and o == entries[i - 1][1] + entries[i - 1][2]:
            out += _uvarint(0)
        else:
            out += _uvarint(o + 1)
    return bytes(out)


def write_pmtiles(path, tiles, internal_comp=1, tile_comp=1, min_z=0, max_z=7):
    """tiles: dict {(z, x, y): bytes}. internal/tile comp: 1 none, 2 gzip."""
    items = sorted(tiles.items(), key=lambda kv: zxy_to_tileid(*kv[0]))
    blob = bytearray()
    entries = []
    for (z, x, y), data in items:
        payload = gzip.compress(data) if tile_comp == 2 else data
        entries.append((zxy_to_tileid(z, x, y), len(blob), len(payload), 1))
        blob += payload

    directory = _serialize_directory(entries)
    if internal_comp == 2:
        directory = gzip.compress(directory)

    root_offset = 127
    root_length = len(directory)
    tile_data_offset = root_offset + root_length
    tile_data_length = len(blob)

    hdr = bytearray(127)
    hdr[0:7] = b'PMTiles'
    hdr[7] = 3
    struct.pack_into('<QQ', hdr, 8, root_offset, root_length)
    struct.pack_into('<QQ', hdr, 24, 0, 0)                       # metadata
    struct.pack_into('<QQ', hdr, 40, 0, 0)                       # leaf dirs
    struct.pack_into('<QQ', hdr, 56, tile_data_offset, tile_data_length)
    struct.pack_into('<QQQ', hdr, 72, len(entries), len(entries), len(entries))
    hdr[96] = 1                                                  # clustered
    hdr[97] = internal_comp
    hdr[98] = tile_comp
    hdr[99] = 2                                                  # tile_type PNG
    hdr[100] = min_z
    hdr[101] = max_z

    with open(path, 'wb') as f:
        f.write(hdr)
        f.write(directory)
        f.write(blob)
    return path


# ── reader ───────────────────────────────────────────────────────────────────
class TestReader:
    @pytest.mark.parametrize('ic,tc', [(1, 1), (2, 1), (1, 2), (2, 2)])
    def test_round_trip_tiles(self, tmp_path, ic, tc):
        tiles = {(0, 0, 0): b'BASE', (7, 100, 60): b'PNGDATA-1', (5, 3, 9): b'xy'}
        p = write_pmtiles(str(tmp_path / 'a.pmtiles'), tiles,
                          internal_comp=ic, tile_comp=tc)
        with PMTilesReader(p) as r:
            assert r.get(0, 0, 0) == b'BASE'
            assert r.get(7, 100, 60) == b'PNGDATA-1'
            assert r.get(5, 3, 9) == b'xy'
            assert r.get(7, 0, 0) is None              # absent tile
            assert r.get(9, 0, 0) is None              # out of zoom range

    def test_rejects_non_pmtiles(self, tmp_path):
        p = tmp_path / 'bad.pmtiles'
        p.write_bytes(b'not a pmtiles file at all............................')
        with pytest.raises(ValueError):
            PMTilesReader(str(p))


# ── offline-first resolver ───────────────────────────────────────────────────
class TestSourcesOfflineFirst:
    def _make_base(self, base_dir, tiles=None):
        os.makedirs(base_dir, exist_ok=True)
        write_pmtiles(os.path.join(base_dir, 'world-base.pmtiles'),
                      tiles or {(0, 0, 0): b'WORLD'})

    def test_no_data_never_raises_and_returns_none(self, tmp_path):
        src = BasemapSources(base_dir=str(tmp_path / 'empty'))
        assert src.available is False
        assert src.tile(0, 0, 0) is None
        assert src.best_tile(7, 100, 60) is None       # never blank → still no crash
        src.close()

    def test_world_base_resolves_offline(self, tmp_path):
        bd = str(tmp_path / 'maps')
        self._make_base(bd, {(0, 0, 0): b'WORLD', (7, 100, 60): b'DETAIL'})
        src = BasemapSources(base_dir=bd)
        assert src.available is True
        assert src.tile(0, 0, 0) == b'WORLD'
        src.close()

    def test_best_tile_walks_up_to_avoid_blank(self, tmp_path):
        bd = str(tmp_path / 'maps')
        # only the z0 world tile exists; a z7 request must fall back to it
        self._make_base(bd, {(0, 0, 0): b"WORLD"})
        src = BasemapSources(base_dir=bd)
        res = src.best_tile(7, 100, 60)
        assert res is not None and res.data == b'WORLD' and res.z == 0
        src.close()

    def test_bbox_pack_takes_priority_over_world_base(self, tmp_path):
        bd = str(tmp_path / 'maps')
        self._make_base(bd, {(7, 100, 60): b"COARSE"})
        os.makedirs(os.path.join(bd, 'bbox'))
        write_pmtiles(os.path.join(bd, 'bbox', 'flight.pmtiles'),
                      {(7, 100, 60): b'HIRES'})
        src = BasemapSources(base_dir=bd)
        assert src.tile(7, 100, 60) == b'HIRES'        # detail source wins
        src.close()

    def test_corrupt_archive_is_skipped_not_fatal(self, tmp_path):
        bd = str(tmp_path / 'maps')
        os.makedirs(os.path.join(bd, 'packs'))
        (open(os.path.join(bd, 'packs', 'broken.pmtiles'), 'wb')
         .write(b'garbage-not-pmtiles'))
        self._make_base(bd, {(0, 0, 0): b"WORLD"})
        src = BasemapSources(base_dir=bd)                # must not raise
        assert src.tile(0, 0, 0) == b'WORLD'
        src.close()
