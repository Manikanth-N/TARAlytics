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
                                'HDop': np.full(n, 0.8), 'Spd': np.full(n, 2.0),
                                'Alt': np.clip(t, 0, 40),
                                'Lat': np.linspace(-35.36, -35.355, n),
                                'Lng': np.linspace(149.16, 149.165, n)}),
        'XKF4[0]': pd.DataFrame({'TimeS': t, 'SV': np.full(n, 0.1), 'SP': np.full(n, 0.1),
                                 'SH': np.full(n, 0.1), 'SM': np.full(n, 0.1), 'FS': np.zeros(n)}),
        'VIBE[0]': pd.DataFrame({'TimeS': t, 'VibeX': np.full(n, 5.0), 'VibeY': np.full(n, 5.0),
                                 'VibeZ': np.full(n, 8.0), 'Clip': np.zeros(n)}),
        'BAT': pd.DataFrame({'TimeS': t, 'Volt': np.linspace(12.6, 11.4, n), 'Curr': np.full(n, 28.0)}),
        'ARM': pd.DataFrame({'TimeS': [5.0, 95.0], 'ArmState': [1, 0]}),
        'MODE': pd.DataFrame({'TimeS': [5.0], 'Mode': [5]}),
    }


class TestTransportDrivesCursor:
    def test_transport_play_advances_shared_cursor(self, qtbot):
        from ui.main_window import MainWindow
        w = MainWindow(); qtbot.addWidget(w)
        w.data_ready.emit(_data())
        w._app_state.set_cursor_time(0.0)
        seen = []
        w._app_state.cursor_time_changed.connect(lambda t: seen.append(t))
        w._transport._speed = 5.0
        w._transport.toggle_play(); w._transport._tick(); w._transport._stop()
        assert w._app_state.cursor_time > 0.0            # playback advanced the cursor
        assert seen and seen[-1] == pytest.approx(w._app_state.cursor_time)

    def test_playback_updates_other_surfaces(self, qtbot):
        from ui.main_window import MainWindow
        w = MainWindow(); qtbot.addWidget(w)
        w.data_ready.emit(_data())
        w._app_state.set_cursor_time(50.0)               # a transport playback position
        # the dock context (a cursor subscriber) reflects the time
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


class TestPlotter:
    @pytest.fixture
    def plot(self, qtbot):
        from ui.main_window import MainWindow
        w = MainWindow(); qtbot.addWidget(w)
        w.data_ready.emit(_data())
        return w, w._tab_plotter

    def test_preset_loads_signals(self, plot):
        w, pl = plot
        pl._clear_all(); pl.apply_preset('Attitude')
        assert set(pl._active_sigs) == {'ATT.Roll', 'ATT.DesRoll', 'ATT.Pitch', 'ATT.DesPitch'}

    def test_preset_resolves_instance(self, plot):
        w, pl = plot
        pl._clear_all(); pl.apply_preset('EKF')
        assert set(pl._active_sigs) == {'XKF4[0].SV', 'XKF4[0].SP', 'XKF4[0].SH', 'XKF4[0].SM'}

    def test_preset_clears_previous(self, plot):
        w, pl = plot
        pl.apply_preset('Attitude'); pl.apply_preset('Power')
        assert set(pl._active_sigs) == {'BAT.Volt', 'BAT.Curr'}

    def test_search_filters_tree(self, plot):
        w, pl = plot
        pl._filter_tree('vibex')
        root = pl._tree.invisibleRootItem(); visible = []
        for gi in range(root.childCount()):
            g = root.child(gi)
            for mi in range(g.childCount()):
                m = g.child(mi)
                for fi in range(m.childCount()):
                    f = m.child(fi)
                    if not f.isHidden():
                        visible.append(f.text(0).lower())
        assert visible and all('vibex' in v for v in visible)

    def test_event_to_signal_linking(self, plot):
        w, pl = plot
        pl._clear_all()
        w._app_state.request_plot('OSCILLATION')        # finding category → preset
        assert set(pl._active_sigs) == {'ATT.Roll', 'ATT.DesRoll', 'ATT.Pitch', 'ATT.DesPitch'}
        pl._clear_all()
        w._app_state.request_plot('VIBE')
        assert set(pl._active_sigs) == {'VIBE[0].VibeX', 'VIBE[0].VibeY', 'VIBE[0].VibeZ'}

    def test_finding_click_plots_and_navigates(self, plot):
        w, pl = plot
        # build a finding row and click it
        from core.flight_analytics import Finding
        d = w._mod_debrief
        navs = []
        d.nav_requested.connect(lambda i: navs.append(i))
        d._on_finding(Finding('WARNING', 'GPS', 'GPS anomaly', 'x', t_start=40.0))
        assert set(pl._active_sigs) == {'GPS[0].Status', 'GPS[0].NSats', 'GPS[0].HDop'}
        assert navs == [4]                               # navigated to Signals
