"""Verification classification regression tests (operational state model).

Covers the seven approved operational states end-to-end through the engine, plus the
centralized core.verification_model. Real-log scenarios (complete / truncated signed
logs) use the bundled logs and the SN-01 public key; they skip cleanly if absent.
"""
import os
import base64
import struct
import pytest

from core.signature_verifier import full_verify, load_pubkey_file, SIGNED_MAGIC
from core import verification_model as vmodel

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_KEY_FILE = os.path.join(_ROOT, 'SN-01_log_public_key.dat')
_LOG_COMPLETE = os.path.join(_ROOT, 'logs', '00000002.BIN')   # signed + closed
_LOG_TRUNCATED = os.path.join(_ROOT, 'logs', '00000011.BIN')  # signed, power-loss


def _key():
    if not os.path.isfile(_KEY_FILE):
        pytest.skip('SN-01 public key not present')
    return load_pubkey_file(_KEY_FILE)


def _read(path):
    if not os.path.isfile(path):
        pytest.skip(f'{os.path.basename(path)} not present')
    with open(path, 'rb') as f:
        return f.read()


# ── The seven operational scenarios ───────────────────────────────────────────

class TestOperationalStates:
    def test_1_complete_signed_log_is_verified(self):
        raw = _read(_LOG_COMPLETE)
        r = full_verify(raw, _key())
        assert r['state'] == vmodel.VERIFIED
        assert r['chain_ok'] is True and r['closed'] is True

    def test_2_truncated_signed_log_is_partial(self):
        raw = _read(_LOG_TRUNCATED)
        r = full_verify(raw, _key())
        assert r['state'] == vmodel.PARTIAL
        assert r['chain_valid'] is True     # every written chunk is intact
        assert r['closed'] is False         # END record never written
        assert r['chain_chunks'] > 0

    def test_2b_truncated_is_partial_even_without_key(self):
        # PARTIAL is determinable from the keyless hash chain alone.
        raw = _read(_LOG_TRUNCATED)
        assert full_verify(raw, None)['state'] == vmodel.PARTIAL

    def test_3_signed_log_without_key_is_unknown(self):
        raw = _read(_LOG_COMPLETE)
        r = full_verify(raw, None)
        assert r['state'] == vmodel.UNKNOWN
        assert 'No public key' in r['detail']

    def test_4_signed_log_with_wrong_key_is_wrong_key(self):
        raw = _read(_LOG_COMPLETE)
        _key()  # ensure key infra present / consistent skip
        wrong = 'PUBLIC_KEYV1:' + base64.b64encode(bytes(range(32))).decode()
        r = full_verify(raw, wrong)
        assert r['state'] in (vmodel.WRONG_KEY, vmodel.INVALID)

    def test_5_unsigned_log_is_unsigned(self):
        # Standard unsigned DataFlash stream (A3 95 …), not an error.
        r = full_verify(b'\xA3\x95' + b'\x00' * 500, None)
        assert r['state'] == vmodel.UNSIGNED

    def test_6_hash_chain_modification_is_invalid(self):
        raw = bytearray(_read(_LOG_COMPLETE))
        key = _key()
        assert full_verify(bytes(raw), key)['state'] == vmodel.VERIFIED   # baseline
        # Flip a 64-byte run in the middle of the signed data → breaks a chunk hash.
        mid = len(raw) // 2
        for i in range(mid, mid + 64):
            raw[i] ^= 0xFF
        r = full_verify(bytes(raw), key)
        assert r['chain_valid'] is False
        assert r['state'] == vmodel.INVALID

    def test_7_malformed_structure_is_corrupted(self):
        # Signed magic but no chunks and no readable trailer → integrity undeterminable.
        r = full_verify(SIGNED_MAGIC + b'\x00' * 300, None)
        assert r['state'] == vmodel.CORRUPTED


# ── Centralized model ─────────────────────────────────────────────────────────

class TestVerificationModel:
    def test_every_state_has_full_copy(self):
        for s in vmodel.ALL_STATES:
            i = vmodel.info(s)
            assert i.label and i.color and i.tone
            assert i.operational_meaning and i.investigator_guidance

    def test_legacy_states_normalize(self):
        assert vmodel.normalize_state('STRUCTURE_ERROR') == vmodel.CORRUPTED
        assert vmodel.normalize_state('TAMPERED') == vmodel.INVALID
        assert vmodel.normalize_state('KEY_MISMATCH') == vmodel.WRONG_KEY
        assert vmodel.normalize_state('NOT_SIGNED') == vmodel.UNSIGNED
        assert vmodel.normalize_state('UNVERIFIED') == vmodel.UNKNOWN
        assert vmodel.normalize_state('NOT_LOADED') == vmodel.UNKNOWN
        assert vmodel.normalize_state('') == vmodel.UNKNOWN
        assert vmodel.normalize_state('anything-weird') == vmodel.UNKNOWN

    def test_partial_basis_mentions_interruption(self):
        result = {'state': vmodel.PARTIAL, 'chain_chunks': 48705, 'chain_valid': True,
                  'closed': False, 'algo_name': 'Blake2b-256 + Ed25519-Blake2b'}
        basis = vmodel.verification_basis(result)
        joined = ' '.join(basis)
        assert '48,705' in joined
        assert 'END record not present' in joined
        assert 'unavailable' in joined.lower()

    def test_no_raw_states_leak_as_labels(self):
        # Labels are human-facing; never the internal collapsed STRUCTURE_ERROR token.
        for s in vmodel.ALL_STATES:
            assert vmodel.label(s) != 'STRUCTURE_ERROR'
        assert vmodel.label('STRUCTURE_ERROR') == 'CORRUPTED'
