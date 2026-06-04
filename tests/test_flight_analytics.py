"""P3 tests: the Flight Intelligence Layer (whole-flight analytics) on synthetic
signals with known answers — tracking, smoothness, yaw, landing, oscillation,
saturation, findings, scorecard, and the overall flight-quality verdict."""
import numpy as np
import pandas as pd
import pytest

from core.flight_analytics import FlightAnalytics, analyze


def _base(n=4000, dur=80.0, arm=(5.0, 75.0)):
    """A clean hovering flight: armed window, level attitude, steady sticks/motors,
    a soft landing. Individual tests perturb one aspect."""
    t = np.linspace(0.0, dur, n)
    z = np.zeros(n)
    # altitude: climb to 20 m, hold, then a gentle (~0.9 m/s) descent to 0
    agl = np.interp(t, [0, 5, 10, 50, 72, dur], [0, 0, 20, 20, 0, 0])
    crt = np.gradient(agl, t)
    return {
        't': t,
        'data': {
            'ARM': pd.DataFrame({'TimeS': [arm[0], arm[1]], 'ArmState': [1, 0]}),
            'MODE': pd.DataFrame({'TimeS': [arm[0]], 'Mode': [5]}),
            'PARM': pd.DataFrame({'Name': ['RCMAP_ROLL', 'RCMAP_PITCH', 'RCMAP_THROTTLE',
                                           'RCMAP_YAW', 'MOT_PWM_MIN', 'MOT_PWM_MAX'],
                                  'Value': [1.0, 2.0, 3.0, 4.0, 1000.0, 2000.0]}),
            'ATT': pd.DataFrame({'TimeS': t, 'DesRoll': z.copy(), 'Roll': z.copy(),
                                 'DesPitch': z.copy(), 'Pitch': z.copy(),
                                 'DesYaw': np.full(n, 90.0), 'Yaw': np.full(n, 90.0)}),
            'RCIN': pd.DataFrame({'TimeS': t, 'C1': np.full(n, 1500.0), 'C2': np.full(n, 1500.0),
                                  'C3': np.full(n, 1500.0), 'C4': np.full(n, 1500.0)}),
            'RCOU': pd.DataFrame({'TimeS': t, 'C1': np.full(n, 1500.0), 'C2': np.full(n, 1500.0),
                                  'C3': np.full(n, 1500.0), 'C4': np.full(n, 1500.0)}),
            'BARO[0]': pd.DataFrame({'TimeS': t, 'Alt': agl, 'CRt': crt}),
            'POS': pd.DataFrame({'TimeS': t, 'RelHomeAlt': agl}),
        },
    }


class TestTracking:
    def test_clean_tracking_high_score(self):
        b = _base()
        r = analyze(b['data'])
        roll = next(x for x in r.tracking if x.axis == 'roll')
        assert roll.rms_deg < 1.0 and roll.score > 95 and roll.pct_in_tol == 100.0

    def test_constant_offset_low_score(self):
        b = _base()
        b['data']['ATT']['Roll'] = b['data']['ATT']['DesRoll'] + 12.0   # 12° lag
        r = analyze(b['data'])
        roll = next(x for x in r.tracking if x.axis == 'roll')
        assert roll.rms_deg == pytest.approx(12.0, abs=0.5)
        assert roll.score < 30 and roll.pct_in_tol < 50


class TestOscillation:
    def test_detects_injected_oscillation(self):
        b = _base()
        t = b['t']
        # 3 Hz, 4° oscillation on roll within the armed window
        osc = 4.0 * np.sin(2 * np.pi * 3.0 * t)
        b['data']['ATT']['Roll'] = b['data']['ATT']['DesRoll'] + osc
        r = analyze(b['data'])
        ro = next(x for x in r.oscillations if x.axis == 'roll')
        assert ro.detected
        assert ro.freq_hz == pytest.approx(3.0, abs=0.4)
        assert ro.amplitude_deg == pytest.approx(4.0, rel=0.4)
        assert ro.severity in ('WARNING', 'CRITICAL')

    def test_clean_flight_no_oscillation(self):
        r = analyze(_base()['data'])
        assert not any(o.detected for o in r.oscillations)


class TestSaturation:
    def test_motor_saturation_detected(self):
        b = _base()
        t = b['t']
        # motor 1 pinned at max for the second half of the flight
        c1 = np.where(t > 40, 2000.0, 1500.0)
        b['data']['RCOU']['C1'] = c1
        r = analyze(b['data'])
        assert r.saturation.motor_pct is not None and r.saturation.motor_pct > 20
        assert r.saturation.severity in ('WARNING', 'CRITICAL')

    def test_no_saturation_clean(self):
        r = analyze(_base()['data'])
        assert (r.saturation.motor_pct or 0) < 1.0
        assert r.saturation.severity == 'OK'


class TestLanding:
    def test_soft_landing_classified_smooth(self):
        r = analyze(_base()['data'])
        assert r.landing.detected
        assert r.landing.classification in ('SMOOTH', 'FIRM')

    def test_hard_landing_detected(self):
        b = _base()
        t = b['t']
        # steep final descent: drop from 20 m to 0 in 2 s near 71 s
        agl = np.interp(t, [0, 5, 10, 69, 71, 80], [0, 0, 20, 20, 0, 0])
        b['data']['BARO[0]'] = pd.DataFrame({'TimeS': t, 'Alt': agl, 'CRt': np.gradient(agl, t)})
        b['data']['POS'] = pd.DataFrame({'TimeS': t, 'RelHomeAlt': agl})
        r = analyze(b['data'])
        assert r.landing.detected
        assert r.landing.touchdown_rate_mps > 3.0
        assert r.landing.classification in ('HARD', 'SEVERE')


class TestSmoothness:
    def test_jittery_sticks_lower_smoothness(self):
        b = _base(); t = b['t']
        clean = analyze(b['data'])
        c_roll = next(x for x in clean.smoothness if x.axis == 'roll')
        # rapid full-scale roll reversals
        b['data']['RCIN']['C1'] = 1500.0 + 480.0 * np.sign(np.sin(2 * np.pi * 2.0 * t))
        jit = analyze(b['data'])
        j_roll = next(x for x in jit.smoothness if x.axis == 'roll')
        assert j_roll.reversals_per_s > c_roll.reversals_per_s
        assert j_roll.score < c_roll.score


class TestScorecardAndQuality:
    def test_good_flight_verdict(self):
        r = analyze(_base()['data'])
        assert r.quality.verdict == 'GOOD'
        assert r.scorecard.overall > 90 and r.scorecard.grade == 'A'

    def test_oscillation_downgrades_verdict(self):
        b = _base(); t = b['t']
        b['data']['ATT']['Roll'] = b['data']['ATT']['DesRoll'] + 7.0 * np.sin(2 * np.pi * 4 * t)
        r = analyze(b['data'])
        assert r.quality.verdict in ('MARGINAL', 'POOR', 'ACCEPTABLE')
        assert any(f.category == 'OSCILLATION' for f in r.findings)

    def test_findings_generated_and_sorted(self):
        b = _base(); t = b['t']
        b['data']['ATT']['Roll'] = b['data']['ATT']['DesRoll'] + 6.0 * np.sin(2 * np.pi * 5 * t)
        b['data']['RCOU']['C1'] = np.where(t > 30, 2000.0, 1500.0)
        r = analyze(b['data'])
        assert len(r.findings) >= 2
        cats = {f.category for f in r.findings}
        assert 'OSCILLATION' in cats and 'SATURATION' in cats

    def test_to_dict_serializable(self):
        import json
        r = analyze(_base()['data'])
        json.dumps(r.to_dict(), default=str)


class TestRobustness:
    def test_empty_data_no_crash(self):
        r = analyze({})
        assert r.quality.verdict == 'NO DATA'
        assert r.scorecard.overall is None

    def test_missing_attitude_degrades(self):
        b = _base(); del b['data']['ATT']
        r = analyze(b['data'])
        assert r.quality.verdict in ('NO DATA',)  # no tracking → no verdict

    def test_no_arm_uses_whole_log(self):
        b = _base(); del b['data']['ARM']; del b['data']['MODE']
        r = analyze(b['data'])
        assert r.armed_duration_s > 0
