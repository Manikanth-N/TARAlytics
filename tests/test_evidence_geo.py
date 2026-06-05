"""M6 — geographic context (nearest airport/runway + map snapshot) in evidence."""
import os

import numpy as np
import pandas as pd
import pytest

import core.basemap.aviation as AV
from core import evidence_export as ex


AIRPORTS_CSV = (
    "id,ident,type,name,latitude_deg,longitude_deg,elevation_ft,iso_country\n"
    "1,YSSY,large_airport,Sydney Kingsford Smith,-33.9461,151.1772,21,AU\n"
)
RUNWAYS_CSV = (
    "id,airport_ref,airport_ident,length_ft,width_ft,surface,lighted,closed,"
    "le_ident,le_latitude_deg,le_longitude_deg,le_heading_degT,"
    "he_ident,he_latitude_deg,he_longitude_deg,he_heading_degT\n"
    "10,1,YSSY,12999,150,ASP,1,0,16R,-33.9329,151.1883,160,34L,-33.9594,151.1714,340\n"
)


def _data(n=200, dur=80.0):
    t = np.linspace(0.0, dur, n)
    lat = np.linspace(-33.9461, -33.940, n)        # home at YSSY
    lon = np.linspace(151.1772, 151.183, n)
    return {
        'POS': pd.DataFrame({'TimeS': t, 'RelHomeAlt': np.clip(t, 0, 60),
                             'Lat': lat, 'Lng': lon}),
        'GPS[0]': pd.DataFrame({'TimeS': t, 'Status': np.full(n, 6), 'NSats': np.full(n, 12),
                                'Spd': np.full(n, 5.0), 'Lat': lat, 'Lng': lon,
                                'Alt': np.clip(t, 0, 60)}),
    }


@pytest.fixture
def aviation_dir(tmp_path, monkeypatch):
    d = tmp_path / 'ourairports'; d.mkdir()
    (d / 'airports.csv').write_text(AIRPORTS_CSV)
    (d / 'runways.csv').write_text(RUNWAYS_CSV)
    AV._CACHE.clear()
    orig = AV.AviationData.load
    monkeypatch.setattr(AV.AviationData, 'load',
                        staticmethod(lambda base_dir=None: orig(base_dir=str(tmp_path))))
    return tmp_path


# ── pure-core rendering ──────────────────────────────────────────────────────
class TestGeoMarkdown:
    def _meta(self):
        return {'log_path': 'flight.bin', 'geo': {
            'home': {'lat': -33.9461, 'lon': 151.1772},
            'nearest_airport': {'ident': 'YSSY', 'name': 'Sydney', 'dist_m': 0.0},
            'nearest_runway': {'designator': '16R/34L', 'airport': 'YSSY', 'dist_m': 1800.0},
            'map_image': 'flight_plots/map.png'}}

    def test_geo_section_rendered(self):
        md = ex.to_markdown([], self._meta())
        assert '## Geographic Context' in md
        assert 'Nearest aerodrome:** YSSY' in md
        assert 'Nearest runway:** 16R/34L' in md
        assert '![Map snapshot](flight_plots/map.png)' in md

    def test_no_geo_no_section(self):
        md = ex.to_markdown([], {'log_path': 'x'})
        assert 'Geographic Context' not in md

    def test_json_includes_geo(self):
        import json
        rep = json.loads(ex.to_json([], self._meta()))
        assert rep['geographic_context']['nearest_airport']['ident'] == 'YSSY'


# ── UI integration ───────────────────────────────────────────────────────────
class TestEvidenceModuleGeo:
    @pytest.fixture
    def module(self, qtbot, aviation_dir):
        from ui.app_state import AppState
        from ui.modules.mod_evidence import EvidenceModule
        st = AppState()
        st.set_parsed_data(_data(), b'', '')
        mod = EvidenceModule(st); qtbot.addWidget(mod)
        return mod

    def test_geo_facts_nearest_airport_and_runway(self, module):
        geo = module._geo_facts()
        assert geo is not None
        assert geo['nearest_airport']['ident'] == 'YSSY'
        assert geo['nearest_runway']['designator'] == '16R/34L'
        assert geo['nearest_airport']['dist_m'] < 50      # home == airport

    def test_map_snapshot_renders_png(self, module, tmp_path):
        out = str(tmp_path / 'map.png')
        assert module._render_map_snapshot(out) is True
        assert os.path.isfile(out)
        with open(out, 'rb') as f:
            assert f.read(8) == b'\x89PNG\r\n\x1a\n'

    def test_full_markdown_export_has_geo_and_map(self, module, tmp_path):
        out = tmp_path / 'flight_evidence.md'
        module._app.set_cursor_time(40.0)
        module._app.capture_snapshot()
        # drive the markdown branch directly (bypass the file dialog)
        meta = {**module._app.evidence_meta(), 'geo': module._geo_facts()}
        mdir = tmp_path / 'flight_plots'; mdir.mkdir()
        assert module._render_map_snapshot(str(mdir / 'map.png'))
        meta['geo']['map_image'] = 'flight_plots/map.png'
        md = ex.to_markdown(module._app.snapshots.all(), meta, module._app.flight_report)
        out.write_text(md)
        assert '## Geographic Context' in md
        assert 'YSSY' in md and '16R/34L' in md
        assert (mdir / 'map.png').exists()
