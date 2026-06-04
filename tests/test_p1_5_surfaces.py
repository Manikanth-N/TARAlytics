"""P1.5 tests: Unified Events, Artificial Horizon, RC Visualization, Map
synchronization, and the full Select-Event → all-surfaces-update workflow."""
import numpy as np
import pandas as pd
import pytest


def _data():
    """Synthetic flight with attitude, RC, GPS track, and a mix of events."""
    n = 200
    t = np.linspace(0.0, 100.0, n)
    des_roll = np.where((t >= 30) & (t < 50), 18.0, 0.0)
    act_roll = des_roll.copy()
    c1 = np.where((t >= 30) & (t < 50), 1800.0, 1500.0)
    return {
        'ATT': pd.DataFrame({'TimeS': t, 'DesRoll': des_roll, 'Roll': act_roll,
                             'DesPitch': np.zeros(n), 'Pitch': np.zeros(n),
                             'DesYaw': np.full(n, 90.0), 'Yaw': np.full(n, 90.0)}),
        'RCIN': pd.DataFrame({'TimeS': t, 'C1': c1, 'C2': np.full(n, 1500.0),
                              'C3': np.full(n, 1450.0), 'C4': np.full(n, 1500.0)}),
        'RCOU': pd.DataFrame({'TimeS': t, 'C1': np.full(n, 1550.0),
                              'C2': np.full(n, 1550.0), 'C3': np.full(n, 1500.0),
                              'C4': np.full(n, 1550.0)}),
        'PARM': pd.DataFrame({'Name': ['RCMAP_ROLL', 'RCMAP_PITCH',
                                       'RCMAP_THROTTLE', 'RCMAP_YAW'],
                              'Value': [1.0, 2.0, 3.0, 4.0]}),
        'GPS[0]': pd.DataFrame({'TimeS': t, 'Status': np.full(n, 6),
                                'NSats': np.full(n, 12), 'Spd': np.full(n, 2.0),
                                'Lat': np.linspace(-35.36, -35.355, n),
                                'Lng': np.linspace(149.16, 149.165, n),
                                'Alt': np.clip(t, 0, 40)}),
        'POS': pd.DataFrame({'TimeS': t, 'RelHomeAlt': np.clip(t, 0, 40)}),
        'ARM': pd.DataFrame({'TimeS': [10.0, 95.0], 'ArmState': [1, 0]}),
        'MODE': pd.DataFrame({'TimeS': [10.0, 30.0], 'Mode': [0, 5]}),
        'ERR': pd.DataFrame({'TimeS': [60.0], 'Subsys': [11], 'ECode': [2]}),
        'EV': pd.DataFrame({'TimeS': [10.0, 95.0], 'Id': [10, 11]}),
    }


# ── Unified Events ───────────────────────────────────────────────────────────

@pytest.fixture
def events(qtbot):
    from ui.app_state import AppState
    from ui.modules.mod_events import EventsModule
    st = AppState()
    m = EventsModule(st)
    qtbot.addWidget(m)
    st.set_parsed_data(_data(), b'', '')
    return m, st


class TestUnifiedEvents:
    def test_single_authoritative_source(self, events):
        m, st = events
        from core.event_extractor import EventExtractor
        assert m._events == EventExtractor.collect(st.data)

    def test_search_filter(self, events):
        m, _ = events
        m._search.setText('ERR')
        shown = [i for i in range(m._table.rowCount()) if not m._table.isRowHidden(i)]
        assert shown and all('ERR' in m._events[i][2] or 'ERR' in m._events[i][3].upper()
                             for i in shown)

    def test_severity_filter(self, events):
        m, _ = events
        m._sev.setCurrentText('ERROR')
        shown = [i for i in range(m._table.rowCount()) if not m._table.isRowHidden(i)]
        assert shown and all(m._events[i][1] == 'ERROR' for i in shown)

    def test_type_filter(self, events):
        m, _ = events
        m._type.setCurrentText('MODE')
        shown = [i for i in range(m._table.rowCount()) if not m._table.isRowHidden(i)]
        assert shown and all(m._events[i][2] == 'MODE' for i in shown)

    def test_notes_persist(self, events):
        m, _ = events
        from PyQt6.QtCore import Qt
        item = m._table.item(0, 5)
        item.setText('check this')
        assert m._notes[0] == 'check this'

    def test_status_cycles(self, events):
        m, _ = events
        assert m._status[0] == 'OPEN'
        m._on_cell_clicked(0, 4)
        assert m._status[0] == 'REVIEWED'
        m._on_cell_clicked(0, 4)
        assert m._status[0] == 'FLAGGED'

    def test_selecting_row_drives_cursor(self, events):
        m, st = events
        seen = []
        st.cursor_time_changed.connect(lambda t: seen.append(t))
        m._table.selectRow(3)
        assert seen and seen[-1] == pytest.approx(m._events[3][0])

    def test_event_stepping(self, events):
        m, st = events
        st.set_cursor_time(0.0)
        m._step(+1)
        first = st.cursor_time
        assert first > 0.0
        m._step(+1)
        assert st.cursor_time > first
        m._step(-1)
        assert st.cursor_time == pytest.approx(first)

    def test_jump_to_cursor_selects_nearest(self, events):
        m, st = events
        st.set_cursor_time(59.0)                  # ERR is at 60
        m._select_nearest(59.0)
        row = m._table.selectionModel().selectedRows()[0].row()
        assert m._events[row][2] == 'ERR'

    def test_following_cursor_does_not_loop(self, events):
        m, st = events
        # a cursor move highlights nearest WITHOUT re-emitting another jump
        count = {'n': 0}
        st.cursor_time_changed.connect(lambda t: count.__setitem__('n', count['n'] + 1))
        st.set_cursor_time(60.0)
        assert count['n'] == 1                    # exactly one propagation, no feedback


# ── Artificial Horizon ───────────────────────────────────────────────────────

class TestHorizon:
    def test_reads_attitude_at_cursor(self, qtbot):
        from ui.app_state import AppState
        from ui.widgets.horizon import ArtificialHorizon
        st = AppState(); hz = ArtificialHorizon(st); qtbot.addWidget(hz)
        st.set_parsed_data(_data(), b'', '')
        st.set_cursor_time(40.0)                  # rolling 18°
        assert hz._has
        assert hz._roll == pytest.approx(18.0, abs=0.5)
        assert hz._des_roll == pytest.approx(18.0, abs=0.5)

    def test_no_data_flag(self, qtbot):
        from ui.app_state import AppState
        from ui.widgets.horizon import ArtificialHorizon
        st = AppState(); hz = ArtificialHorizon(st); qtbot.addWidget(hz)
        st.set_cursor_time(5.0)
        assert hz._has is False
        hz.repaint()                              # must not raise without data


# ── RC Visualization ─────────────────────────────────────────────────────────

class TestRCViz:
    def test_pilot_and_servo_at_cursor(self, qtbot):
        from ui.app_state import AppState
        from ui.widgets.rc_viz import RCVisualization
        st = AppState(); rc = RCVisualization(st); qtbot.addWidget(rc)
        st.set_parsed_data(_data(), b'', '')
        st.set_cursor_time(40.0)                  # C1=1800 → roll right
        assert rc._pilot is not None
        assert rc._pilot.roll > 0.1
        assert rc._servo is not None


# ── Map synchronization ──────────────────────────────────────────────────────

class TestMapSync:
    @pytest.fixture
    def mapt(self, qtbot):
        from ui.tab_map_view import MapTab
        m = MapTab(); qtbot.addWidget(m)
        m.update_data(_data())
        return m

    def test_trajectory_and_events_loaded(self, mapt):
        assert mapt._traj is not None
        assert mapt._event_times.size > 0

    def test_set_time_moves_position(self, mapt):
        mapt.set_time(50.0)
        x = mapt._pos_item.getData()[0]
        assert len(x) == 1

    def test_highlight_event_sets_ring(self, mapt):
        mapt.highlight_event(60.0)                # ERR position
        x, y = mapt._evt_highlight.getData()
        assert len(x) == 1


# ── Full workflow: one selection updates every surface ───────────────────────

class TestFullWorkflow:
    def test_select_event_updates_all_surfaces(self, qtbot):
        from ui.main_window import MainWindow
        w = MainWindow(); qtbot.addWidget(w)
        w.data_ready.emit(_data())
        ev = w._mod_events
        target_row = next(i for i, e in enumerate(ev._events) if e[2] == 'ERR')
        target_t = ev._events[target_row][0]

        ev._table.selectRow(target_row)           # ONE user action
        t = w._app_state.cursor_time

        assert t == pytest.approx(target_t)
        assert w._mod_timeline.canvas.cursor_time == pytest.approx(t)
        assert w._cursor_dock.context._vals['time'].text() == f'{t:.2f} s'
        assert w._mod_situation.horizon._has
        assert w._mod_situation.rc._pilot is not None
        # map highlight ring placed at the event
        hx, _ = w._tab_map._evt_highlight.getData()
        assert len(hx) == 1
