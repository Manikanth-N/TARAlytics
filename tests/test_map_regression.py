"""M2 — basemap backdrop renders beneath the track without disturbing existing
Map behaviour (track, markers, cursor follow, event highlight)."""
import os

import numpy as np
import pandas as pd
import pytest
from PyQt6.QtCore import QByteArray, QBuffer
from PyQt6.QtGui import QImage, QColor

from core.basemap import projection as P
from core.basemap.sources import BasemapSources
from ui.widgets.map_basemap import MapBasemap
from tests.test_basemap_offline import write_pmtiles


def _data(n=300, dur=100.0):
    t = np.linspace(0.0, dur, n)
    lat = np.linspace(-35.363, -35.358, n)
    lon = np.linspace(149.165, 149.170, n)
    return {
        'POS': pd.DataFrame({'TimeS': t, 'RelHomeAlt': np.clip(t, 0, 40),
                             'Lat': lat, 'Lng': lon}),
        'GPS[0]': pd.DataFrame({'TimeS': t, 'Status': np.full(n, 6), 'NSats': np.full(n, 12),
                                'Spd': np.full(n, 2.0), 'Lat': lat, 'Lng': lon,
                                'Alt': np.clip(t, 0, 40)}),
        'ERR': pd.DataFrame({'TimeS': [60.0], 'Subsys': [11], 'ECode': [2]}),
    }


def _png(color='#224466'):
    img = QImage(256, 256, QImage.Format.Format_RGB32)
    img.fill(QColor(color))
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QBuffer.OpenModeFlag.WriteOnly)
    img.save(buf, 'PNG')
    return bytes(ba)


def _world_base(base_dir):
    """A world-base.pmtiles covering the test flight area, z0–z7, real PNG tiles."""
    os.makedirs(base_dir, exist_ok=True)
    tiles = {}
    png = _png()
    for z in range(0, 8):
        for x, y in P.tiles_covering(149.16, -35.37, 149.18, -35.35, z):
            tiles[(z, x, y)] = png
    write_pmtiles(os.path.join(base_dir, 'world-base.pmtiles'), tiles, max_z=7)


@pytest.fixture
def map_tab_with_base(qtbot, tmp_path):
    from ui.tab_map_view import MapTab
    _world_base(str(tmp_path / 'maps'))
    tab = MapTab()
    qtbot.addWidget(tab)
    tab.resize(800, 600)
    # inject offline test sources
    tab._basemap.close()
    tab._basemap = MapBasemap(tab._plot, sources=BasemapSources(base_dir=str(tmp_path / 'maps')))
    tab._basemap.set_style('streets')
    tab.update_data(_data())
    # force a concrete view + synchronous backdrop build
    tab._plot.setXRange(-300, 300, padding=0)
    tab._plot.setYRange(-300, 300, padding=0)
    tab._basemap.refresh()
    return tab


class TestBackdrop:
    def test_backdrop_items_inserted_at_z_minus_1(self, map_tab_with_base):
        tab = map_tab_with_base
        assert tab._basemap._items, 'expected basemap tiles to render'
        for item in tab._basemap._items.values():
            assert item.zValue() == -1

    def test_track_and_markers_unchanged(self, map_tab_with_base):
        tab = map_tab_with_base
        # trajectory + live aircraft marker still built
        assert tab._traj is not None
        assert tab._pos_item is not None

    def test_cursor_follow_still_works(self, map_tab_with_base):
        tab = map_tab_with_base
        tab.set_time(50.0)
        assert tab._cursor_alt_lbl.text().startswith('Alt @ cursor:')
        assert 'm' in tab._cursor_alt_lbl.text()

    def test_event_highlight_still_works(self, map_tab_with_base):
        tab = map_tab_with_base
        tab.highlight_event(60.0)               # must not raise; ring repositioned
        assert tab._evt_highlight is not None

    def test_basemap_off_clears_backdrop(self, map_tab_with_base):
        tab = map_tab_with_base
        tab._basemap.set_style('off')
        assert not tab._basemap._items

    def test_sim_origin_disables_backdrop(self, qtbot, tmp_path):
        from ui.tab_map_view import MapTab
        _world_base(str(tmp_path / 'maps'))
        tab = MapTab(); qtbot.addWidget(tab); tab.resize(800, 600)
        tab._basemap.close()
        tab._basemap = MapBasemap(tab._plot,
                                  sources=BasemapSources(base_dir=str(tmp_path / 'maps')))
        tab._basemap.set_origin(0.0, 0.0)       # SIM / non-geographic
        tab._basemap.refresh()
        assert not tab._basemap._items
