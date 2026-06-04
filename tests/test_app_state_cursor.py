"""Tests for the AppState shared-cursor backbone (Step 4.1)."""
import numpy as np
import pandas as pd
import pytest

from ui.app_state import AppState


def _data():
    att = pd.DataFrame({'TimeS': [10.0, 11.0, 12.0],
                        'Roll': [0.0, 10.0, 20.0], 'DesRoll': [0.0, 5.0, 5.0]})
    parm = pd.DataFrame({'Name': ['RCMAP_ROLL'], 'Value': [1.0]})
    return {'ATT': att, 'PARM': parm}


@pytest.fixture
def st():
    return AppState()


class TestSingleUpdatePropagation:
    def test_one_emission_per_set(self, st):
        seen = []
        st.cursor_time_changed.connect(lambda t: seen.append(t))
        st.set_cursor_time(11.5)
        assert seen == [11.5]
        assert st.cursor_time == 11.5

    def test_cursor_time_stored(self, st):
        st.set_cursor_time(7.0)
        assert st.cursor_time == pytest.approx(7.0)


class TestNoRecursiveUpdates:
    def test_reentrant_set_is_ignored(self, st):
        calls = []

        def handler(t):
            calls.append(t)
            # a misbehaving subscriber tries to move the cursor again
            st.set_cursor_time(t + 1.0)

        st.cursor_time_changed.connect(handler)
        st.set_cursor_time(5.0)
        # exactly one propagation; the re-entrant call was dropped by the guard
        assert calls == [5.0]
        assert st.cursor_time == 5.0

    def test_guard_clears_after_broadcast(self, st):
        st.cursor_time_changed.connect(lambda t: st.set_cursor_time(t + 1))
        st.set_cursor_time(1.0)   # re-entrant dropped
        # a subsequent independent move must still work
        out = []
        st.cursor_time_changed.connect(lambda t: out.append(t))
        st.set_cursor_time(2.0)
        assert 2.0 in out and st.cursor_time == 2.0


class TestRepeatedMovement:
    def test_many_moves(self, st):
        seen = []
        st.cursor_time_changed.connect(lambda t: seen.append(t))
        for t in np.linspace(10, 12, 50):
            st.set_cursor_time(float(t))
        assert len(seen) == 50
        assert seen[-1] == pytest.approx(12.0)
        assert st.cursor_time == pytest.approx(12.0)


class TestMultipleSubscribers:
    def test_all_receive(self, st):
        a, b, c = [], [], []
        st.cursor_time_changed.connect(lambda t: a.append(t))
        st.cursor_time_changed.connect(lambda t: b.append(t))
        st.cursor_time_changed.connect(lambda t: c.append(t))
        st.set_cursor_time(11.0)
        assert a == b == c == [11.0]


class TestSubscriberRemoval:
    def test_disconnected_subscriber_stops_receiving(self, st):
        got = []
        fn = lambda t: got.append(t)
        st.cursor_time_changed.connect(fn)
        st.set_cursor_time(10.0)
        st.cursor_time_changed.disconnect(fn)
        st.set_cursor_time(11.0)
        assert got == [10.0]   # only the pre-disconnect move


class TestLazyServices:
    def test_services_none_without_data(self, st):
        assert st.sample_service is None
        assert st.timeline_model is None
        assert st.rc_model is None

    def test_services_built_on_data(self, st):
        st.set_parsed_data(_data(), b'', '')
        svc = st.sample_service
        assert svc is not None
        assert svc.value_at('ATT', 'Roll', 11.5) == pytest.approx(15.0)
        assert st.timeline_model is not None
        assert st.rc_model.channel_for('roll') == 1

    def test_services_cached_same_instance(self, st):
        st.set_parsed_data(_data(), b'', '')
        assert st.sample_service is st.sample_service
        assert st.timeline_model is st.timeline_model
        assert st.rc_model is st.rc_model


class TestLogReload:
    def test_services_rebuilt_and_cursor_reset_on_reload(self, st):
        st.set_parsed_data(_data(), b'', '')
        first_svc = st.sample_service
        st.set_cursor_time(11.0)
        assert st.cursor_time == 11.0

        # reload a different log
        d2 = _data()
        d2['ATT'] = d2['ATT'].assign(Roll=d2['ATT']['Roll'] * 2.0)
        st.set_parsed_data(d2, b'', '')

        assert st.cursor_time == 0.0                    # cursor reset
        second_svc = st.sample_service
        assert second_svc is not first_svc             # rebuilt
        assert second_svc.value_at('ATT', 'Roll', 11.0) == pytest.approx(20.0)

    def test_reload_invalidates_all_services(self, st):
        st.set_parsed_data(_data(), b'', '')
        tm1, rc1 = st.timeline_model, st.rc_model
        st.set_parsed_data(_data(), b'', '')
        assert st.timeline_model is not tm1
        assert st.rc_model is not rc1
