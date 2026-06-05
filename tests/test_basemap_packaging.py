"""M7 — bundled-asset resolution (offline-first first launch)."""
import os
import sys

import pytest

import core.basemap.assets as assets
import core.basemap.sources as sources_mod
import core.basemap.aviation as AV
from core.basemap.sources import BasemapSources
from core.basemap.aviation import AviationData
from tests.test_basemap_offline import write_pmtiles

AIRPORTS_CSV = (
    "id,ident,type,name,latitude_deg,longitude_deg,elevation_ft,iso_country\n"
    "1,YSSY,large_airport,Sydney,-33.9461,151.1772,21,AU\n")
RUNWAYS_CSV = (
    "id,airport_ref,airport_ident,length_ft,width_ft,surface,lighted,closed,"
    "le_ident,le_latitude_deg,le_longitude_deg,le_heading_degT,"
    "he_ident,he_latitude_deg,he_longitude_deg,he_heading_degT\n"
    "10,1,YSSY,12999,150,ASP,1,0,16R,-33.9329,151.1883,160,34L,-33.9594,151.1714,340\n")


class TestAssetResolution:
    def test_frozen_uses_meipass(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, '_MEIPASS', str(tmp_path), raising=False)
        assert assets.bundled_basemap_dir() == os.path.join(str(tmp_path), 'assets', 'basemap')

    def test_dev_points_at_repo_assets(self, monkeypatch):
        monkeypatch.delattr(sys, '_MEIPASS', raising=False)
        d = assets.bundled_basemap_dir()
        assert d.endswith(os.path.join('assets', 'basemap'))
        assert os.path.isfile(os.path.join(d, 'ATTRIBUTION.txt'))   # committed


class TestBundledWorldBase:
    def test_falls_back_to_bundled_when_user_has_none(self, tmp_path, monkeypatch):
        bundled = tmp_path / 'bundled'
        bundled.mkdir()
        write_pmtiles(str(bundled / 'world-base.pmtiles'), {(0, 0, 0): b'BUNDLED'})
        monkeypatch.setattr(sources_mod, 'bundled_basemap_dir', lambda: str(bundled))
        src = BasemapSources(base_dir=str(tmp_path / 'empty_user'))
        assert src.available is True
        assert src.tile(0, 0, 0) == b'BUNDLED'
        src.close()

    def test_user_base_overrides_bundled(self, tmp_path, monkeypatch):
        bundled = tmp_path / 'bundled'; bundled.mkdir()
        write_pmtiles(str(bundled / 'world-base.pmtiles'), {(0, 0, 0): b'BUNDLED'})
        user = tmp_path / 'user'; user.mkdir()
        write_pmtiles(str(user / 'world-base.pmtiles'), {(0, 0, 0): b'USER'})
        monkeypatch.setattr(sources_mod, 'bundled_basemap_dir', lambda: str(bundled))
        src = BasemapSources(base_dir=str(user))
        assert src.tile(0, 0, 0) == b'USER'
        src.close()


class TestBundledOurAirports:
    def test_falls_back_to_bundled_csvs(self, tmp_path, monkeypatch):
        bundled = tmp_path / 'bundled_oa'; bundled.mkdir()
        (bundled / 'airports.csv').write_text(AIRPORTS_CSV)
        (bundled / 'runways.csv').write_text(RUNWAYS_CSV)
        monkeypatch.setattr(AV, 'bundled_ourairports_dir', lambda: str(bundled))
        AV._CACHE.clear()
        data = AviationData.load(base_dir=str(tmp_path / 'empty_user'))
        assert data.available is True
        a, _ = data.nearest_airport(-33.9461, 151.1772)
        assert a.ident == 'YSSY'
