"""M3 — OurAirports access + airports/runways overlays."""
import os

import pytest

from core.basemap import aviation as AV
from core.basemap.aviation import AviationData


AIRPORTS_CSV = (
    "id,ident,type,name,latitude_deg,longitude_deg,elevation_ft,iso_country\n"
    "1,YSSY,large_airport,Sydney Kingsford Smith,-33.9461,151.1772,21,AU\n"
    "2,YSCN,small_airport,Camden,-34.0403,150.6872,230,AU\n"
    "3,HELI1,heliport,City Heliport,-33.95,151.20,10,AU\n"
    "4,VIDX,medium_airport,Hindon,28.7078,77.3578,700,IN\n"
)
RUNWAYS_CSV = (
    "id,airport_ref,airport_ident,length_ft,width_ft,surface,lighted,closed,"
    "le_ident,le_latitude_deg,le_longitude_deg,le_heading_degT,"
    "he_ident,he_latitude_deg,he_longitude_deg,he_heading_degT\n"
    "10,1,YSSY,12999,150,ASP,1,0,16R,-33.9329,151.1883,160,34L,-33.9594,151.1714,340\n"
    "11,2,YSCN,3000,60,ASP,0,0,06,-34.043,150.683,60,24,-34.038,150.692,240\n"
    "12,9,NOXY,1000,40,GRS,0,0,,,,,,,,\n"   # missing endpoints → skipped
)


@pytest.fixture
def av(tmp_path):
    d = tmp_path / 'ourairports'
    d.mkdir()
    (d / 'airports.csv').write_text(AIRPORTS_CSV)
    (d / 'runways.csv').write_text(RUNWAYS_CSV)
    AV._CACHE.clear()
    return AviationData.load(base_dir=str(tmp_path))


class TestAviationData:
    def test_available(self, av):
        assert av.available

    def test_airports_in_bbox(self, av):
        aps = av.airports_in_bbox(-34.2, -33.8, 150.5, 151.3)
        idents = {a.ident for a in aps}
        assert 'YSSY' in idents and 'YSCN' in idents
        assert 'VIDX' not in idents            # in India, outside bbox

    def test_runways_with_endpoints_only(self, av):
        rws = av.runways_in_bbox(-34.2, -33.8, 150.5, 151.3)
        assert any(r.designator == '16R/34L' for r in rws)
        assert all(r.designator for r in rws)  # the endpoint-less NOXY runway dropped

    def test_nearest_airport(self, av):
        a, dist = av.nearest_airport(-33.95, 151.18)
        assert a.ident == 'YSSY'
        assert dist < 5000                     # within a few km

    def test_nearest_runway(self, av):
        r, dist = av.nearest_runway(-33.94, 151.18)
        assert r.airport_ident == 'YSSY'
        assert dist >= 0

    def test_missing_files_never_raise(self, tmp_path):
        AV._CACHE.clear()
        data = AviationData.load(base_dir=str(tmp_path / 'nope'))
        assert data.available is False
        assert data.airports_in_bbox(-90, 90, -180, 180) == []
        assert data.nearest_airport(0, 0) is None


class TestOverlays:
    def test_overlays_build_into_viewbox(self, qtbot, av):
        import pyqtgraph as pg
        from core.basemap.overlays import OverlayManager
        plot = pg.PlotWidget(); qtbot.addWidget(plot)
        mgr = OverlayManager(plot)
        # Sydney home origin; bbox around YSSY+YSCN
        mgr.set_data(av, -33.9461, 151.1772,
                     (-34.2, -33.8, 150.5, 151.3))
        ap = mgr.layers['airports']
        rw = mgr.layers['runways']
        assert ap._items, 'airport markers/labels expected'
        assert rw._items, 'runway lines expected'
        # heliport excluded from airport markers
        # toggling visibility flips the items
        mgr.set_visible('airports', False)
        assert all(not it.isVisible() for it in ap._items)
        mgr.set_visible('airports', True)
        assert all(it.isVisible() for it in ap._items)

    def test_registry_is_extensible(self):
        from core.basemap.overlays import OVERLAY_REGISTRY
        ids = {cls.id for cls in OVERLAY_REGISTRY}
        assert {'airports', 'runways'} <= ids
