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
        # Sprint-1.2: stride fix parses MOTB fully (was truncated 'ThrAvM1HCH').
        cols = list(data['MOTB'].columns)
        assert cols == ['TimeUS', 'LiftMax', 'BatVolt', 'ThLimit',
                        'ThrAvMx', 'ThrOut', 'FailFlags', 'TimeS']
        assert all('\x00' not in c for c in cols)

    def test_alphabetical_ordering(self, data):
        keys = list(data.keys())
        assert keys == sorted(keys)

    def test_type_count(self, data):
        # Sprint-1.2: chunk-exclusion + FMT stride=89 recover the full catalog.
        assert len(data) == 92


# ── Sprint-1.2 corrected metrics (chunk leak + stride fixed) ─────────────────

class TestMetricsCorrected:
    def test_duration_armed_window(self, data):
        assert FlightMetrics.duration(data)[1] == '0:43'   # armed, not log span

    def test_log_span_secondary(self, data):
        assert FlightMetrics.log_span(data)[1] == '0:58'

    def test_altitude_agl(self, data):
        assert FlightMetrics.max_altitude(data)[1] == '10.0 m'  # was 199968.8

    def test_speed_real(self, data):
        assert FlightMetrics.max_speed(data)[1] == '2.5 m/s'    # was 199968.8

    def test_distance_real(self, data):
        assert FlightMetrics.distance(data)[1] == '0 m'         # was 44133.13 km

    def test_event_count_unchanged(self, data):
        assert FlightMetrics.event_count(data) == 29

    def test_mode_count_unchanged(self, data):
        assert FlightMetrics.mode_change_count(data) == 4

    def test_arm_count_unchanged(self, data):
        assert FlightMetrics.arm_count(data) == 2


# ── Parser correctness: full telemetry recovered, zero signature leakage ─────

class TestTelemetryRecovered:
    def test_no_signature_sentinel(self, data):
        SENT = 199968.765625   # float32 of bytes '1HCH'
        cells = sum(int((data[k][c] == SENT).sum())
                    for k in data for c in data[k].columns
                    if data[k][c].dtype.kind == 'f')
        assert cells == 0

    def test_core_types_present(self, data):
        for t in ('ATT', 'POS', 'RATE', 'XKF1[0]', 'XKQ[0]', 'VER', 'IMU[0]'):
            assert t in data, f'{t} missing after parser correction'

    def test_attitude_plausible(self, data):
        att = data['ATT']
        assert att['Roll'].abs().max() < 180
        assert att['Pitch'].abs().max() < 90


# ── FMT stride + chunk-exclusion: signed / unsigned / truncated coverage ─────

class TestParserCorrectness:
    def test_fmt_stride_is_89(self):
        from core.log_parser import DataFlashParser as P
        assert P.FMT_RECORD_SIZE == 89   # sizeof(log_Format) per AP_Logger

    def test_extract_signed_data_removes_chunks(self):
        # On the reference signed log, the data ranges contain no chunk magic.
        from core import signature_verifier as sv
        raw = open(BIN, 'rb').read()
        clean = sv.extract_signed_data(raw)
        assert clean is not None
        assert clean.count(b'1HCH') == 0
        assert clean.count(bytes.fromhex('31484348')) == 0   # HCH1 LE

    def test_unsigned_stream_returns_none(self):
        from core import signature_verifier as sv
        # Unsigned DataFlash (no A5 01 header) -> no chunk extraction.
        assert sv.extract_signed_data(b'\xA3\x95\x80' + b'\x00' * 200) is None

    def test_unsigned_log_still_parses(self, att_log_bytes, tmp_path):
        # Synthetic unsigned log parses via the whole-stream path unchanged.
        from core.log_parser import DataFlashParser
        p = tmp_path / 'unsigned.bin'
        p.write_bytes(att_log_bytes)
        data = DataFlashParser().parse(str(p))
        assert isinstance(data, dict)

    def test_truncated_signed_log_degrades_gracefully(self):
        # A signed log truncated mid-chunk (no END/trailer) still yields a
        # data stream from the chunk records present.
        from core import signature_verifier as sv
        raw = open(BIN, 'rb').read()
        truncated = raw[: len(raw) // 2]          # cut before END/trailer
        clean = sv.extract_signed_data(truncated)
        assert clean is not None and len(clean) > 0
        assert clean.count(b'1HCH') == 0


# ── Regression guard: filters must remain (catches accidental stash R1) ─────

class TestFiltersPreserved:
    def test_filter_block_present(self):
        src = open(os.path.join(os.path.dirname(__file__), '..',
                                'core', 'log_parser.py')).read()
        assert '3e11' in src, 'TimeUS bound removed — possible R1 regression'
        assert 'FIELD_BOUNDS[col]' in src, 'FIELD_BOUNDS clamp removed'
        assert '1e9' in src, '1e9 magnitude gate removed'
        assert '1e15' not in src, 'stash 1e15 filter must NOT be present'
