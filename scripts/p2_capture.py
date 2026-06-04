"""
P2 capture — Evidence module + a sample exported report.

    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 QT_QPA_PLATFORM=offscreen \
        python3 scripts/p2_capture.py
"""
import os
import sys

from PyQt6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.log_parser import DataFlashParser            # noqa: E402
from core import evidence_export as ex                  # noqa: E402
from ui.main_window import MainWindow                   # noqa: E402
from ui.modules.mod_evidence import export_pdf          # noqa: E402

OUT = 'docs/screenshots/sprint_p2'
NAV_EVIDENCE, NAV_SITUATION = 8, 3


def main():
    os.makedirs(OUT, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    w = MainWindow(); w.resize(1640, 900); w.show()

    data = DataFlashParser().parse('logs/00000002.BIN')
    w._raw_bytes = b''
    w.data_ready.emit(data)
    st = w._app_state

    # capture three snapshots across phases via the real workflow
    for t, notes, status in [(135.0, 'climb-out, EKF nominal', 'REVIEWED'),
                             (150.0, 'descent / LAND mode entry', 'FLAGGED'),
                             (175.0, 'post-flight, disarmed', 'OPEN')]:
        st.set_cursor_time(t)
        st.capture_snapshot(notes=notes, status=status)
    print('captured', len(st.snapshots), 'snapshots')

    # Situation window (shows the dock with V.Speed / EKF / Pos-Div indicators)
    w._on_module_requested(NAV_SITUATION)
    st.set_cursor_time(140.0)
    app.processEvents()
    w.grab().save(f'{OUT}/window_indicators_log02.png')
    print(f'-> {OUT}/window_indicators_log02.png')

    # Evidence module window
    w._on_module_requested(NAV_EVIDENCE)
    w._mod_evidence._list.selectRow(1)
    app.processEvents()
    w.grab().save(f'{OUT}/window_evidence_log02.png')
    print(f'-> {OUT}/window_evidence_log02.png')

    # sample exports committed as reference artifacts
    meta = st.evidence_meta()
    with open(f'{OUT}/sample_evidence.md', 'w') as f:
        f.write(ex.to_markdown(st.snapshots.all(), meta))
    export_pdf(ex.to_markdown(st.snapshots.all(), meta), f'{OUT}/sample_evidence.pdf')
    with open(f'{OUT}/sample_evidence.json', 'w') as f:
        f.write(ex.to_json(st.snapshots.all(), meta))
    print(f'-> sample_evidence.md / .pdf / .json')


if __name__ == '__main__':
    main()
