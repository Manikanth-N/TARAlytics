"""
Sprint-1.1 parser-quality regression tests.

Locks in the SAFE structural fixes (PID I-term, MOTB columns, alphabetical
ordering) and guards the success criteria: flight metrics must NOT change.

Requires the bundled test log logs/00000002.BIN.
"""
import os
import pytest

from core.log_parser import DataFlashParser
from core.flight_metrics import FlightMetrics
from core.health_analyzer import HealthAnalyzer

BIN = os.path.join(os.path.dirname(__file__), '..', 'logs', '00000002.BIN')
pytestmark = pytest.mark.skipif(not os.path.isfile(BIN),
                                reason='logs/00000002.BIN not present')


@pytest.fixture(scope='module')
def data():
    return DataFlashParser().parse(BIN)


# ── Structural fixes (intended changes) ─────────────────────────────────────

class TestStructuralFixes:
    def test_pid_tables_unified(self, data):
        # PID I-term fix: float 'I' no longer treated as instance index.
        assert 'PIDR' in data and 'PIDY' in data and 'PIDE' in data
        for inst_key in ('PIDR[0]', 'PIDY[0]', 'PIDE[0]', 'PIDE[5]'):
            assert inst_key not in data

    def test_pid_integral_column_restored(self, data):
        for name in ('PIDR', 'PIDY', 'PIDE'):
            assert 'I' in data[name].columns
            assert data[name]['I'].dtype.kind == 'f'  # float integral term

    def test_motb_columns_clean(self, data):
        cols = list(data['MOTB'].columns)
        assert cols == ['TimeUS', 'LiftMax', 'BatVolt', 'ThLimit',
                        'ThrAvM1HCH', 'TimeS']
        assert all('\x00' not in c for c in cols)

    def test_alphabetical_ordering(self, data):
        keys = list(data.keys())
        assert keys == sorted(keys)

    def test_type_count(self, data):
        assert len(data) == 59


# ── Success criteria (metrics must stay UNCHANGED vs pre-Sprint-1.1) ─────────

class TestMetricsUnchanged:
    def test_duration_unchanged(self, data):
        assert FlightMetrics.duration(data)[1] == '0:58'

    def test_altitude_unchanged(self, data):
        assert FlightMetrics.max_altitude(data)[1] == '199968.8 m'

    def test_speed_unchanged(self, data):
        assert FlightMetrics.max_speed(data)[1] == '199968.8 m/s'

    def test_distance_unchanged(self, data):
        assert FlightMetrics.distance(data)[1] == '44133.13 km'

    def test_event_count_unchanged(self, data):
        assert FlightMetrics.event_count(data) == 29

    def test_mode_count_unchanged(self, data):
        assert FlightMetrics.mode_change_count(data) == 4

    def test_arm_count_unchanged(self, data):
        assert FlightMetrics.arm_count(data) == 2

    def test_gps_sitl_unchanged(self, data):
        assert HealthAnalyzer.gps(data)['is_sitl'] is True


# ── Regression guard: filters must remain (catches accidental stash R1) ─────

class TestFiltersPreserved:
    def test_filter_block_present(self):
        src = open(os.path.join(os.path.dirname(__file__), '..',
                                'core', 'log_parser.py')).read()
        assert '3e11' in src, 'TimeUS bound removed — possible R1 regression'
        assert 'FIELD_BOUNDS[col]' in src, 'FIELD_BOUNDS clamp removed'
        assert '1e9' in src, '1e9 magnitude gate removed'
        assert '1e15' not in src, 'stash 1e15 filter must NOT be present'
