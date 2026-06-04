"""Tests for the Step 4.2 Timeline surface: pure transform/clustering helpers,
the AppState cursor-debug introspection, and the TimelineCanvas interactions."""
import numpy as np
import pandas as pd
import pytest

from ui.widgets.timeline_canvas import (
    time_to_x, x_to_time, cluster_events, event_density, _nice_step,
    EventCluster,
)


# ── synthetic flight with arm/mode/events/altitude ───────────────────────────

def _flight_data():
    t = np.linspace(0.0, 100.0, 400)
    agl = np.clip(np.concatenate([
        np.linspace(0, 20, 100), np.full(200, 20.0), np.linspace(20, 0, 100)]), 0, None)
    return {
        'POS': pd.DataFrame({'TimeS': t, 'RelHomeAlt': agl}),
        'ARM': pd.DataFrame({'TimeS': [10.0, 90.0], 'ArmState': [1, 0]}),
        'MODE': pd.DataFrame({'TimeS': [10.0, 40.0, 80.0], 'Mode': [0, 5, 6]}),
        'EV':  pd.DataFrame({'TimeS': [10.0, 90.0], 'Id': [10, 11]}),
        'ERR': pd.DataFrame({'TimeS': [55.0], 'Subsys': [11], 'ECode': [2]}),
    }


def _multi_flight_data():
    rows_t, rows_s = [], []
    for base in (10.0, 60.0, 110.0):
        rows_t += [base, base + 30.0]; rows_s += [1, 0]
    t = np.linspace(0.0, 150.0, 300)
    return {
        'POS': pd.DataFrame({'TimeS': t, 'RelHomeAlt': np.abs(np.sin(t / 10) * 15)}),
        'ARM': pd.DataFrame({'TimeS': rows_t, 'ArmState': rows_s}),
        'MODE': pd.DataFrame({'TimeS': [10.0], 'Mode': [5]}),
    }


# ── pure transform helpers ───────────────────────────────────────────────────

class TestTransform:
    def test_time_to_x_endpoints(self):
        assert time_to_x(0, 0, 100, 80, 1080) == pytest.approx(80)
        assert time_to_x(100, 0, 100, 80, 1080) == pytest.approx(1080)
        assert time_to_x(50, 0, 100, 80, 1080) == pytest.approx(580)

    def test_round_trip(self):
        for t in (0, 12.5, 37, 99.9, 100):
            x = time_to_x(t, 0, 100, 80, 1080)
            assert x_to_time(x, 0, 100, 80, 1080) == pytest.approx(t, abs=1e-6)

    def test_x_to_time_clamps_outside_view(self):
        assert x_to_time(0, 0, 100, 80, 1080) == pytest.approx(0)      # left of plot
        assert x_to_time(2000, 0, 100, 80, 1080) == pytest.approx(100)  # right of plot

    def test_zero_span_is_safe(self):
        assert time_to_x(5, 10, 10, 80, 1080) == 80
        assert x_to_time(500, 10, 10, 80, 1080) == 10

    def test_nice_step_is_1_2_5(self):
        for span in (10, 47, 100, 523, 1000, 3.2):
            s = _nice_step(span, 8)
            mant = s / 10 ** np.floor(np.log10(s))
            assert round(mant) in (1, 2, 5, 10)


# ── event clustering / density (scalability) ─────────────────────────────────

class TestClustering:
    def _events(self, times, sev=None):
        sev = sev or ['INFO'] * len(times)
        return [(float(t), s, 'EV', 'x') for t, s in zip(times, sev)]

    def test_dense_events_collapse_when_zoomed_out(self):
        # 500 events packed into a 1000px plot collapse to far fewer clusters
        ev = self._events(np.linspace(0, 100, 500))
        clusters = cluster_events(ev, 0, 100, 80, 1080, min_px=11)
        assert len(clusters) < 120
        assert sum(c.count for c in clusters) == 500   # nothing lost

    def test_zoom_in_splits_clusters(self):
        ev = self._events(np.linspace(0, 100, 500))
        wide = cluster_events(ev, 0, 100, 80, 1080)
        narrow = cluster_events(ev, 40, 50, 80, 1080)   # 10s window
        # zooming into a 10s slice exposes more individual pins per second
        assert len(narrow) > 0
        # density within the zoomed window is higher resolution
        assert max((c.count for c in wide), default=0) >= \
               max((c.count for c in narrow), default=0)

    def test_cluster_severity_is_highest(self):
        ev = self._events([10.0, 10.05, 10.1], ['INFO', 'CRITICAL', 'WARNING'])
        clusters = cluster_events(ev, 0, 100, 80, 1080, min_px=50)
        assert len(clusters) == 1
        assert clusters[0].severity == 'CRITICAL'
        assert clusters[0].count == 3

    def test_only_visible_events_clustered(self):
        ev = self._events([5.0, 50.0, 95.0])
        clusters = cluster_events(ev, 40, 60, 80, 1080)
        assert len(clusters) == 1
        assert clusters[0].t == pytest.approx(50.0)

    def test_density_counts_and_bins(self):
        times = np.array([1.0, 1.0, 1.0, 9.0])
        d = event_density(times, 0, 10, 10)
        assert d.shape == (10,)
        assert d.sum() == 4
        assert d[1] == 3   # three events in the 1..2s bin

    def test_density_empty_is_zeros(self):
        assert event_density(np.array([]), 0, 10, 5).sum() == 0


# ── AppState cursor-debug introspection ──────────────────────────────────────

class TestCursorDebug:
    def test_debug_info_reports_state_and_subscribers(self):
        from ui.app_state import AppState
        st = AppState()
        st.connect_cursor(lambda t: None, 'A')
        st.connect_cursor(lambda t: None, 'B')
        st.set_cursor_time(12.5)
        info = st.cursor_debug_info()
        assert info['cursor_time'] == pytest.approx(12.5)
        assert info['broadcasting'] is False      # guard cleared after broadcast
        assert info['named_count'] == 2
        assert info['subscribers'] == ['A', 'B']
        assert info['subscriber_count'] >= 2       # Qt's own receiver count

    def test_broadcasting_true_during_emit(self):
        from ui.app_state import AppState
        st = AppState()
        seen = {}
        st.connect_cursor(lambda t: seen.update(st.cursor_debug_info()), 'probe')
        st.set_cursor_time(3.0)
        assert seen['broadcasting'] is True        # guard was set mid-broadcast


# ── canvas-level interaction (needs QApplication via qtbot) ──────────────────

@pytest.fixture
def canvas(qtbot):
    from ui.app_state import AppState
    from ui.widgets.timeline_canvas import TimelineCanvas
    st = AppState()
    c = TimelineCanvas(st)
    qtbot.addWidget(c)
    c.resize(1080, 320)
    st.set_parsed_data(_flight_data(), b'', '')
    return c, st


class TestCanvas:
    def test_loads_structure(self, canvas):
        c, _ = canvas
        assert len(c._flights) == 1
        assert c._t_start == pytest.approx(0.0)
        assert c._t_end == pytest.approx(100.0)
        assert len(c._events) > 0

    def test_fit_resets_view(self, canvas):
        c, _ = canvas
        c._view_start, c._view_end = 40, 50
        c.fit()
        assert (c._view_start, c._view_end) == pytest.approx((0.0, 100.0))

    def test_x2t_maps_into_view(self, canvas):
        c, _ = canvas
        x0, x1 = c._plot_x()
        mid = c._x2t((x0 + x1) / 2)
        assert mid == pytest.approx((c._view_start + c._view_end) / 2, rel=1e-3)

    def test_step_event_moves_cursor_forward_and_back(self, canvas):
        c, st = canvas
        st.set_cursor_time(0.0)
        c.step_event(+1)
        first = st.cursor_time
        assert first > 0.0
        c.step_event(+1)
        assert st.cursor_time > first
        c.step_event(-1)
        assert st.cursor_time == pytest.approx(first)

    def test_step_flight_jumps_to_flight_start(self, canvas):
        c, st = canvas
        st.set_cursor_time(0.0)
        c.step_flight(+1)
        assert st.cursor_time == pytest.approx(c._flights[0].start)

    def test_render_does_not_crash(self, canvas):
        c, _ = canvas
        c._render_static()
        assert c._static is not None
        assert c._static.size().width() == c.width()


class TestMultiFlightCanvas:
    def test_three_flight_windows(self, qtbot):
        from ui.app_state import AppState
        from ui.widgets.timeline_canvas import TimelineCanvas
        st = AppState()
        c = TimelineCanvas(st)
        qtbot.addWidget(c)
        c.resize(1080, 320)
        st.set_parsed_data(_multi_flight_data(), b'', '')
        assert len(c._flights) == 3

    def test_step_flight_walks_all_three(self, qtbot):
        from ui.app_state import AppState
        from ui.widgets.timeline_canvas import TimelineCanvas
        st = AppState()
        c = TimelineCanvas(st)
        qtbot.addWidget(c)
        c.resize(1080, 320)
        st.set_parsed_data(_multi_flight_data(), b'', '')
        st.set_cursor_time(0.0)
        starts = []
        for _ in range(3):
            c.step_flight(+1)
            starts.append(round(st.cursor_time, 1))
        assert starts == [round(f.start, 1) for f in c._flights]
