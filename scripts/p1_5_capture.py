"""
P1.5 capture — Unified Events, Artificial Horizon, RC Visualization, Map sync,
and the full investigation window after a one-click event selection.

    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 QT_QPA_PLATFORM=offscreen \
        python3 scripts/p1_5_capture.py
"""
import os
import sys
import time

import numpy as np
from PyQt6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.log_parser import DataFlashParser            # noqa: E402
from core import signature_verifier                    # noqa: E402
from ui.main_window import MainWindow                   # noqa: E402

OUT = 'docs/screenshots/sprint_p1_5'
NAV = {'EVENTS': 2, 'SITUATION': 3, 'MAP': 7}


def _load(w, path):
    raw = open(path, 'rb').read()
    data = DataFlashParser().parse(path)
    w._raw_bytes = raw
    w.data_ready.emit(data)
    try:
        w._app_state.set_verification(signature_verifier.full_verify(raw, None))
    except Exception:
        pass
    return data


def _grab(w, name):
    QApplication.processEvents()
    path = f'{OUT}/{name}.png'
    w.grab().save(path)
    print(f'   -> {path}')


def main():
    os.makedirs(OUT, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    w.resize(1640, 900)
    w.show()

    plan = [
        ('02', 'logs/00000002.BIN', [
            ('SITUATION', 150.0, 'window_situation_log02'),
            ('EVENTS',    150.0, 'window_events_log02'),
            ('MAP',       150.0, 'window_map_log02'),
        ]),
        ('11', 'logs/00000011.BIN', [
            ('SITUATION', 1485.2, 'window_situation_pilot_log11'),
            ('EVENTS',    1555.0, 'window_events_log11'),
        ]),
        ('12', 'logs/00000012.BIN', [
            ('SITUATION', 876.1, 'window_situation_divergence_log12'),
            ('MAP',       876.1, 'window_map_divergence_log12'),
        ]),
    ]

    for name, path, shots in plan:
        if not os.path.isfile(path):
            print(f'{name}: missing'); continue
        t0 = time.perf_counter()
        _load(w, path)
        print(f'== log {name} (parse {time.perf_counter()-t0:.1f}s) ==')
        ev = w._mod_events
        for module, t, fname in shots:
            w._on_module_requested(NAV[module])
            # drive via an event selection nearest t (the real workflow)
            if ev._times.size:
                idx = int(np.argmin(np.abs(ev._times - t)))
                ev._select_row(idx, jump=True)
            else:
                w._app_state.set_cursor_time(t)
            cur = w._app_state.cursor_time
            print(f'  [{module}] event-select → cursor {cur:.2f}s')
            _grab(w, fname)


if __name__ == '__main__':
    main()
