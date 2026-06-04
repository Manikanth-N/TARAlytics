"""
Failure sprint — areas 5 (huge logs) & 10 (long-duration soak / memory leak).

Soak: one MainWindow, repeatedly reload a log + move the cursor + switch workspace
layouts + pop-out/redock + capture snapshots, for N cycles, watching peak RSS. A leak
shows as RSS growing roughly linearly with cycles; healthy behaviour plateaus.

    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 QT_QPA_PLATFORM=offscreen \
        python3 scripts/soak_test.py [cycles] [--huge]
"""
import os
import sys
import gc
import time
import resource

import numpy as np
import pandas as pd
from PyQt6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.log_parser import DataFlashParser            # noqa: E402
from core.flight_analytics import analyze              # noqa: E402


def _rss():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _data(seed=0, dur=120.0, n=6000):
    rng = np.random.default_rng(seed)
    t = np.linspace(0, dur, n)
    return {
        'ATT': pd.DataFrame({'TimeS': t, 'DesRoll': np.zeros(n),
                             'Roll': 10 * np.sin(t * 0.3) + rng.normal(0, 0.2, n),
                             'DesPitch': np.zeros(n), 'Pitch': 5 * np.cos(t * 0.2),
                             'DesYaw': np.full(n, 90.0), 'Yaw': np.full(n, 90.0)}),
        'RCIN': pd.DataFrame({'TimeS': t, 'C1': np.full(n, 1500.0), 'C2': np.full(n, 1500.0),
                              'C3': np.full(n, 1450.0), 'C4': np.full(n, 1500.0)}),
        'RCOU': pd.DataFrame({'TimeS': t, 'C1': np.full(n, 1550.0), 'C2': np.full(n, 1560.0),
                              'C3': np.full(n, 1545.0), 'C4': np.full(n, 1555.0)}),
        'PARM': pd.DataFrame({'Name': ['RCMAP_ROLL', 'MOT_PWM_MIN', 'MOT_PWM_MAX'],
                              'Value': [1.0, 1000.0, 2000.0]}),
        'POS': pd.DataFrame({'TimeS': t, 'RelHomeAlt': np.clip(t, 0, 30),
                             'Lat': np.linspace(-35.36, -35.355, n),
                             'Lng': np.linspace(149.16, 149.165, n)}),
        'BARO[0]': pd.DataFrame({'TimeS': t, 'Alt': np.clip(t, 0, 30), 'CRt': np.gradient(np.clip(t, 0, 30), t)}),
        'GPS[0]': pd.DataFrame({'TimeS': t, 'Status': np.full(n, 6), 'NSats': np.full(n, 12),
                                'Spd': np.full(n, 2.0), 'Lat': np.linspace(-35.36, -35.355, n),
                                'Lng': np.linspace(149.16, 149.165, n)}),
        'ARM': pd.DataFrame({'TimeS': [5.0, dur - 5], 'ArmState': [1, 0]}),
        'MODE': pd.DataFrame({'TimeS': [5.0, dur / 2], 'Mode': [0, 5]}),
        'ERR': pd.DataFrame({'TimeS': [dur * 0.6], 'Subsys': [11], 'ECode': [2]}),
    }


def soak(cycles):
    app = QApplication.instance() or QApplication([])
    from ui.main_window import MainWindow
    w = MainWindow(); w.resize(1500, 900)
    ws = w._mod_workspace
    layouts = ['Pilot Analysis', 'Accident Investigation', 'Certification']
    print(f'{"cycle":>5}{"RSS MB":>10}{"types":>7}{"verdict":>10}')
    base = None
    for c in range(1, cycles + 1):
        w.data_ready.emit(_data(seed=c))           # reload
        span = w._app_state.timeline_model.log_span()
        for tt in np.linspace(span[0], span[1], 40):
            w._app_state.set_cursor_time(float(tt))  # scrub
        ws.set_layout(layouts[c % 3])               # switch layout
        ws._popout('horizon'); ws._floating['horizon'].close()  # pop-out + redock
        w._app_state.set_cursor_time(span[0] + 0.4 * (span[1] - span[0]))
        w._app_state.capture_snapshot()
        rep = w._app_state.flight_report
        app.processEvents(); gc.collect()
        rss = _rss()
        if base is None:
            base = rss
        if c <= 3 or c % 5 == 0 or c == cycles:
            print(f'{c:>5}{rss:>10.0f}{len(w._app_state.data):>7}{rep.quality.verdict:>10}')
    growth = _rss() - base
    print(f'\nRSS base {base:.0f} MB → end {_rss():.0f} MB  (growth {growth:+.0f} MB over '
          f'{cycles} cycles, {growth/cycles:+.2f} MB/cycle)')
    print('VERDICT:', 'PLATEAU / OK' if growth / max(cycles, 1) < 3.0 else 'POSSIBLE LEAK')


def huge():
    path = 'logs/00000012.BIN'
    if not os.path.isfile(path):
        print('huge log missing'); return
    t = time.perf_counter()
    data = DataFlashParser().parse(path)
    print(f'huge parse: {time.perf_counter()-t:.1f}s  RSS {_rss():.0f}MB  types {len(data)}')
    t = time.perf_counter()
    rep = analyze(data)
    print(f'huge analyze: {time.perf_counter()-t:.1f}s  verdict {rep.quality.verdict} '
          f'findings {len(rep.findings)}  RSS {_rss():.0f}MB')


if __name__ == '__main__':
    cycles = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 30
    soak(cycles)
    if '--huge' in sys.argv:
        huge()
