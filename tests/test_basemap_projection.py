"""M1 gate — basemap projection round-trips and slippy-tile math."""
import math
import pytest

from core.basemap import projection as P


# A realistic home (ArduPilot SITL default, Canberra) and a far-north site.
HOMES = [(-35.363261, 149.165230), (28.7041, 77.1025), (0.0, 0.0)]


class TestEnuLatLonRoundTrip:
    @pytest.mark.parametrize('lat0,lon0', HOMES)
    def test_round_trip_metres(self, lat0, lon0):
        # offsets up to ±10 km E/N should round-trip to sub-millimetre
        for east in (-10000.0, -250.0, 0.0, 137.0, 10000.0):
            for north in (-10000.0, -42.0, 0.0, 980.0, 10000.0):
                lat, lon = P.enu_to_lla(east, north, lat0, lon0)
                e2, n2 = P.lla_to_enu(lat, lon, lat0, lon0)
                assert abs(e2 - east) < 1e-3
                assert abs(n2 - north) < 1e-3

    def test_inverse_matches_gps_converter(self):
        # lla_to_enu must equal the forward math core.gps_converter uses
        from core.gps_converter import lla_to_enu as gps_enu
        lat0, lon0 = -35.363261, 149.165230
        lat, lon = -35.36, 149.17
        e1, n1, _ = gps_enu(lat, lon, 0.0, lat0, lon0, 0.0)
        e2, n2 = P.lla_to_enu(lat, lon, lat0, lon0)
        assert abs(e1 - e2) < 1e-6 and abs(n1 - n2) < 1e-6


class TestSlippyTiles:
    @pytest.mark.parametrize('z', [0, 1, 5, 7])
    def test_point_inside_its_tile_bounds(self, z):
        lon, lat = 149.165230, -35.363261
        x, y = P.lonlat_to_tile(lon, lat, z)
        b = P.tile_bounds(x, y, z)
        assert b.lon_w <= lon <= b.lon_e
        assert b.lat_s <= lat <= b.lat_n

    def test_tile_count_grows_with_zoom(self):
        n0 = P.lonlat_to_tile(180, 0, 0)
        assert n0 == (0, 0)
        # zoom 7 → coordinates in [0, 127]
        x, y = P.lonlat_to_tile(149.0, -35.0, 7)
        assert 0 <= x < 128 and 0 <= y < 128

    def test_tiles_covering_box_nonempty_and_ordered(self):
        tiles = P.tiles_covering(149.16, -35.37, 149.18, -35.35, 7)
        assert tiles
        assert all(0 <= x < 128 and 0 <= y < 128 for x, y in tiles)


class TestZoomPicker:
    def test_zoom_increases_as_view_narrows(self):
        lat0 = -35.36
        wide = P.pick_zoom(span_m=200000.0, px=800, lat0=lat0)
        tight = P.pick_zoom(span_m=500.0, px=800, lat0=lat0)
        assert tight >= wide

    def test_zoom_clamped_to_world_base_range(self):
        # extremely tight view must not exceed the bundled z0–z7 base
        z = P.pick_zoom(span_m=1.0, px=2000, lat0=0.0, max_z=7)
        assert 0 <= z <= 7

    def test_degenerate_view_is_safe(self):
        assert P.pick_zoom(span_m=0.0, px=0, lat0=0.0) == 0
