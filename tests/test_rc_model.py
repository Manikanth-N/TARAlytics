"""Tests for core.rc_model.RCModel."""
import os
import numpy as np
import pandas as pd
import pytest

from core.rc_model import RCModel, StickState, params_from_data


class TestDefaultMapping:
    def test_default_axis_channels(self):
        rc = RCModel({})  # no params
        assert rc.channel_for('roll') == 1
        assert rc.channel_for('pitch') == 2
        assert rc.channel_for('throttle') == 3
        assert rc.channel_for('yaw') == 4

    def test_default_normalization_centered(self):
        rc = RCModel({})  # defaults MIN1000 TRIM1500 MAX2000
        assert rc.normalize('roll', 1500) == pytest.approx(0.0)   # trim -> 0
        assert rc.normalize('roll', 2000) == pytest.approx(1.0)   # full right
        assert rc.normalize('roll', 1000) == pytest.approx(-1.0)  # full left
        assert rc.normalize('roll', 1750) == pytest.approx(0.5)

    def test_default_throttle_0_to_1(self):
        rc = RCModel({})
        assert rc.normalize('throttle', 1000) == pytest.approx(0.0)
        assert rc.normalize('throttle', 2000) == pytest.approx(1.0)
        assert rc.normalize('throttle', 1500) == pytest.approx(0.5)

    def test_clamping(self):
        rc = RCModel({})
        assert rc.normalize('roll', 2500) == pytest.approx(1.0)
        assert rc.normalize('roll', 500) == pytest.approx(-1.0)
        assert rc.normalize('throttle', 2500) == pytest.approx(1.0)


class TestCustomMapping:
    def test_custom_rcmap(self):
        rc = RCModel({'RCMAP_ROLL': 5, 'RCMAP_PITCH': 6,
                      'RCMAP_THROTTLE': 7, 'RCMAP_YAW': 8})
        assert rc.channel_for('roll') == 5
        assert rc.channel_for('yaw') == 8

    def test_custom_min_max_trim(self):
        rc = RCModel({'RC1_MIN': 1100, 'RC1_MAX': 1900, 'RC1_TRIM': 1500})
        assert rc.normalize('roll', 1900) == pytest.approx(1.0)
        assert rc.normalize('roll', 1100) == pytest.approx(-1.0)
        assert rc.normalize('roll', 1700) == pytest.approx(0.5)   # (1700-1500)/(1900-1500)


class TestReversed:
    def test_reversed_new_param(self):
        rc = RCModel({'RC1_REVERSED': 1})
        assert rc.normalize('roll', 2000) == pytest.approx(-1.0)
        assert rc.normalize('roll', 1000) == pytest.approx(1.0)

    def test_reversed_legacy_param(self):
        rc = RCModel({'RC1_REV': -1})
        assert rc.normalize('roll', 2000) == pytest.approx(-1.0)

    def test_reversed_throttle(self):
        rc = RCModel({'RC3_REVERSED': 1})
        assert rc.normalize('throttle', 2000) == pytest.approx(0.0)
        assert rc.normalize('throttle', 1000) == pytest.approx(1.0)

    def test_new_param_takes_precedence(self):
        rc = RCModel({'RC1_REVERSED': 0, 'RC1_REV': -1})  # REVERSED wins -> normal
        assert rc.normalize('roll', 2000) == pytest.approx(1.0)


class TestDeadzone:
    def test_deadzone_centers_small_inputs(self):
        rc = RCModel({'RC1_DZ': 30})  # trim 1500
        assert rc.normalize('roll', 1520) == pytest.approx(0.0)   # within DZ
        assert rc.normalize('roll', 1530) == pytest.approx(0.0)   # edge of DZ
        # just outside DZ -> small non-zero
        v = rc.normalize('roll', 1560)
        assert v is not None and 0.0 < v < 0.2


class TestMissingAndMalformed:
    def test_missing_pwm_returns_none(self):
        assert RCModel({}).normalize('roll', None) is None

    def test_missing_params_use_defaults(self):
        rc = RCModel({})  # nothing
        assert rc.normalize('pitch', 2000) == pytest.approx(1.0)

    def test_malformed_min_max_fall_back(self):
        # MIN >= MAX is invalid -> defaults (1000/2000)
        rc = RCModel({'RC1_MIN': 2000, 'RC1_MAX': 1000})
        assert rc.normalize('roll', 2000) == pytest.approx(1.0)
        assert rc.normalize('roll', 1000) == pytest.approx(-1.0)

    def test_malformed_string_param_ignored(self):
        rc = RCModel({'RCMAP_ROLL': 'banana', 'RC1_MIN': 'x'})
        assert rc.channel_for('roll') == 1           # fell back to default
        assert rc.normalize('roll', 2000) == pytest.approx(1.0)

    def test_nan_param_ignored(self):
        rc = RCModel({'RC1_TRIM': float('nan')})
        assert rc.normalize('roll', 1500) == pytest.approx(0.0)  # default trim 1500

    def test_trim_out_of_range_recentred(self):
        rc = RCModel({'RC1_MIN': 1000, 'RC1_MAX': 2000, 'RC1_TRIM': 3000})
        # trim invalid -> recentred to midpoint 1500
        assert rc.normalize('roll', 1500) == pytest.approx(0.0)


class TestTimeResolved:
    def _svc(self):
        from core.sample_service import SampleService
        rcin = pd.DataFrame({'TimeS': [10.0, 11.0],
                             'C1': [1500, 2000], 'C2': [1500, 1500],
                             'C3': [1000, 1500], 'C4': [1500, 1500]})
        rcou = pd.DataFrame({'TimeS': [10.0, 11.0],
                             'C1': [1500, 1800], 'C2': [1500, 1500],
                             'C3': [1100, 1600], 'C4': [1500, 1500]})
        return SampleService({'RCIN': rcin, 'RCOU': rcou})

    def test_pilot_input_state(self):
        rc = RCModel({}); svc = self._svc()
        s = rc.pilot_input(svc, 11.0)
        assert isinstance(s, StickState)
        assert s.roll == pytest.approx(1.0)        # C1 2000 -> full right
        assert s.throttle == pytest.approx(0.5)    # C3 1500 -> 0.5
        assert s.pitch == pytest.approx(0.0)

    def test_servo_output_state(self):
        rc = RCModel({}); svc = self._svc()
        s = rc.servo_output(svc, 11.0)
        assert s.roll == pytest.approx(0.6)        # C1 1800 -> 0.6
        assert s.throttle == pytest.approx(0.6)    # C3 1600 -> 0.6

    def test_out_of_range_gives_none_axis(self):
        rc = RCModel({}); svc = self._svc()
        s = rc.pilot_input(svc, 99.0)              # beyond data
        assert s.roll is None and s.throttle is None


# ── real-log validation ──────────────────────────────────────────────────────

BIN = os.path.join(os.path.dirname(__file__), '..', 'logs', '00000002.BIN')


@pytest.mark.skipif(not os.path.isfile(BIN), reason='reference log absent')
class TestRealLog:
    @pytest.fixture(scope='class')
    def ctx(self):
        from core.log_parser import DataFlashParser
        from core.sample_service import SampleService
        data = DataFlashParser().parse(BIN)
        return RCModel.from_data(data), SampleService(data), data

    def test_params_extracted(self, ctx):
        rc, svc, data = ctx
        p = params_from_data(data)
        assert p.get('RCMAP_ROLL') == 1.0
        assert p.get('RC1_MIN') == 1000.0 and p.get('RC1_MAX') == 2000.0

    def test_semantic_axes_resolve(self, ctx):
        rc, svc, data = ctx
        t = float(data['RCIN']['TimeS'].iloc[200])
        s = rc.pilot_input(svc, t)
        # all four axes resolvable and within their semantic ranges
        assert -1.0 <= s.roll <= 1.0
        assert -1.0 <= s.pitch <= 1.0
        assert -1.0 <= s.yaw <= 1.0
        assert 0.0 <= s.throttle <= 1.0

    def test_pilot_vs_output_both_available(self, ctx):
        rc, svc, data = ctx
        t = float(data['RCIN']['TimeS'].iloc[200])
        assert rc.pilot_input(svc, t).throttle is not None
        assert rc.servo_output(svc, t).roll is not None
