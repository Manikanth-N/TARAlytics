"""Tests for core.sample_service.SampleService (the shared-cursor engine)."""
import os
import math
import numpy as np
import pandas as pd
import pytest

from core.sample_service import SampleService


def _df(times, **cols):
    d = {'TimeS': np.asarray(times, dtype=float)}
    for k, v in cols.items():
        d[k] = np.asarray(v, dtype=float)
    return pd.DataFrame(d)


@pytest.fixture
def svc():
    data = {
        'ATT': _df([10.0, 11.0, 12.0], Roll=[0.0, 10.0, 20.0], DesRoll=[0.0, 5.0, 5.0]),
        'MODE': _df([10.0, 11.5], ModeNum=[0.0, 4.0]),
        'NAN': _df([10.0, 11.0, 12.0], X=[0.0, float('nan'), 4.0]),
        'UNSORTED': _df([12.0, 10.0, 11.0], V=[20.0, 0.0, 10.0]),
        'EMPTY': pd.DataFrame({'TimeS': [], 'X': []}),
    }
    return SampleService(data)


class TestValueAt:
    def test_exact_sample(self, svc):
        assert svc.value_at('ATT', 'Roll', 11.0) == 10.0

    def test_linear_interpolation(self, svc):
        # midpoint between (11,10) and (12,20) -> 15
        assert svc.value_at('ATT', 'Roll', 11.5) == pytest.approx(15.0)
        # quarter point
        assert svc.value_at('ATT', 'Roll', 11.25) == pytest.approx(12.5)

    def test_below_range_returns_none(self, svc):
        assert svc.value_at('ATT', 'Roll', 9.9) is None

    def test_above_range_returns_none(self, svc):
        assert svc.value_at('ATT', 'Roll', 12.1) is None

    def test_endpoints(self, svc):
        assert svc.value_at('ATT', 'Roll', 10.0) == 0.0
        assert svc.value_at('ATT', 'Roll', 12.0) == 20.0

    def test_missing_message(self, svc):
        assert svc.value_at('NOPE', 'Roll', 11.0) is None

    def test_missing_column(self, svc):
        assert svc.value_at('ATT', 'Nope', 11.0) is None

    def test_empty_message(self, svc):
        assert svc.value_at('EMPTY', 'X', 11.0) is None


class TestNaN:
    def test_nan_neighbour_uses_other(self, svc):
        # NAN.X at t=10.5 brackets (10,0.0) and (11,nan) -> returns 0.0
        assert svc.value_at('NAN', 'X', 10.5) == 0.0
        # at t=11.5 brackets (11,nan) and (12,4.0) -> returns 4.0
        assert svc.value_at('NAN', 'X', 11.5) == 4.0

    def test_exact_nan_sample_falls_back(self, svc):
        # exact hit on the NaN sample: should not return NaN
        v = svc.value_at('NAN', 'X', 11.0)
        assert v is None or not math.isnan(v)


class TestUnsorted:
    def test_unsorted_times_are_handled(self, svc):
        # UNSORTED defined out of order; interpolation must still be correct
        assert svc.value_at('UNSORTED', 'V', 10.5) == pytest.approx(5.0)
        assert svc.value_at('UNSORTED', 'V', 11.5) == pytest.approx(15.0)


class TestLatestAt:
    def test_step_hold(self, svc):
        assert svc.latest_at('MODE', 'ModeNum', 10.0) == 0.0
        assert svc.latest_at('MODE', 'ModeNum', 11.0) == 0.0   # before the change
        assert svc.latest_at('MODE', 'ModeNum', 11.5) == 4.0
        assert svc.latest_at('MODE', 'ModeNum', 99.0) == 4.0   # holds last

    def test_before_first_is_none(self, svc):
        assert svc.latest_at('MODE', 'ModeNum', 9.0) is None


class TestBatchAndRange:
    def test_batch_labels(self, svc):
        out = svc.batch(11.5, [('roll', 'ATT', 'Roll'), ('ATT', 'DesRoll')])
        assert out['roll'] == pytest.approx(15.0)
        assert out['ATT.DesRoll'] == pytest.approx(5.0)

    def test_batch_step(self, svc):
        out = svc.batch(11.5, [('mode', 'MODE', 'ModeNum')], step=True)
        assert out['mode'] == 4.0

    def test_time_range(self, svc):
        assert svc.time_range('ATT') == (10.0, 12.0)
        assert svc.time_range('NOPE') is None

    def test_index_at(self, svc):
        assert svc.index_at('ATT', 11.4) == 1
        assert svc.index_at('ATT', 9.0) is None


# ── Real-log accuracy: SampleService must match a manual interpolation ───────

BIN = os.path.join(os.path.dirname(__file__), '..', 'logs', '00000002.BIN')


@pytest.mark.skipif(not os.path.isfile(BIN), reason='reference log absent')
class TestRealLog:
    @pytest.fixture(scope='class')
    def real(self):
        from core.log_parser import DataFlashParser
        data = DataFlashParser().parse(BIN)
        return SampleService(data), data

    def test_matches_manual_interp(self, real):
        svc, data = real
        att = data['ATT'].sort_values('TimeS').reset_index(drop=True)
        t = float(att['TimeS'].iloc[100]) + 0.5 * (
            float(att['TimeS'].iloc[101]) - float(att['TimeS'].iloc[100]))
        manual = np.interp(t, att['TimeS'].values, att['Roll'].values)
        assert svc.value_at('ATT', 'Roll', t) == pytest.approx(manual, abs=1e-6)

    def test_desired_and_actual_available(self, real):
        svc, data = real
        t = float(data['ATT']['TimeS'].iloc[300])
        assert svc.value_at('ATT', 'Roll', t) is not None
        assert svc.value_at('ATT', 'DesRoll', t) is not None
