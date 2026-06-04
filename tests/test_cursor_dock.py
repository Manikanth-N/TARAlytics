"""Tests for the Step 4.3 CursorDock: ValuesAtCursorTable (single batch + provenance),
CursorContextPanel, and the Pilot/Demand/Actual AttitudeMatrix."""
import numpy as np
import pandas as pd
import pytest

from ui.design.tokens import T


def _dock_data():
    """Synthetic flight: pilot rolls right mid-flight; a divergence window where the
    aircraft fails to follow the roll demand; full GPS/BAT/RCOU for the table."""
    n = 200
    t = np.linspace(0.0, 100.0, n)
    # actual roll tracks demand except in [60,70] where it diverges
    des_roll = np.where((t >= 30) & (t < 50), 20.0, 0.0)
    act_roll = des_roll.copy()
    div = (t >= 60) & (t < 70)
    des_roll[div] = 20.0
    act_roll[div] = -5.0                     # 25° divergence
    # pilot stick: centred except [30,50] where pilot commands right roll
    c1 = np.full(n, 1500.0)
    c1[(t >= 30) & (t < 50)] = 1800.0
    return {
        'ATT': pd.DataFrame({'TimeS': t,
                             'DesRoll': des_roll, 'Roll': act_roll,
                             'DesPitch': np.zeros(n), 'Pitch': np.zeros(n),
                             'DesYaw': np.full(n, 90.0), 'Yaw': np.full(n, 90.0)}),
        'RCIN': pd.DataFrame({'TimeS': t, 'C1': c1, 'C2': np.full(n, 1500.0),
                              'C3': np.full(n, 1400.0), 'C4': np.full(n, 1500.0)}),
        'RCOU': pd.DataFrame({'TimeS': t, 'C1': np.full(n, 1550.0),
                              'C2': np.full(n, 1560.0), 'C3': np.full(n, 1545.0),
                              'C4': np.full(n, 1555.0)}),
        'PARM': pd.DataFrame({'Name': ['RCMAP_ROLL', 'RCMAP_PITCH',
                                       'RCMAP_THROTTLE', 'RCMAP_YAW'],
                              'Value': [1.0, 2.0, 3.0, 4.0]}),
        'POS': pd.DataFrame({'TimeS': t, 'RelHomeAlt': np.clip(t, 0, 30)}),
        'GPS[0]': pd.DataFrame({'TimeS': t, 'Status': np.full(n, 6),
                                'NSats': np.full(n, 11), 'Spd': np.full(n, 3.5)}),
        'BAT': pd.DataFrame({'TimeS': t, 'Volt': np.linspace(12.6, 11.4, n),
                             'Curr': np.full(n, 28.0)}),
        'ARM': pd.DataFrame({'TimeS': [10.0, 95.0], 'ArmState': [1, 0]}),
        'MODE': pd.DataFrame({'TimeS': [10.0, 30.0], 'Mode': [0, 5]}),
    }


@pytest.fixture
def dock(qtbot):
    from ui.app_state import AppState
    from ui.widgets.cursor_dock import CursorDock
    st = AppState()
    d = CursorDock(st)
    qtbot.addWidget(d)
    st.set_parsed_data(_dock_data(), b'', '')
    return d, st


# ── ValuesAtCursorTable ──────────────────────────────────────────────────────

class TestValuesTable:
    def test_single_batch_per_cursor_move(self, dock):
        d, st = dock
        from core import sample_service as ss
        calls = {'n': 0}
        orig = ss.SampleService.batch

        def counting(self, t, specs, step=False):
            calls['n'] += 1
            return orig(self, t, specs, step)
        ss.SampleService.batch = counting
        try:
            st.set_cursor_time(40.0)
            assert calls['n'] == 1          # exactly one batch for the whole table
        finally:
            ss.SampleService.batch = orig

    def test_values_resolve_and_format(self, dock):
        d, st = dock
        st.set_cursor_time(40.0)
        rows = {r.label: d.values._table.item(i, 1).text()
                for i, r in enumerate(d.values._rows)}
        assert 'V' in rows['BAT Volt']
        assert rows['Motor 1'].startswith('15')      # RCOU.C1 ~1550
        assert rows['Vibe Z'] == '—'                 # VIBE absent → never fabricated

    def test_configurable_rows(self, dock):
        from ui.widgets.cursor_dock import RowSpec
        d, st = dock
        d.values.set_rows([RowSpec('Roll', 'ATT', 'Roll', '°', '{:+.1f}')])
        st.set_cursor_time(40.0)
        assert d.values._table.rowCount() == 1
        assert '°' in d.values._table.item(0, 1).text()

    def test_out_of_range_is_dash(self, dock):
        d, st = dock
        st.set_cursor_time(-5.0)                      # before any data
        for i in range(len(d.values._rows)):
            assert d.values._table.item(i, 1).text() == '—'

    def test_hover_sets_provenance_tooltip(self, dock):
        d, st = dock
        st.set_cursor_time(40.3)
        d.values._on_hover(0, 1)                       # BAT Volt
        tip = d.values._table.item(0, 1).toolTip()
        assert 'BAT.Volt' in tip
        assert ('interpolated' in tip or 'exact' in tip)


# ── CursorContextPanel ───────────────────────────────────────────────────────

class TestContextPanel:
    def test_fields_populate(self, dock):
        d, st = dock
        st.set_cursor_time(40.0)
        v = d.context._vals
        assert v['flight'].text() == '1 / 1'
        assert v['time'].text() == '40.00 s'
        assert v['mode'].text() == 'LOITER'
        assert v['gps'].text() == 'RTK_FIXED'
        assert v['sats'].text() == '11'
        assert 'm' in v['alt'].text()
        assert 'm/s' in v['speed'].text()

    def test_verify_state_reflected(self, dock):
        d, st = dock
        st.set_verification({'state': 'VERIFIED', 'hashes': {}})
        assert d.context._vals['verify'].text() == 'VERIFIED'

    def test_pre_arm_has_no_flight_number(self, dock):
        d, st = dock
        st.set_cursor_time(5.0)                         # before arm at 10s
        assert d.context._vals['flight'].text() == '— / 1'


# ── AttitudeMatrix (Pilot / Demand / Actual) ─────────────────────────────────

class TestAttitudeMatrix:
    def test_pilot_demand_actual_track_during_maneuver(self, dock):
        d, st = dock
        st.set_cursor_time(40.0)                        # pilot rolling right, tracked
        m = d.context._matrix._cells
        assert m[('roll', 'pilot')].text().startswith('+0.')  # >0 stick
        assert m[('roll', 'pilot')].text() != '+0.00'
        assert m[('roll', 'demand')].text() == '+20°'
        assert m[('roll', 'actual')].text() == '+20°'

    def test_divergence_is_colour_flagged(self, dock):
        d, st = dock
        st.set_cursor_time(65.0)                        # demand 20°, actual -5° → 25°
        cell = d.context._matrix._cells[('roll', 'actual')]
        assert cell.text() == '-5°'
        assert T.status.critical in cell.styleSheet()   # >= 20° divergence → critical

    def test_tracked_flight_not_flagged(self, dock):
        d, st = dock
        st.set_cursor_time(40.0)
        cell = d.context._matrix._cells[('roll', 'actual')]
        assert T.status.critical not in cell.styleSheet()
        assert T.status.caution not in cell.styleSheet()

    def test_blank_without_data(self, qtbot):
        from ui.app_state import AppState
        from ui.widgets.cursor_dock import CursorDock
        st = AppState()
        d = CursorDock(st)
        qtbot.addWidget(d)
        st.set_cursor_time(10.0)                        # no data loaded
        assert d.context._matrix._cells[('roll', 'pilot')].text() == '—'

    def test_delta_column_shows_magnitude(self, dock):
        d, st = dock
        st.set_cursor_time(65.0)                        # demand +20°, actual -5° → 25°
        cell = d.context._matrix._cells[('roll', 'delta')]
        assert cell.text() == '25°'
        assert T.status.critical in cell.styleSheet()   # ≥ 20° → critical

    def test_throttle_row_present_and_populates(self, dock):
        d, st = dock
        st.set_cursor_time(40.0)
        m = d.context._matrix._cells
        assert ('throttle', 'pilot') in m
        # RCIN.C3 = 1400 → (1400-1000)/1000 = 0.40 pilot throttle
        assert m[('throttle', 'pilot')].text() == '0.40'
        # no CTUN in synthetic data → demand / Δ never fabricated
        assert m[('throttle', 'demand')].text() == '—'
        assert m[('throttle', 'delta')].text() == '—'

    def test_snapshot_placeholder_records(self, dock):
        d, st = dock
        st.set_cursor_time(42.0)
        d._on_snapshot()
        assert len(d._snapshots) == 1
        assert '42.00' in d._snap_status.text()
