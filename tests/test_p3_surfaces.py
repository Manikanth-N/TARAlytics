"""P3 surface-improvement tests: Replay→shared-cursor, Horizon 10 s history,
and (added later) Plotter search / presets / event-linking."""
import numpy as np
import pandas as pd
import pytest


def _data(n=400, dur=100.0):
    t = np.linspace(0.0, dur, n)
    roll = 15.0 * np.sin(2 * np.pi * 0.1 * t)      # slow roll oscillation for history
    return {
        'ATT': pd.DataFrame({'TimeS': t, 'DesRoll': np.zeros(n), 'Roll': roll,
                             'DesPitch': np.zeros(n), 'Pitch': roll * 0.3,
                             'DesYaw': np.full(n, 90.0), 'Yaw': np.full(n, 90.0)}),
        'RCIN': pd.DataFrame({'TimeS': t, 'C1': np.full(n, 1500.0), 'C2': np.full(n, 1500.0),
                              'C3': np.full(n, 1450.0), 'C4': np.full(n, 1500.0)}),
        'RCOU': pd.DataFrame({'TimeS': t, 'C1': np.full(n, 1550.0), 'C2': np.full(n, 1550.0),
                              'C3': np.full(n, 1550.0), 'C4': np.full(n, 1550.0)}),
        'PARM': pd.DataFrame({'Name': ['RCMAP_ROLL'], 'Value': [1.0]}),
        'POS': pd.DataFrame({'TimeS': t, 'RelHomeAlt': np.clip(t, 0, 40)}),
        'GPS[0]': pd.DataFrame({'TimeS': t, 'Status': np.full(n, 6), 'NSats': np.full(n, 12),
                                'Spd': np.full(n, 2.0), 'Alt': np.clip(t, 0, 40),
                                'Lat': np.linspace(-35.36, -35.355, n),
                                'Lng': np.linspace(149.16, 149.165, n)}),
        'ARM': pd.DataFrame({'TimeS': [5.0, 95.0], 'ArmState': [1, 0]}),
        'MODE': pd.DataFrame({'TimeS': [5.0], 'Mode': [5]}),
    }


class TestReplayDrivesCursor:
    def test_replay_time_advances_shared_cursor(self, qtbot):
        from ui.main_window import MainWindow
        w = MainWindow(); qtbot.addWidget(w)
        w.data_ready.emit(_data())
        w._tab_3d._replay.set_range(0.0, 100.0)
        seen = []
        w._app_state.cursor_time_changed.connect(lambda t: seen.append(t))
        w._tab_3d._replay.time_changed.emit(42.0)        # a playback tick
        assert w._app_state.cursor_time == pytest.approx(42.0)
        assert seen and seen[-1] == pytest.approx(42.0)

    def test_playback_updates_other_surfaces(self, qtbot):
        from ui.main_window import MainWindow
        w = MainWindow(); qtbot.addWidget(w)
        w.data_ready.emit(_data())
        w._tab_3d._replay.set_range(0.0, 100.0)
        w._tab_3d._replay.time_changed.emit(50.0)
        # the dock context (a cursor subscriber) reflects the replay time
        assert w._cursor_dock.context._vals['time'].text() == '50.00 s'
        # the horizon (a cursor subscriber) followed too
        assert w._mod_situation.horizon._win is not None


class TestHorizonHistory:
    @pytest.fixture
    def hz(self, qtbot):
        from ui.app_state import AppState
        from ui.widgets.horizon import ArtificialHorizon
        st = AppState(); h = ArtificialHorizon(st); qtbot.addWidget(h)
        st.set_parsed_data(_data(), b'', '')
        return h, st

    def test_history_window_is_last_10s(self, hz):
        h, st = hz
        st.set_cursor_time(50.0)
        assert h._win is not None
        tw = h._win['t']
        assert tw.min() >= 50.0 - 10.0 - 1e-6
        assert tw.max() <= 50.0 + 1e-6
        assert tw.size >= 2

    def test_history_has_actual_and_desired(self, hz):
        h, st = hz
        st.set_cursor_time(50.0)
        assert h._win['roll'] is not None
        assert h._win['des_roll'] is not None
        # actual roll varies (oscillation) over the window
        assert np.ptp(h._win['roll']) > 1.0

    def test_no_window_before_data_start(self, hz):
        h, st = hz
        st.set_cursor_time(-50.0)
        assert h._win is None

    def test_renders_with_history(self, hz):
        h, st = hz
        st.set_cursor_time(50.0)
        h.resize(360, 420)
        h.repaint()              # must not raise
        assert h._has
