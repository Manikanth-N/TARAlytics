"""M5 — deterministic, cache-only Map PNG export."""
import numpy as np
import pandas as pd
import pytest

from core.basemap import projection as P
from core.basemap.sources import BasemapSources
from ui.widgets.map_basemap import MapBasemap
from ui.map_export import render_map_png
from tests.test_basemap_offline import write_pmtiles
from tests.test_map_regression import _png, _world_base, _data


@pytest.fixture
def exportable_tab(qtbot, tmp_path):
    from ui.tab_map_view import MapTab
    _world_base(str(tmp_path / 'maps'))
    tab = MapTab(); qtbot.addWidget(tab); tab.resize(700, 520)
    tab._basemap.close()
    tab._basemap = MapBasemap(
        tab._plot, sources=BasemapSources(base_dir=str(tmp_path / 'maps')))
    tab._basemap.set_style('streets')
    tab.update_data(_data())
    tab._plot.setXRange(-400, 400, padding=0)
    tab._plot.setYRange(-400, 400, padding=0)
    tab.show(); qtbot.waitExposed(tab)
    return tab


class TestDeterministicExport:
    def test_export_returns_png_bytes(self, exportable_tab):
        data = render_map_png(exportable_tab)
        assert data[:8] == b'\x89PNG\r\n\x1a\n'        # PNG magic
        assert len(data) > 1000

    def test_repeated_export_byte_identical(self, exportable_tab):
        a = render_map_png(exportable_tab)
        b = render_map_png(exportable_tab)
        assert a == b                                   # deterministic

    def test_writes_to_path(self, exportable_tab, tmp_path):
        out = tmp_path / 'snap.png'
        data = render_map_png(exportable_tab, path=str(out))
        assert out.exists()
        assert out.read_bytes() == data

    def test_export_is_cache_only_no_network(self, exportable_tab):
        # Phase 1 sources never enable network — the export contract relies on it
        assert exportable_tab._basemap._sources.allow_network is False
