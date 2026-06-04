"""M4 — metric scale bar + north arrow, including capture in a grab() (export path)."""
import numpy as np
import pandas as pd
import pytest


def _data(n=200, dur=80.0):
    t = np.linspace(0.0, dur, n)
    lat = np.linspace(-35.363, -35.355, n)
    lon = np.linspace(149.165, 149.175, n)
    return {
        'POS': pd.DataFrame({'TimeS': t, 'RelHomeAlt': np.clip(t, 0, 40),
                             'Lat': lat, 'Lng': lon}),
        'GPS[0]': pd.DataFrame({'TimeS': t, 'Status': np.full(n, 6), 'NSats': np.full(n, 12),
                                'Spd': np.full(n, 5.0), 'Lat': lat, 'Lng': lon,
                                'Alt': np.clip(t, 0, 40)}),
    }


class TestNiceLength:
    @pytest.mark.parametrize('target,expect', [
        (1.0, 1.0), (1.5, 2.0), (3.0, 5.0), (7.0, 10.0),
        (42.0, 50.0), (130.0, 200.0), (900.0, 1000.0), (1300.0, 2000.0)])
    def test_snaps_to_1_2_5(self, target, expect):
        from ui.widgets.map_decorations import MapDecorations
        assert MapDecorations._nice_length(target) == expect

    def test_fmt_km(self):
        from ui.widgets.map_decorations import MapDecorations
        assert MapDecorations._fmt(500) == '500 m'
        assert MapDecorations._fmt(2000) == '2 km'


class TestDecorations:
    @pytest.fixture
    def tab(self, qtbot):
        from ui.tab_map_view import MapTab
        t = MapTab(); qtbot.addWidget(t); t.resize(800, 600)
        t.update_data(_data())
        t._plot.setXRange(-500, 500, padding=0)
        t._plot.setYRange(-500, 500, padding=0)
        t.show(); qtbot.waitExposed(t)
        return t

    def test_decorations_exist_and_enabled(self, tab):
        assert tab._decorations is not None
        assert tab._decorations._enabled

    def test_metres_per_pixel_positive(self, tab):
        assert tab._decorations._metres_per_pixel() > 0

    def test_paints_without_error(self, tab):
        tab._decorations.repaint()              # must not raise

    def test_present_in_grab_export(self, tab):
        # the decorations are a child of the plot → captured by grab()
        pix = tab._plot.grab()
        assert pix.width() > 0 and pix.height() > 0
        # overlay geometry tracks the plot
        assert tab._decorations.width() == tab._plot.width()

    def test_disable_hides(self, tab):
        tab._decorations.set_enabled(False)
        assert not tab._decorations.isVisible()
