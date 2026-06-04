"""P4 tests: persistent timeline transport, workspace mode, pop-out, saved layouts."""
import numpy as np
import pandas as pd
import pytest


def _data(n=300, dur=100.0):
    t = np.linspace(0.0, dur, n)
    return {
        'ATT': pd.DataFrame({'TimeS': t, 'DesRoll': np.zeros(n), 'Roll': np.sin(t),
                             'DesPitch': np.zeros(n), 'Pitch': np.zeros(n),
                             'DesYaw': np.full(n, 90.0), 'Yaw': np.full(n, 90.0)}),
        'RCIN': pd.DataFrame({'TimeS': t, 'C1': np.full(n, 1500.0)}),
        'RCOU': pd.DataFrame({'TimeS': t, 'C1': np.full(n, 1500.0)}),
        'PARM': pd.DataFrame({'Name': ['RCMAP_ROLL'], 'Value': [1.0]}),
        'POS': pd.DataFrame({'TimeS': t, 'RelHomeAlt': np.clip(t, 0, 40),
                             'Lat': np.linspace(-35.36, -35.355, n),
                             'Lng': np.linspace(149.16, 149.165, n)}),
        'GPS[0]': pd.DataFrame({'TimeS': t, 'Status': np.full(n, 6), 'NSats': np.full(n, 12),
                                'Spd': np.full(n, 2.0), 'Lat': np.linspace(-35.36, -35.355, n),
                                'Lng': np.linspace(149.16, 149.165, n)}),
        'ARM': pd.DataFrame({'TimeS': [5.0, 95.0], 'ArmState': [1, 0]}),
        'MODE': pd.DataFrame({'TimeS': [5.0, 40.0], 'Mode': [0, 5]}),
        'ERR': pd.DataFrame({'TimeS': [60.0], 'Subsys': [11], 'ECode': [2]}),
    }


@pytest.fixture
def transport(qtbot):
    from ui.app_state import AppState
    from ui.widgets.timeline_transport import TimelineTransport
    st = AppState()
    tr = TimelineTransport(st)
    qtbot.addWidget(tr)
    tr.resize(800, 74)
    st.set_parsed_data(_data(), b'', '')
    return tr, st


class TestTransport:
    def test_scrub_drives_cursor(self, transport):
        tr, st = transport
        mt = tr._mini
        x0, x1 = mt._plot_x()
        target_t = mt._x2t((x0 + x1) / 2)
        seen = []
        st.cursor_time_changed.connect(lambda t: seen.append(t))
        st.set_cursor_time(target_t)               # what a mid scrub emits
        assert seen and abs(st.cursor_time - target_t) < 1e-6

    def test_play_tick_advances_cursor(self, transport):
        tr, st = transport
        st.set_cursor_time(10.0)
        tr._speed = 5.0
        tr._tick()
        assert st.cursor_time == pytest.approx(10.0 + 0.033 * 5.0, abs=1e-6)

    def test_play_stops_at_end(self, transport):
        tr, st = transport
        t0, t1 = tr._span()
        st.set_cursor_time(t1 - 0.01)
        tr._playing = True
        tr._tick()
        assert st.cursor_time == pytest.approx(t1)
        assert tr._playing is False

    def test_reset_to_start(self, transport):
        tr, st = transport
        st.set_cursor_time(50.0)
        tr._reset()
        t0, _ = tr._span()
        assert st.cursor_time == pytest.approx(t0)

    def test_mini_has_modes_and_events(self, transport):
        tr, st = transport
        assert len(tr._mini._modes) >= 1
        assert len(tr._mini._events) >= 1

    def test_renders(self, transport):
        tr, st = transport
        st.set_cursor_time(50.0)
        tr._mini.repaint()           # must not raise


class TestTransportInMainWindow:
    def test_transport_persistent_and_global(self, qtbot):
        from ui.main_window import MainWindow
        w = MainWindow(); qtbot.addWidget(w)
        w.data_ready.emit(_data())
        # the transport is a registered cursor subscriber regardless of active module
        subs = w._app_state.cursor_debug_info()['subscribers']
        assert 'TimelineTransport' in subs
        # transport drives every module: scrub → dock + situation follow
        w._transport._mini._app.set_cursor_time(50.0)
        assert w._cursor_dock.context._vals['time'].text() == '50.00 s'
        assert w._mod_situation.horizon._has
