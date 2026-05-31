"""Unit tests for core/log_parser.py."""
import struct
import pytest
import numpy as np

from core.log_parser import (
    _build_fmt_struct, get_instance_col, is_valid_instance,
    DataFlashParser, FIELD_BOUNDS,
)
from tests.helpers import (
    make_fmt_record, make_data_record,
    make_att_fmt, make_att_record,
    make_escx_fmt, make_escx_record,
    ATT_TYPE, ATT_MSG_LEN,
    ESCX_TYPE, ESCX_MSG_LEN,
)


# ── _build_fmt_struct ─────────────────────────────────────────────────────────

class TestBuildFmtStruct:
    def test_integer_types(self):
        s, sizes, scales = _build_fmt_struct('biI')
        assert s is not None
        assert s.size == 1 + 4 + 4
        assert scales == ['b', 'i', 'I']

    def test_scale_types(self):
        s, sizes, scales = _build_fmt_struct('qcC')
        assert s is not None
        assert s.size == 8 + 2 + 2
        assert scales == ['q', 'c', 'C']

    def test_float_types(self):
        s, sizes, scales = _build_fmt_struct('fd')
        assert s is not None
        assert s.size == 4 + 8

    def test_string_types(self):
        s, sizes, scales = _build_fmt_struct('nNZ')
        assert s is not None
        assert s.size == 4 + 16 + 64

    def test_unknown_char_returns_none(self):
        s, sizes, scales = _build_fmt_struct('qXf')
        assert s is None
        assert sizes is None
        assert scales is None

    def test_empty_string(self):
        s, sizes, scales = _build_fmt_struct('')
        assert s is not None
        assert s.size == 0


# ── get_instance_col ──────────────────────────────────────────────────────────

class TestGetInstanceCol:
    def test_detects_I(self):
        assert get_instance_col(['TimeUS', 'I', 'Value']) == 'I'

    def test_detects_Instance(self):
        assert get_instance_col(['TimeUS', 'Instance', 'Value']) == 'Instance'

    def test_detects_IMU(self):
        assert get_instance_col(['TimeUS', 'IMU', 'AccX']) == 'IMU'

    def test_returns_none_when_absent(self):
        assert get_instance_col(['TimeUS', 'Roll', 'Pitch', 'Yaw']) is None

    def test_empty_list(self):
        assert get_instance_col([]) is None


# ── is_valid_instance ─────────────────────────────────────────────────────────

class TestIsValidInstance:
    def test_escx_valid(self):
        assert is_valid_instance('ESCX', 0) is True
        assert is_valid_instance('ESCX', 11) is True

    def test_escx_out_of_range(self):
        assert is_valid_instance('ESCX', 12) is False
        assert is_valid_instance('ESCX', -1) is False

    def test_imu_valid(self):
        assert is_valid_instance('IMU', 0) is True
        assert is_valid_instance('IMU', 3) is True

    def test_imu_out_of_range(self):
        assert is_valid_instance('IMU', 4) is False

    def test_unknown_type_uses_default_0_to_15(self):
        assert is_valid_instance('UNKNOWN', 0) is True
        assert is_valid_instance('UNKNOWN', 15) is True
        assert is_valid_instance('UNKNOWN', 16) is False


# ── DataFlashParser ───────────────────────────────────────────────────────────

class TestDataFlashParser:
    def test_att_records_parsed(self, tmp_path, att_log_bytes):
        path = tmp_path / 'test.bin'
        path.write_bytes(att_log_bytes)
        result = DataFlashParser().parse(str(path))

        assert 'ATT' in result
        df = result['ATT']
        assert len(df) == 3
        assert set(['Roll', 'Pitch', 'Yaw', 'TimeUS', 'TimeS']).issubset(df.columns)

    def test_scale_c_divides_by_100(self, tmp_path, att_log_bytes):
        path = tmp_path / 'test.bin'
        path.write_bytes(att_log_bytes)
        df = DataFlashParser().parse(str(path))['ATT']
        assert abs(float(df['Roll'].iloc[0]) - 1.5) < 0.01
        assert abs(float(df['Pitch'].iloc[0]) - (-0.5)) < 0.01
        assert abs(float(df['Yaw'].iloc[0]) - 90.0) < 0.01

    def test_time_us_converted_to_seconds(self, tmp_path, att_log_bytes):
        path = tmp_path / 'test.bin'
        path.write_bytes(att_log_bytes)
        df = DataFlashParser().parse(str(path))['ATT']
        assert abs(float(df['TimeS'].iloc[0]) - 40.0) < 0.01
        assert abs(float(df['TimeS'].iloc[1]) - 41.0) < 0.01

    def test_instanced_messages_split_by_key(self, tmp_path, escx_log_bytes):
        path = tmp_path / 'test.bin'
        path.write_bytes(escx_log_bytes)
        result = DataFlashParser().parse(str(path))
        assert 'ESCX[0]' in result
        assert 'ESCX[1]' in result
        assert 'ESCX' not in result

    def test_instance_column_dropped_from_dataframe(self, tmp_path, escx_log_bytes):
        path = tmp_path / 'test.bin'
        path.write_bytes(escx_log_bytes)
        result = DataFlashParser().parse(str(path))
        # 'I' is the instance column — it must not appear in the output DataFrame
        assert 'I' not in result['ESCX[0]'].columns
        assert 'I' not in result['ESCX[1]'].columns

    def test_instance_row_counts(self, tmp_path, escx_log_bytes):
        path = tmp_path / 'test.bin'
        path.write_bytes(escx_log_bytes)
        result = DataFlashParser().parse(str(path))
        assert len(result['ESCX[0]']) == 2
        assert len(result['ESCX[1]']) == 2

    def test_escx_outpct_scaling(self, tmp_path, escx_log_bytes):
        path = tmp_path / 'test.bin'
        path.write_bytes(escx_log_bytes)
        result = DataFlashParser().parse(str(path))
        val = float(result['ESCX[0]']['outpct'].iloc[0])
        assert abs(val - 50.0) < 0.01

    def test_zero_timestamp_filtered(self, tmp_path):
        data = (
            make_att_fmt()
            + make_att_record(0, 1.0, 0.0, 0.0)           # TimeUS=0 → filtered
            + make_att_record(40_000_000, 2.0, 0.5, 90.0)  # kept
        )
        path = tmp_path / 'test.bin'
        path.write_bytes(data)
        df = DataFlashParser().parse(str(path))['ATT']
        assert len(df) == 1
        assert abs(float(df['Roll'].iloc[0]) - 2.0) < 0.01

    def test_extreme_timestamp_filtered(self, tmp_path):
        data = (
            make_att_fmt()
            + make_att_record(400_000_000, 1.0, 0.0, 0.0)  # TimeUS > 3e8 → filtered
            + make_att_record(40_000_000, 2.0, 0.5, 90.0)   # kept
        )
        path = tmp_path / 'test.bin'
        path.write_bytes(data)
        df = DataFlashParser().parse(str(path))['ATT']
        assert len(df) == 1

    def test_field_bounds_out_of_range_becomes_nan(self, tmp_path):
        # Roll = 200.0 exceeds FIELD_BOUNDS['Roll'] = (-180, 180)
        # Pitch = 5.0 is within FIELD_BOUNDS['Pitch'] = (-90, 90)
        S = struct.Struct('<qhh')
        msg_len = 3 + S.size
        fmt = make_fmt_record(20, msg_len, 'ATT', 'qcc', 'TimeUS,Roll,Pitch')
        body = S.pack(40_000_000, 20000, 500)  # Roll=200.0 (OOB), Pitch=5.0
        rec = make_data_record(20, body)
        path = tmp_path / 'test.bin'
        path.write_bytes(fmt + rec)
        result = DataFlashParser().parse(str(path))
        assert 'ATT' in result
        df = result['ATT']
        assert np.isnan(float(df['Roll'].iloc[0]))
        assert not np.isnan(float(df['Pitch'].iloc[0]))

    def test_invalid_format_char_message_skipped(self, tmp_path):
        # 'X' is not a valid format char → _build_fmt_struct returns None → type ignored
        fmt = make_fmt_record(21, 10, 'BAD', 'qXf', 'TimeUS,Unknown,Val')
        S = struct.Struct('<qf')
        rec = make_data_record(21, S.pack(40_000_000, 1.0))
        path = tmp_path / 'test.bin'
        path.write_bytes(fmt + rec)
        result = DataFlashParser().parse(str(path))
        assert 'BAD' not in result

    def test_signed_log_skips_64_byte_header(self, tmp_path):
        # Parser detects 0xA5 0x01 magic and skips 64 bytes before parsing
        header = bytes([0xA5, 0x01]) + b'\x00' * 62  # 64-byte signed header
        data = header + make_att_fmt() + make_att_record(40_000_000, 1.5, -0.5, 90.0)
        path = tmp_path / 'test.bin'
        path.write_bytes(data)
        result = DataFlashParser().parse(str(path))
        assert 'ATT' in result
        assert len(result['ATT']) == 1

    def test_multiple_message_types_coexist(self, tmp_path):
        data = make_att_fmt() + make_escx_fmt()
        data += make_att_record(40_000_000, 1.5, -0.5, 90.0)
        data += make_escx_record(40_000_000, 0, 55.0)
        path = tmp_path / 'test.bin'
        path.write_bytes(data)
        result = DataFlashParser().parse(str(path))
        assert 'ATT' in result
        assert 'ESCX[0]' in result

    def test_empty_file_returns_empty_dict(self, tmp_path):
        path = tmp_path / 'empty.bin'
        path.write_bytes(b'')
        result = DataFlashParser().parse(str(path))
        assert result == {}

    def test_garbage_bytes_returns_empty_dict(self, tmp_path):
        path = tmp_path / 'garbage.bin'
        path.write_bytes(b'\xDE\xAD\xBE\xEF' * 50)
        result = DataFlashParser().parse(str(path))
        assert result == {}
