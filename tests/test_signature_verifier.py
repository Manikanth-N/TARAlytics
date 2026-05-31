"""Unit tests for core/signature_verifier.py."""
import struct
import pytest

from core.signature_verifier import (
    check_structure, compute_hashes, parse_header,
    check_fingerprint, full_verify, load_pubkey_file,
    SIGNED_MAGIC, TRAILER_MAGIC, TRAILER_SIZE,
)
from tests.helpers import minimal_signed_log


# ── check_structure ───────────────────────────────────────────────────────────

class TestCheckStructure:
    def test_unsigned_log_returns_false(self):
        ok, msg = check_structure(b'\xA3\x95' + b'\x00' * 200)
        assert ok is False
        assert 'Not a signed log' in msg

    def test_too_small_returns_false(self):
        ok, msg = check_structure(SIGNED_MAGIC + b'\x00' * 10)
        assert ok is False

    def test_missing_trailer_magic_returns_false(self):
        raw = SIGNED_MAGIC + b'\x00' * 200
        ok, msg = check_structure(raw)
        assert ok is False
        assert 'Trailer magic missing' in msg

    def test_corrupt_structure_returns_false(self):
        # Valid header + valid trailer magic but wrong data lengths
        header = bytearray(64)
        header[0:2] = SIGNED_MAGIC
        trailer = bytearray(TRAILER_SIZE)
        trailer[0:4] = TRAILER_MAGIC
        struct.pack_into('<I', trailer, 4, 999)   # data_len that doesn't match
        struct.pack_into('<I', trailer, 8, 64)    # data_start
        raw = bytes(header) + b'\x00' * 50 + bytes(trailer)
        ok, msg = check_structure(raw)
        assert ok is False
        assert 'CORRUPT' in msg

    def test_valid_structure_returns_true(self, signed_log_bytes):
        ok, msg = check_structure(signed_log_bytes)
        assert ok is True
        assert 'intact' in msg.lower()

    def test_structure_message_includes_range(self, signed_log_bytes):
        ok, msg = check_structure(signed_log_bytes)
        assert '64' in msg  # data_start = 64


# ── parse_header ──────────────────────────────────────────────────────────────

class TestParseHeader:
    def test_unsigned_log_returns_empty_dict(self):
        result = parse_header(b'\xA3\x95' + b'\x00' * 200)
        assert result == {}

    def test_too_short_returns_empty_dict(self):
        result = parse_header(b'\xA5' + b'\x00' * 10)
        assert result == {}

    def test_signed_header_parsed(self, signed_log_bytes):
        result = parse_header(signed_log_bytes)
        assert 'version' in result
        assert 'algorithm' in result
        assert 'algo_name' in result
        assert result['algorithm'] == 2  # BLAKE2B

    def test_algo_name_populated(self, signed_log_bytes):
        result = parse_header(signed_log_bytes)
        assert 'Blake2b' in result['algo_name'] or 'blake' in result['algo_name'].lower()


# ── compute_hashes ────────────────────────────────────────────────────────────

class TestComputeHashes:
    def test_hashes_present(self, signed_log_bytes):
        h = compute_hashes(signed_log_bytes)
        assert 'sha256_signed' in h
        assert 'sha256_full' in h
        assert 'header_mac' in h
        assert 'key_id' in h
        assert 'data_start' in h
        assert 'data_len' in h

    def test_sha256_is_hex_string(self, signed_log_bytes):
        h = compute_hashes(signed_log_bytes)
        assert len(h['sha256_signed']) == 64
        assert all(c in '0123456789abcdef' for c in h['sha256_signed'])

    def test_data_start_matches_header(self, signed_log_bytes):
        h = compute_hashes(signed_log_bytes)
        assert h['data_start'] == 64

    def test_data_len_matches_payload(self, signed_log_bytes):
        h = compute_hashes(signed_log_bytes)
        assert h['data_len'] == 100  # payload size in minimal_signed_log()


# ── full_verify ───────────────────────────────────────────────────────────────

class TestFullVerify:
    def test_unsigned_log_state(self):
        result = full_verify(b'\xA3\x95' + b'\x00' * 200)
        assert result['state'] == 'NOT_SIGNED'

    def test_no_pubkey_state(self, signed_log_bytes):
        result = full_verify(signed_log_bytes, pubkey_b64=None)
        assert result['state'] == 'UNVERIFIED'
        assert 'No public key' in result['detail']

    def test_structure_error_state(self):
        # Signed magic but no valid trailer → STRUCTURE_ERROR
        raw = SIGNED_MAGIC + b'\x00' * 200
        result = full_verify(raw, pubkey_b64=None)
        assert result['state'] == 'STRUCTURE_ERROR'

    def test_valid_structure_parsed(self, signed_log_bytes):
        result = full_verify(signed_log_bytes, pubkey_b64=None)
        assert result['structure_ok'] is True

    def test_wrong_key_gives_key_mismatch(self, signed_log_bytes):
        import base64
        fake_key = base64.b64encode(b'\x00' * 32).decode()
        result = full_verify(signed_log_bytes, pubkey_b64=f'PUBLIC_KEYV1:{fake_key}')
        # With our minimal log (no valid hash chain), should be KEY_MISMATCH or TAMPERED
        assert result['state'] in ('KEY_MISMATCH', 'TAMPERED', 'UNVERIFIED')

    def test_result_always_has_required_keys(self, signed_log_bytes):
        result = full_verify(signed_log_bytes, pubkey_b64=None)
        for key in ('state', 'detail', 'structure_ok', 'hashes', 'header_info'):
            assert key in result


# ── load_pubkey_file ──────────────────────────────────────────────────────────

class TestLoadPubkeyFile:
    def test_missing_file_returns_none(self):
        result = load_pubkey_file('/nonexistent/path/key.dat')
        assert result is None

    def test_valid_file_returns_string(self, tmp_path):
        key = 'PUBLIC_KEYV1:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA='
        keyfile = tmp_path / 'test.dat'
        keyfile.write_text(key + '\n')
        result = load_pubkey_file(str(keyfile))
        assert result == key  # stripped

    def test_file_content_stripped(self, tmp_path):
        keyfile = tmp_path / 'test.dat'
        keyfile.write_text('  some_key_value  \n  ')
        result = load_pubkey_file(str(keyfile))
        assert result == 'some_key_value'
