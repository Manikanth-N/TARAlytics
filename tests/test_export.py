"""Signal export tests (P0/P1): downsampling, in-plot legend, light export theme,
DPI scaling, clipboard image."""
import numpy as np
import pandas as pd
import pytest


def _data(nsig=20, pts=20000, dur=1200.0):
    t = np.linspace(0, dur, pts)
    cols = {'TimeS': t}
    for i in range(nsig):
        cols[f'C{i}'] = np.sin(t * (0.05 + i * 0.01)) + i
    return {'SIG': pd.DataFrame(cols)}


@pytest.fixture
def plotter(qtbot):
    from ui.main_window import MainWindow
    w = MainWindow(); qtbot.addWidget(w)
    w._raw_bytes = b''
    w.data_ready.emit(_data())
    pl = w._tab_plotter
    pl._plot.resize(1200, 700)
    pl._clear_all()
    for i in range(20):
        pl._add_signal('SIG', f'C{i}', f'SIG.C{i}')
    return w, pl


class TestDownsampling:
    def test_downsampling_and_clip_enabled(self, plotter):
        w, pl = plotter
        curve = pl._active_sigs['SIG.C0']['curve']
        assert curve.opts['autoDownsample'] is True
        assert curve.opts['downsampleMethod'] == 'peak'
        assert curve.opts['clipToView'] is True

    def test_no_data_loss_in_values(self, plotter):
        # downsampling is render-only; the stored signal arrays are full-resolution
        w, pl = plotter
        sig = pl._active_sigs['SIG.C0']
        assert len(sig['values']) == 20000


class TestLegend:
    def test_legend_populated_and_hidden_live(self, plotter):
        w, pl = plotter
        assert len(pl._legend.items) == 20      # one per signal
        assert pl._legend.isVisible() is False  # hidden during live use

    def test_legend_updates_on_remove_and_clear(self, plotter):
        w, pl = plotter
        pl._remove_signal('SIG.C0')
        assert len(pl._legend.items) == 19
        pl._clear_all()
        assert len(pl._legend.items) == 0


class TestExportTheme:
    def test_export_pixmap_light_bg_and_restore(self, plotter):
        w, pl = plotter
        pm = pl.render_export_pixmap(scale=1.0, light=True)
        assert not pm.isNull()
        c = pm.toImage().pixelColor(3, 3)
        assert (c.red(), c.green(), c.blue()) == (255, 255, 255)   # white bg
        # legend hidden again + live dark theme restored
        assert pl._legend.isVisible() is False
        assert pl._plot.backgroundBrush().color().name() == '#1e1e2e'

    def test_dpi_scaling(self, plotter):
        w, pl = plotter
        base = pl.render_export_pixmap(scale=1.0)
        x2 = pl.render_export_pixmap(scale=2.0)
        x4 = pl.render_export_pixmap(scale=4.0)
        assert x2.width() == pytest.approx(base.width() * 2, abs=2)
        assert x4.width() == pytest.approx(base.width() * 4, abs=4)

    def test_export_includes_legend(self, plotter):
        # legend must be visible during the export render (self-describing image)
        w, pl = plotter
        seen = {}
        orig = pl._legend.setVisible
        pl._legend.setVisible = lambda v, _o=orig, _s=seen: (_s.__setitem__('on', _s.get('on') or v), _o(v))[1]
        pl.render_export_pixmap(scale=1.0, light=True)
        assert seen.get('on') is True


class TestClipboard:
    def test_copy_to_clipboard(self, plotter):
        from PyQt6.QtWidgets import QApplication
        w, pl = plotter
        pl._copy_to_clipboard()
        assert not QApplication.clipboard().pixmap().isNull()

    def test_dpi_selector_default_2x(self, plotter):
        w, pl = plotter
        assert pl._export_scale() == 2.0
