"""Multi-instance isolation regression tests.

Multi-instance = multi-process (main() builds one MainWindow). The worst case for
isolation is two MainWindows in ONE process — they share the process-global
QThreadPool, QSettings, pyqtgraph config and module globals. If those are isolated,
separate processes trivially are. These tests pin that isolation.
"""
import numpy as np
import pandas as pd
import pytest


def _data(roll_amp=1.0, dur=100.0):
    t = np.linspace(0, dur, 2000)
    return {
        'ATT': pd.DataFrame({'TimeS': t, 'DesRoll': np.zeros(2000), 'Roll': roll_amp * np.sin(t),
                             'DesPitch': np.zeros(2000), 'Pitch': np.zeros(2000),
                             'DesYaw': np.full(2000, 90.0), 'Yaw': np.full(2000, 90.0)}),
        'RCIN': pd.DataFrame({'TimeS': t, 'C1': np.full(2000, 1500.0)}),
        'RCOU': pd.DataFrame({'TimeS': t, 'C1': np.full(2000, 1500.0)}),
        'PARM': pd.DataFrame({'Name': ['RCMAP_ROLL'], 'Value': [1.0]}),
        'POS': pd.DataFrame({'TimeS': t, 'RelHomeAlt': np.clip(t, 0, 30),
                             'Lat': np.linspace(-35.36, -35.35, 2000),
                             'Lng': np.linspace(149.16, 149.17, 2000)}),
        'GPS[0]': pd.DataFrame({'TimeS': t, 'Status': np.full(2000, 6), 'NSats': np.full(2000, 12),
                                'Spd': np.full(2000, 2.0), 'Lat': np.linspace(-35.36, -35.35, 2000),
                                'Lng': np.linspace(149.16, 149.17, 2000)}),
        'ARM': pd.DataFrame({'TimeS': [5.0, dur - 5], 'ArmState': [1, 0]}),
        'MODE': pd.DataFrame({'TimeS': [5.0], 'Mode': [5]}),
    }


@pytest.fixture
def two_windows(qtbot):
    from ui.main_window import MainWindow
    a = MainWindow(); b = MainWindow()
    qtbot.addWidget(a); qtbot.addWidget(b)
    a.data_ready.emit(_data(roll_amp=1.0, dur=100.0))
    b.data_ready.emit(_data(roll_amp=20.0, dur=500.0))
    return a, b


class TestInstanceIsolation:
    def test_distinct_appstate_and_widgets(self, two_windows):
        a, b = two_windows
        assert a._app_state is not b._app_state
        assert a._mod_workspace is not b._mod_workspace
        assert a._cursor_dock is not b._cursor_dock
        assert a._transport is not b._transport

    def test_cursor_isolated(self, two_windows):
        a, b = two_windows
        a._app_state.set_cursor_time(40.0)
        assert a._app_state.cursor_time == 40.0
        assert b._app_state.cursor_time == 0.0          # A's cursor never touches B

    def test_replay_isolated(self, two_windows):
        a, b = two_windows
        a._transport.toggle_play(); a._transport._tick()
        assert a._app_state.cursor_time > 0.0
        assert b._app_state.cursor_time == 0.0          # A's replay never moves B

    def test_snapshots_isolated(self, two_windows):
        a, b = two_windows
        a._app_state.set_cursor_time(50.0); a._app_state.capture_snapshot()
        assert len(a._app_state.snapshots) == 1
        assert len(b._app_state.snapshots) == 0         # A's snapshot never in B

    def test_data_and_analytics_isolated(self, two_windows):
        a, b = two_windows
        assert a._app_state.data is not b._app_state.data
        assert a._app_state.timeline_model.log_span()[1] == pytest.approx(100.0, abs=1)
        assert b._app_state.timeline_model.log_span()[1] == pytest.approx(500.0, abs=1)
        assert a._app_state.flight_report is not b._app_state.flight_report

    def test_context_dock_isolated(self, two_windows):
        a, b = two_windows
        a._app_state.set_cursor_time(40.0)
        # A's dock shows 40 s; B's dock shows 0
        assert a._cursor_dock.context._vals['time'].text() == '40.00 s'
        assert b._cursor_dock.context._vals['time'].text() == '0.00 s'

    def test_reload_in_one_window_does_not_touch_other(self, two_windows):
        a, b = two_windows
        b._app_state.set_cursor_time(120.0); b._app_state.capture_snapshot()
        a.data_ready.emit(_data(dur=300.0))             # reload A
        assert a._app_state.cursor_time == 0.0          # A reset
        assert b._app_state.cursor_time == 120.0        # B untouched
        assert len(b._app_state.snapshots) == 1         # B's snapshot survives


class TestNoSharedModuleState:
    def test_parser_output_is_local_per_call(self):
        # two parses of different bytes produce independent dicts (no shared buffer)
        from core.log_parser import DataFlashParser
        import os
        open('/tmp/_iso1.bin', 'wb').write(os.urandom(2000))
        open('/tmp/_iso2.bin', 'wb').write(os.urandom(4000))
        r1 = DataFlashParser().parse('/tmp/_iso1.bin')
        r2 = DataFlashParser().parse('/tmp/_iso2.bin')
        assert r1 is not r2 and isinstance(r1, dict) and isinstance(r2, dict)

    def test_appstate_has_no_class_level_mutable_state(self):
        from ui.app_state import AppState
        a, b = AppState(), AppState()
        a.set_cursor_time(5.0)
        assert b.cursor_time == 0.0                     # no shared class attribute
        assert a._snapshots is not b._snapshots
