"""
Step 4.3 — CursorDock validation capture.

Parses logs 02 / 11 / 12 once each, parks the shared cursor at frames that
demonstrate the three diagnosis cases, prints the Pilot/Demand/Actual matrix, and
grabs a PNG of the dock for each. Run:

    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 QT_QPA_PLATFORM=offscreen \
        python3 scripts/cursor_dock_capture.py
"""
import os
import sys
import time

from PyQt6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.log_parser import DataFlashParser            # noqa: E402
from core import signature_verifier                    # noqa: E402
from ui.app_state import AppState                       # noqa: E402
from ui.widgets.cursor_dock import CursorDock           # noqa: E402

OUT = 'docs/screenshots/sprint_p1_step4_3'
H = 580

# (case label, log name, path, cursor time)
FRAMES = [
    ('pilot_maneuver',  '11', 'logs/00000011.BIN', 1485.2),
    ('stabilization',   '12', 'logs/00000012.BIN', 892.1),
    ('divergence',      '12', 'logs/00000012.BIN', 876.1),
    ('autopilot_track', '02', 'logs/00000002.BIN', 150.0),
]


def _matrix_str(dock):
    m = dock.context._matrix._cells
    out = []
    for ax in ('roll', 'pitch', 'yaw'):
        out.append(f"{ax[:1].upper()} pilot={m[(ax,'pilot')].text():>6} "
                   f"dem={m[(ax,'demand')].text():>5} act={m[(ax,'actual')].text():>5}")
    return ' | '.join(out)


def main():
    os.makedirs(OUT, exist_ok=True)
    app = QApplication.instance() or QApplication([])

    # group frames by log so each big log is parsed once
    by_log: dict = {}
    for label, name, path, t in FRAMES:
        by_log.setdefault((name, path), []).append((label, t))

    for (name, path), frames in by_log.items():
        if not os.path.isfile(path):
            print(f'{name}: missing {path}'); continue
        t0 = time.perf_counter()
        raw = open(path, 'rb').read()
        data = DataFlashParser().parse(path)
        st = AppState()
        dock = CursorDock(st)
        dock.resize(300, H)
        st.set_parsed_data(data, raw, path)
        try:
            st.set_verification(signature_verifier.full_verify(raw, None))
        except Exception:
            pass
        print(f'\n== log {name} ({len(data)} types, parse {time.perf_counter()-t0:.1f}s) ==')
        for label, t in frames:
            st.set_cursor_time(t)
            app.processEvents()
            c = dock.context._vals
            print(f'  [{label}] @ {t}s  flight={c["flight"].text()} '
                  f'phase={c["phase"].text()} mode={c["mode"].text()} '
                  f'alt={c["alt"].text()} spd={c["speed"].text()}')
            print(f'        {_matrix_str(dock)}')
            png = f'{OUT}/dock_{label}_log{name}.png'
            dock.grab().save(png)
            print(f'        -> {png}')


if __name__ == '__main__':
    main()
