"""Tests for core.timeline_model.TimelineModel."""
import os
import numpy as np
import pandas as pd
import pytest

from core.timeline_model import TimelineModel, Phase, ModeSegment, ArmRegion


# ── synthetic log builders ───────────────────────────────────────────────────

def _pos(times, agl):
    return pd.DataFrame({'TimeS': np.asarray(times, float),
                         'RelHomeAlt': np.asarray(agl, float)})


def _arm(events):  # events: list of (t, armed_bool)
    return pd.DataFrame({'TimeS': [e[0] for e in events],
                         'ArmState': [1 if e[1] else 0 for e in events]})


def _mode(changes):  # changes: list of (t, mode_num)
    return pd.DataFrame({'TimeS': [c[0] for c in changes],
                         'Mode': [c[1] for c in changes]})


def _ev(rows):  # rows: list of (t, id)
    return pd.DataFrame({'TimeS': [r[0] for r in rows],
                         'Id': [r[1] for r in rows]})


def _normal_profile():
    # 0..60s: pre-arm 0-5, takeoff climb 5-15 (0->10m), hover 15-45 (10m),
    # descent/land 45-55 (10->0), post 55-60
    t = np.arange(0.0, 60.0, 0.5)
    agl = np.piecewise(
        t,
        [t < 5, (t >= 5) & (t < 15), (t >= 15) & (t < 45), (t >= 45) & (t < 55), t >= 55],
        [0.0,
         lambda x: (x - 5) * 1.0,        # climb to 10
         10.0,
         lambda x: 10.0 - (x - 45) * 1.0,  # descend to 0
         0.0],
    )
    return t, agl


# ── tests ────────────────────────────────────────────────────────────────────

class TestNormalFlight:
    @pytest.fixture
    def tl(self):
        t, agl = _normal_profile()
        data = {
            'POS': _pos(t, agl),
            'ARM': _arm([(5.0, True), (55.0, False)]),
            'MODE': _mode([(0.0, 0), (5.0, 4)]),   # STABILIZE -> GUIDED
        }
        return TimelineModel(data)

    def test_log_span(self, tl):
        a, b = tl.log_span()
        assert a == pytest.approx(0.0) and b == pytest.approx(59.5)

    def test_arm_region(self, tl):
        r = tl.arm_regions()
        assert len(r) == 1
        assert r[0].t_start == pytest.approx(5.0) and r[0].t_end == pytest.approx(55.0)

    def test_phases_sequence(self, tl):
        kinds = [p.kind for p in tl.phases()]
        assert kinds[0] == 'PRE_ARM'
        assert kinds[-1] == 'POST'
        assert 'TAKEOFF' in kinds
        assert 'HOVER' in kinds
        assert 'LAND' in kinds

    def test_phases_are_contiguous_and_cover_span(self, tl):
        ph = tl.phases()
        a, b = tl.log_span()
        assert ph[0].t_start == pytest.approx(a)
        assert ph[-1].t_end == pytest.approx(b)
        for i in range(len(ph) - 1):
            assert ph[i].t_end == pytest.approx(ph[i + 1].t_start)

    def test_altitude_profile(self, tl):
        prof = tl.altitude_profile()
        assert prof.source == 'POS.RelHomeAlt'
        assert prof.agl.max() == pytest.approx(10.0, abs=0.5)

    def test_phase_at_and_mode_at(self, tl):
        assert tl.phase_at(30.0).kind == 'HOVER'
        assert tl.mode_at(30.0) == 'GUIDED'
        assert tl.phase_at(2.0).kind == 'PRE_ARM'


class TestModeTransitions:
    def test_segments_merge_and_label(self):
        data = {'MODE': _mode([(0, 0), (10, 4), (20, 4), (30, 5)]),  # dup 4 merged
                'POS': _pos(*_normal_profile()),
                'ARM': _arm([(0, True)])}
        segs = TimelineModel(data).mode_segments()
        labels = [(s.mode, round(s.t_start, 1)) for s in segs]
        assert ('STABILIZE', 0.0) in labels
        assert ('GUIDED', 10.0) in labels      # 10->30 merged (dup at 20 dropped)
        assert ('LOITER', 30.0) in labels
        # no consecutive duplicate mode_nums
        nums = [s.mode_num for s in segs]
        assert all(nums[i] != nums[i + 1] for i in range(len(nums) - 1))


class TestRTL:
    def test_rtl_phase_labeled_from_mode(self):
        t, agl = _normal_profile()
        data = {
            'POS': _pos(t, agl),
            'ARM': _arm([(5.0, True), (55.0, False)]),
            'MODE': _mode([(0, 0), (5, 4), (40, 6)]),   # ... -> RTL(6) at 40
        }
        kinds = [p.kind for p in TimelineModel(data).phases()]
        assert 'RTL' in kinds


class TestTruncatedLog:
    def test_armed_never_disarmed_extends_to_end(self):
        # arm at 5, no disarm; log ends at ~59.5
        t, agl = _normal_profile()
        data = {'POS': _pos(t, agl), 'ARM': _arm([(5.0, True)]),
                'MODE': _mode([(0, 0), (5, 4)])}
        tl = TimelineModel(data)
        r = tl.arm_regions()
        assert len(r) == 1 and r[0].t_end == pytest.approx(tl.log_span()[1])
        # phases still derived; ends with last in-window phase, then POST absent
        ph = tl.phases()
        assert ph[-1].t_end == pytest.approx(tl.log_span()[1])


class TestMissingEvents:
    def test_no_arm_no_mode_gives_single_flight_phase(self):
        t, agl = _normal_profile()
        data = {'POS': _pos(t, agl)}   # no ARM, no MODE, no EV
        tl = TimelineModel(data)
        assert tl.arm_regions() == []
        assert tl.mode_segments() == []
        ph = tl.phases()
        assert len(ph) == 1 and ph[0].kind == 'FLIGHT'

    def test_ev_fallback_when_no_arm(self):
        t, agl = _normal_profile()
        data = {'POS': _pos(t, agl), 'EV': _ev([(5.0, 10), (55.0, 11)])}  # armed/disarmed
        r = TimelineModel(data).arm_regions()
        assert len(r) == 1 and r[0].source == 'EV'
        assert r[0].t_start == pytest.approx(5.0)


class TestSparseMode:
    def test_single_mode_one_segment(self):
        t, agl = _normal_profile()
        data = {'POS': _pos(t, agl), 'ARM': _arm([(5, True), (55, False)]),
                'MODE': _mode([(0, 0)])}   # only one mode the whole flight
        segs = TimelineModel(data).mode_segments()
        assert len(segs) == 1
        assert segs[0].mode == 'STABILIZE'
        assert segs[0].t_end == pytest.approx(TimelineModel(data).log_span()[1])

    def test_no_altitude_falls_back_to_flight(self):
        data = {'ARM': _arm([(5, True), (55, False)]), 'MODE': _mode([(0, 0)]),
                # give a span via a message with TimeS but no usable AGL
                'IMU[0]': pd.DataFrame({'TimeS': np.arange(0, 60, 0.5),
                                        'AccZ': np.zeros(120)})}
        ph = TimelineModel(data).phases()
        # PRE_ARM + FLIGHT (no altitude -> single flight) [+ POST]
        kinds = [p.kind for p in ph]
        assert 'PRE_ARM' in kinds and 'FLIGHT' in kinds


# ── real-log integration ─────────────────────────────────────────────────────

BIN = os.path.join(os.path.dirname(__file__), '..', 'logs', '00000002.BIN')


@pytest.mark.skipif(not os.path.isfile(BIN), reason='reference log absent')
class TestRealLog:
    @pytest.fixture(scope='class')
    def tl(self):
        from core.log_parser import DataFlashParser
        return TimelineModel(DataFlashParser().parse(BIN))

    def test_build_returns_complete_timeline(self, tl):
        t = tl.build()
        assert t.t_end > t.t_start
        assert len(t.arm_regions) >= 1
        assert len(t.modes) >= 1
        assert len(t.phases) >= 1
        assert not t.altitude.empty
        assert len(t.events) == 29

    def test_armed_window_matches_known(self, tl):
        r = tl.arm_regions()
        assert r[0].t_start == pytest.approx(126.99, abs=0.1)
        assert r[-1].t_end == pytest.approx(170.57, abs=0.1)

    def test_altitude_source_is_agl(self, tl):
        prof = tl.altitude_profile()
        assert prof.source in ('POS.RelHomeAlt', 'BARO[0].Alt', 'SIM2.-PD')
        assert prof.agl.max() < 60   # AGL, not 594m AMSL
