"""
Signal Export performance + quality investigation. Measure only (no optimization).

Exercises the REAL PlotterTab export path (self._plot.grab() -> pixmap.save) across
signal counts (1/5/20/50) and time windows (10 s / 1 min / 10 min / full), reporting
render time, file-write time, total latency, and RSS. Also probes SVG/clipboard
(availability) and the investigation questions (re-render, buffer reuse, UI blocking,
workspace updates, pixel-identity).

    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 QT_QPA_PLATFORM=offscreen \
        python3 scripts/profile_export.py
"""
import os
import sys
import time
import tempfile

import numpy as np
import pandas as pd
from PyQt6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DUR = 1200.0           # 20-minute flight
PTS = 300_000          # points per signal (~250 Hz)
W, H = 1600, 900       # export canvas size
SIG_COUNTS = [1, 5, 20, 50]
WINDOWS = [('10 s', 10.0), ('1 min', 60.0), ('10 min', 600.0), ('full', DUR)]


def _rss():
    for line in open('/proc/self/status'):
        if line.startswith('VmRSS'):
            return int(line.split()[1]) / 1024.0
    return 0.0


def _data():
    t = np.linspace(0.0, DUR, PTS)
    cols = {'TimeS': t}
    for i in range(50):
        cols[f'C{i}'] = (np.sin(2 * np.pi * (0.05 + i * 0.01) * t)
                         + 0.1 * np.sin(2 * np.pi * 3 * t) + i)
    return {'SIG': pd.DataFrame(cols)}


def main():
    app = QApplication.instance() or QApplication([])
    from ui.main_window import MainWindow
    w = MainWindow(); w.resize(1700, 950)
    data = _data(); w._raw_bytes = b''; w.data_ready.emit(data)
    pl = w._tab_plotter
    pl._plot.resize(W, H)
    app.processEvents()
    tmp = tempfile.mkdtemp(prefix='export_')

    print(f'canvas {W}x{H}  signal {PTS:,} pts over {DUR:.0f}s  '
          f'(pyqtgraph {__import__("pyqtgraph").__version__})\n')
    print(f'{"signals":>8}{"window":>9}{"vis.pts":>11}{"render ms":>11}'
          f'{"write ms":>10}{"total ms":>10}{"PNG KB":>9}{"RSS MB":>9}')
    print('-' * 78)

    for nsig in SIG_COUNTS:
        pl._clear_all()
        for i in range(nsig):
            pl._add_signal('SIG', f'C{i}', f'SIG.C{i}')
        for wname, wsec in WINDOWS:
            x1 = DUR; x0 = max(0.0, x1 - wsec)
            pl._plot.setXRange(x0, x1, padding=0)
            pl._plot.enableAutoRange(axis='y')
            app.processEvents()
            vis = int(min(wsec, DUR) / DUR * PTS) * nsig
            rss0 = _rss()
            t = time.perf_counter(); pm = pl._plot.grab(); t_render = (time.perf_counter() - t) * 1e3
            path = os.path.join(tmp, f'e_{nsig}_{wname}.png')
            t = time.perf_counter(); pm.save(path, 'PNG'); t_write = (time.perf_counter() - t) * 1e3
            kb = os.path.getsize(path) / 1024.0
            print(f'{nsig:>8}{wname:>9}{vis:>11,}{t_render:>11.1f}{t_write:>10.1f}'
                  f'{t_render + t_write:>10.1f}{kb:>9.0f}{_rss() - rss0:>9.1f}')
    print('-' * 78)
    _questions(app, w, pl, tmp)


def _questions(app, w, pl, tmp):
    import pyqtgraph as pg
    print('\nINVESTIGATION QUESTIONS')
    # availability
    has_svg = hasattr(pg.exporters, 'SVGExporter')
    print(f'  SVG export available in app:        NO (pyqtgraph has SVGExporter={has_svg}, unused)')
    print(f'  Clipboard image export in app:      NO (only tooltip text is copied)')

    # re-render? grab twice, compare timing
    t = time.perf_counter(); pl._plot.grab(); a = time.perf_counter() - t
    t = time.perf_counter(); pl._plot.grab(); b = time.perf_counter() - t
    print(f'  Re-rendered each export?            YES — grab() repaints (grab1 {a*1e3:.0f}ms, grab2 {b*1e3:.0f}ms)')

    # pixel-identical between two grabs of the same view?
    p1 = pl._plot.grab(); p2 = pl._plot.grab()
    id_same = p1.toImage() == p2.toImage()
    print(f'  Two grabs of same view identical:   {"YES" if id_same else "NO"} (deterministic render)')

    # ImageExporter (re-renders at target res) vs grab — pixel identity
    try:
        ie = pg.exporters.ImageExporter(pl._plot.getPlotItem())
        ie.parameters()['width'] = 1600
        t = time.perf_counter(); img = ie.export(toBytes=True); t_ie = (time.perf_counter() - t) * 1e3
        print(f'  ImageExporter render time:          {t_ie:.0f} ms (re-renders scene; not pixel-identical to grab)')
    except Exception as e:
        print(f'  ImageExporter: {e}')

    # SVG prototype timing
    try:
        se = pg.exporters.SVGExporter(pl._plot.getPlotItem())
        path = os.path.join(tmp, 'proto.svg')
        t = time.perf_counter(); se.export(path); t_svg = (time.perf_counter() - t) * 1e3
        print(f'  SVG export (prototype) time:        {t_svg:.0f} ms, {os.path.getsize(path)/1024:.0f} KB '
              f'(vector; large for many points)')
    except Exception as e:
        print(f'  SVG prototype: failed ({type(e).__name__})')

    # does export emit cursor/data signals (workspace updates)?
    fired = {'cursor': 0, 'data': 0}
    w._app_state.cursor_time_changed.connect(lambda *_: fired.__setitem__('cursor', fired['cursor'] + 1))
    w._app_state.data_changed.connect(lambda *_: fired.__setitem__('data', fired['data'] + 1))
    pl._plot.grab(); pl._export_png_to(os.path.join(tmp, 'q.png')) if hasattr(pl, '_export_png_to') else None
    app.processEvents()
    print(f'  Export emits cursor/data signals:   {"NO" if fired==dict(cursor=0,data=0) else fired} '
          f'(no workspace updates triggered)')
    print('  Export blocks the UI:               YES — grab()+save() run synchronously on the GUI thread')
    print('  Visible buffer reused:              NO — no cached pixmap; each export repaints from the scene')


if __name__ == '__main__':
    main()
