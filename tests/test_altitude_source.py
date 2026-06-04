"""Altitude-source selection regression tests (P0).

best_trajectory() must render real vertical motion: prefer POS.RelHomeAlt → BARO.Alt
→ GPS.Alt and reject a flat altitude channel when a varying one exists. Logs 11/12
previously rendered flat because GPS.Alt was 0 while POS.RelHomeAlt carried the climb.
"""
import os
import numpy as np
import pandas as pd
import pytest

from core.gps_converter import best_trajectory, _best_altitude, _ALT_FLAT_EPS

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _t(n=200):
    return np.linspace(0.0, 100.0, n)


def _gps_df(alt, n=200):
    """A GPS frame with real horizontal motion (~500 m) and the given altitude."""
    t = _t(n)
    return pd.DataFrame({
        'TimeS': t,
        'Lat': np.linspace(-35.3600, -35.3550, n),   # ~555 m north
        'Lng': np.linspace(149.1600, 149.1650, n),
        'Alt': np.asarray(alt, dtype=float),
    })


# ── Synthetic source-selection ────────────────────────────────────────────────

class TestSourceSelection:
    def test_flat_gps_varying_relhomealt_picks_relhomealt(self):
        t = _t()
        data = {'GPS[0]': _gps_df(np.zeros(200)),                       # flat GPS.Alt
                'POS': pd.DataFrame({'TimeS': t, 'RelHomeAlt': np.clip(t - 5, 0, 30)})}
        tr = best_trajectory(data)
        assert tr['alt_source'] == 'POS.RelHomeAlt'
        assert np.ptp(tr['up']) > 25                       # real climb, not flat

    def test_baro_fallback_when_no_pos(self):
        t = _t()
        data = {'GPS[0]': _gps_df(np.zeros(200)),
                'BARO': pd.DataFrame({'TimeS': t, 'Alt': np.clip(t, 0, 20)})}
        tr = best_trajectory(data)
        assert tr['alt_source'] == 'BARO.Alt'
        assert np.ptp(tr['up']) > 15

    def test_gps_used_when_only_varying_source(self):
        data = {'GPS[0]': _gps_df(np.clip(_t(), 0, 15))}    # GPS.Alt varies
        tr = best_trajectory(data)
        assert tr['alt_source'] == 'GPS[0].Alt'
        assert np.ptp(tr['up']) > 12

    def test_sim2_only_keeps_its_altitude(self):
        t = _t()
        data = {'SIM2': pd.DataFrame({'TimeS': t,
                                      'PN': np.linspace(0, 50, 200),
                                      'PE': np.linspace(0, 30, 200),
                                      'PD': -np.clip(t, 0, 12)})}
        tr = best_trajectory(data)
        assert np.ptp(tr['up']) > 10                        # SIM2 -PD preserved
        assert tr['pos_source'] == 'SIM2'

    def test_all_flat_returns_none_from_best_altitude(self):
        t = _t()
        data = {'GPS[0]': _gps_df(np.zeros(200)),
                'POS': pd.DataFrame({'TimeS': t, 'RelHomeAlt': np.zeros(200)})}
        up, src = _best_altitude(data, t)
        assert up is None and src is None                   # no varying channel → reject all

    def test_relhomealt_kept_absolute(self):
        # A log starting 5 m above home must not be normalized down to 0.
        t = _t()
        data = {'GPS[0]': _gps_df(np.zeros(200)),
                'POS': pd.DataFrame({'TimeS': t, 'RelHomeAlt': 5.0 + np.clip(t, 0, 10)})}
        tr = best_trajectory(data)
        assert tr['up'][0] == pytest.approx(5.0, abs=0.5)


# ── Real-log validation ────────────────────────────────────────────────────────

@pytest.mark.parametrize('fname,min_climb', [
    ('00000002.BIN', 5.0),
    ('00000011.BIN', 5.0),
    ('00000012.BIN', 10.0),
])
def test_real_logs_have_nonflat_altitude(fname, min_climb):
    path = os.path.join(_ROOT, 'logs', fname)
    if not os.path.isfile(path):
        pytest.skip(f'{fname} not present')
    from core.log_parser import DataFlashParser
    tr = best_trajectory(DataFlashParser().parse(path))
    assert tr is not None
    assert np.ptp(tr['up']) >= min_climb           # no longer flat
    assert tr['alt_source']                         # source label populated


# ── P1: 2D map altitude awareness ──────────────────────────────────────────────

class TestMapAltitude:
    def _data(self):
        t = _t()
        return {'GPS[0]': _gps_df(np.zeros(200)),
                'POS': pd.DataFrame({'TimeS': t, 'RelHomeAlt': np.clip(t - 5, 0, 30)})}

    def test_legend_range_and_cursor_readout(self, qtbot):
        from ui.tab_map_view import MapTab
        m = MapTab(); qtbot.addWidget(m)
        m.update_data(self._data())
        assert m._alt_legend._has is True
        assert m._alt_legend._hi == pytest.approx(m._alt_max, abs=0.1)
        assert 'POS.RelHomeAlt' in m._src_lbl.text()
        # cursor readout follows the shared cursor
        m.set_time(float(m._traj['times'][-1]))
        assert 'm' in m._cursor_alt_lbl.text() and '—' not in m._cursor_alt_lbl.text()

    def test_altitude_colormap_blue_low_red_high(self):
        from core.colors import altitude_rgb
        r_lo, g_lo, b_lo = altitude_rgb(0.0)
        r_hi, g_hi, b_hi = altitude_rgb(1.0)
        assert b_lo > r_lo            # low = blue-ish
        assert r_hi > b_hi            # high = red-ish
