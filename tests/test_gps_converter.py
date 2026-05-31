"""Unit tests for core/gps_converter.py."""
import math
import pytest
import numpy as np
import pandas as pd

from core.gps_converter import lla_to_enu, gps_df_to_enu, sim2_df_to_enu, best_trajectory


# ── lla_to_enu ────────────────────────────────────────────────────────────────

class TestLlaToEnu:
    def test_origin_point_is_zero(self):
        e, n, u = lla_to_enu(-35.363, 149.165, 100.0, -35.363, 149.165, 100.0)
        assert abs(e) < 1e-6
        assert abs(n) < 1e-6
        assert abs(u) < 1e-6

    def test_altitude_difference(self):
        e, n, u = lla_to_enu(-35.363, 149.165, 150.0, -35.363, 149.165, 100.0)
        assert abs(u - 50.0) < 0.01

    def test_north_displacement(self):
        # 1 degree of latitude ≈ 111,319 m
        e, n, u = lla_to_enu(-34.363, 149.165, 0.0, -35.363, 149.165, 0.0)
        assert abs(n - 111_319) < 200  # within 200 m

    def test_east_displacement(self):
        # At -35.363 deg lat, 1 degree longitude ≈ 90,781 m
        e, n, u = lla_to_enu(-35.363, 150.165, 0.0, -35.363, 149.165, 0.0)
        assert 89_000 < e < 93_000  # sanity check on order-of-magnitude

    def test_negative_north(self):
        e, n, u = lla_to_enu(-36.363, 149.165, 0.0, -35.363, 149.165, 0.0)
        assert n < 0


# ── gps_df_to_enu ─────────────────────────────────────────────────────────────

class TestGpsDfToEnu:
    def test_basic_trajectory(self, gps_df):
        result = gps_df_to_enu(gps_df)
        assert result is not None
        assert 'east' in result
        assert 'north' in result
        assert 'up' in result
        assert 'times' in result

    def test_origin_is_first_point(self, gps_df):
        result = gps_df_to_enu(gps_df)
        assert abs(result['east'][0]) < 1.0
        assert abs(result['north'][0]) < 1.0

    def test_alt_mapped_to_up(self, gps_df):
        result = gps_df_to_enu(gps_df)
        assert result['up'][-1] > result['up'][0]  # altitude increases

    def test_none_df_returns_none(self):
        assert gps_df_to_enu(None) is None

    def test_empty_df_returns_none(self):
        empty = pd.DataFrame(columns=['TimeS', 'Lat', 'Lng', 'Alt'])
        assert gps_df_to_enu(empty) is None

    def test_stationary_returns_none(self):
        # All at the same location → range < 1 m → None
        n = 10
        df = pd.DataFrame({
            'TimeS': np.linspace(0, 10, n),
            'Lat':   np.full(n, -35.363),
            'Lng':   np.full(n, 149.165),
            'Alt':   np.full(n, 100.0),
        })
        assert gps_df_to_enu(df) is None

    def test_origin_info_in_result(self, gps_df):
        result = gps_df_to_enu(gps_df)
        assert 'origin_lat' in result
        assert 'origin_lon' in result
        assert 'origin_alt' in result


# ── sim2_df_to_enu ────────────────────────────────────────────────────────────

class TestSim2DfToEnu:
    def test_basic_trajectory(self, sim2_df):
        result = sim2_df_to_enu(sim2_df)
        assert result is not None
        assert 'east' in result
        assert 'north' in result
        assert 'up' in result

    def test_pd_to_up_inverted(self, sim2_df):
        # PD is Down → up = -PD
        result = sim2_df_to_enu(sim2_df)
        # sim2_df has PD going from 0 to -20, so up should go from 0 to +20
        assert result['up'][-1] > result['up'][0]

    def test_missing_columns_returns_none(self):
        df = pd.DataFrame({'TimeS': [1.0, 2.0], 'PN': [0.0, 1.0]})  # missing PE, PD
        assert sim2_df_to_enu(df) is None

    def test_none_returns_none(self):
        assert sim2_df_to_enu(None) is None

    def test_empty_df_returns_none(self):
        df = pd.DataFrame(columns=['TimeS', 'PN', 'PE', 'PD'])
        assert sim2_df_to_enu(df) is None

    def test_origin_is_zero(self, sim2_df):
        result = sim2_df_to_enu(sim2_df)
        assert result['origin_lat'] == 0.0
        assert result['origin_lon'] == 0.0


# ── best_trajectory ───────────────────────────────────────────────────────────

class TestBestTrajectory:
    def test_gps_preferred_over_sim2(self, gps_df, sim2_df):
        data = {'GPS': gps_df, 'SIM2': sim2_df}
        result = best_trajectory(data)
        # GPS result has non-zero origin lat/lon
        assert result is not None
        assert abs(result['origin_lat']) > 0.1

    def test_falls_back_to_sim2(self, sim2_df):
        data = {'SIM2': sim2_df}
        result = best_trajectory(data)
        assert result is not None
        assert result['origin_lat'] == 0.0

    def test_falls_back_to_sim(self):
        n = 20
        sim_df = pd.DataFrame({
            'TimeS': np.linspace(0, 20, n),
            'PN': np.linspace(0, 10, n),
            'PE': np.linspace(0, 10, n),
            'PD': np.linspace(0, -20, n),
        })
        result = best_trajectory({'SIM': sim_df})
        assert result is not None

    def test_empty_data_returns_none(self):
        assert best_trajectory({}) is None

    def test_stationary_gps_falls_back_to_sim2(self, sim2_df):
        n = 10
        bad_gps = pd.DataFrame({
            'TimeS': np.linspace(0, 10, n),
            'Lat':   np.full(n, -35.363),
            'Lng':   np.full(n, 149.165),
            'Alt':   np.full(n, 100.0),
        })
        data = {'GPS': bad_gps, 'SIM2': sim2_df}
        result = best_trajectory(data)
        # GPS returns None (stationary) so SIM2 is used → origin_lat == 0
        assert result is not None
        assert result['origin_lat'] == 0.0
