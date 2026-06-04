"""
Step 4.2 — Timeline performance measurement + screenshot capture.

Parses logs 02 / 11 / 12, builds the Timeline surface offscreen, measures the
static-lane render cost, the per-cursor-move repaint cost, and the event
clustering cost, and writes a PNG of each. Run:

    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 QT_QPA_PLATFORM=offscreen \
        python3 scripts/timeline_capture.py
"""
import os
import sys
import time

import numpy as np
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap, QPainter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.log_parser import DataFlashParser            # noqa: E402
from core import signature_verifier                    # noqa: E402
from ui.app_state import AppState                       # noqa: E402
from ui.widgets.timeline_canvas import (                # noqa: E402
    TimelineCanvas, cluster_events,
)

LOGS = [('02', 'logs/00000002.BIN'),
        ('11', 'logs/00000011.BIN'),
        ('12', 'logs/00000012.BIN')]
OUT = 'docs/screenshots/sprint_p1_step4_2'
W, H = 1320, 340


def _timeit(fn, n):
    best = float('inf')
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t0)
    return best


def main():
    os.makedirs(OUT, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    print(f"{'log':<4}{'rows':>10}{'flights':>8}{'phases':>7}{'modes':>6}"
          f"{'events':>7}{'static ms':>11}{'cursor µs':>11}{'cluster µs':>12}")
    print('-' * 86)

    for name, path in LOGS:
        if not os.path.isfile(path):
            print(f'{name}: missing {path}'); continue
        raw = open(path, 'rb').read()
        data = DataFlashParser().parse(path)
        rows = sum(len(df) for df in data.values())

        st = AppState()
        c = TimelineCanvas(st)
        c.resize(W, H)
        st.set_parsed_data(data, raw, path)
        # verification (drives the verify lane); tolerate truncated logs
        try:
            res = signature_verifier.full_verify(raw, None)
            st.set_verification(res)
        except Exception:
            pass

        # static render (full lanes -> pixmap)
        def render():
            c._static = None
            c._render_static()
        static_ms = _timeit(render, 5) * 1e3

        # per-cursor-move repaint: blit cached pixmap + cursor overlay
        c._render_static()
        target = QPixmap(c.size())
        ts = np.linspace(c._t_start, c._t_end, 200)
        i = {'k': 0}

        def move():
            c._cursor = float(ts[i['k'] % len(ts)]); i['k'] += 1
            p = QPainter(target)
            p.drawPixmap(0, 0, c._static)
            c._draw_cursor(p)
            p.end()
        cursor_us = _timeit(move, 200) * 1e6

        # event clustering cost (full-view)
        x0, x1 = c._plot_x()

        def clust():
            cluster_events(c._events, c._t_start, c._t_end, x0, x1)
        cluster_us = _timeit(clust, 20) * 1e6

        print(f'{name:<4}{rows:>10,}{len(c._flights):>8}{len(c._phases):>7}'
              f'{len(c._modes):>6}{len(c._events):>7}{static_ms:>11.2f}'
              f'{cursor_us:>11.1f}{cluster_us:>12.1f}')

        # screenshot
        c._render_static()
        shot = QPixmap(c.size())
        p = QPainter(shot)
        p.drawPixmap(0, 0, c._static)
        # park the cursor inside the first flight for a representative frame
        if c._flights:
            c._cursor = c._flights[0].start + 0.4 * c._flights[0].duration
        c._draw_cursor(p)
        p.end()
        out = f'{OUT}/timeline_log{name}.png'
        shot.save(out)
        print(f'      -> {out}')


if __name__ == '__main__':
    main()
