import struct
import hashlib
import base64
from typing import Optional

TRAILER_MAGIC = b'1HCH'
TRAILER_SIZE  = 145
SIGNED_MAGIC  = bytes([0xA5, 0x01])

ALGORITHM_SHA256  = 1
ALGORITHM_BLAKE2B = 2

CHUNK_MAGIC       = 0x48434831   # "HCH1"
END_MAGIC         = 0x534C4F47   # "SLOG"
CHUNK_RECORD_SIZE = 44
END_RECORD_SIZE   = 101          # magic(4)+final_hash(32)+sig_len(1)+sig(64)

# ── Pure-Python Ed25519-Blake2b (matches Monocypher crypto_sign/crypto_check)
_P = 2**255 - 19
_Q = 2**252 + 27742317777372353535851937790883648493


def _modinv(x):
    return pow(x, _P - 2, _P)


_d  = -121665 * _modinv(121666) % _P
_Gy = 4 * _modinv(5) % _P


def _recover_x(y, sign):
    x2 = (y * y - 1) * _modinv(_d * y * y + 1) % _P
    x  = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * pow(2, (_P - 1) // 4, _P) % _P
    if x % 2 != sign:
        x = _P - x
    return x


_Gx = _recover_x(_Gy, 0)
_G  = (_Gx, _Gy, 1, _Gx * _Gy % _P)


def _pt_add(A, B):
    a, b   = (A[1] - A[0]) * (B[1] - B[0]) % _P, (A[1] + A[0]) * (B[1] + B[0]) % _P
    c, dd  = 2 * A[3] * B[3] * _d % _P, 2 * A[2] * B[2] % _P
    e, f, g, h = b - a, dd - c, dd + c, b + a
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _pt_mul(s, P):
    R = None
    while s:
        if s & 1:
            R = _pt_add(R, P) if R else P
        P = _pt_add(P, P)
        s >>= 1
    return R


def _compress(P):
    zi = _modinv(P[2])
    x, y = P[0] * zi % _P, P[1] * zi % _P
    return int.to_bytes(y | ((x & 1) << 255), 32, 'little')


def _decompress(b):
    y = int.from_bytes(b, 'little')
    s = y >> 255
    y &= ~(1 << 255)
    return (_recover_x(y, s), y, 1, _recover_x(y, s) * y % _P)


def _blake2b512(*parts):
    h = hashlib.blake2b(digest_size=64)
    for p in parts:
        h.update(p)
    return h.digest()


def _ed25519_blake2b_verify(pk32: bytes, sig64: bytes, msg: bytes) -> bool:
    if len(sig64) != 64 or len(pk32) != 32:
        return False
    try:
        R = _decompress(sig64[:32])
        A = _decompress(pk32)
    except Exception:
        return False
    Rb = _compress(R)
    k  = int.from_bytes(_blake2b512(Rb, pk32, msg), 'little') % _Q
    S  = int.from_bytes(sig64[32:], 'little')
    if S >= _Q:
        return False
    lhs = _compress(_pt_mul(S, _G))
    rhs = _compress(_pt_add(R, _pt_mul(k, A)))
    return lhs == rhs


# ── Hash chain helpers ────────────────────────────────────────────────────────

def _chain_hash(algorithm: int, data: bytes, prev: bytes) -> bytes:
    if algorithm == ALGORITHM_SHA256:
        return hashlib.sha256(data + prev).digest()
    return hashlib.blake2b(data + prev, digest_size=32).digest()


def _header_hash(algorithm: int, data: bytes) -> bytes:
    if algorithm == ALGORITHM_SHA256:
        return hashlib.sha256(data).digest()
    return hashlib.blake2b(data, digest_size=32).digest()


# ── Public API ────────────────────────────────────────────────────────────────

def parse_header(raw: bytes) -> dict:
    if len(raw) < 64 or raw[0] != 0xA5:
        return {}
    version   = raw[1]
    algorithm = raw[2]
    device_id = struct.unpack_from('<H', raw, 4)[0]
    fw_ver    = struct.unpack_from('<H', raw, 6)[0]
    timestamp = struct.unpack_from('<I', raw, 8)[0]
    log_ctr   = struct.unpack_from('<H', raw, 12)[0]
    h0_stored = raw[16:48]
    h0_comp   = _header_hash(algorithm, bytes(raw[0:16]))
    algo_name = {
        ALGORITHM_SHA256:  'SHA-256 + Ed25519',
        ALGORITHM_BLAKE2B: 'Blake2b-256 + Ed25519-Blake2b',
    }.get(algorithm, f'Unknown ({algorithm})')
    return {
        'version':    version,
        'algorithm':  algorithm,
        'algo_name':  algo_name,
        'device_id':  f'0x{device_id:04X}',
        'fw_ver':     f'{fw_ver >> 8}.{fw_ver & 0xFF}',
        'timestamp':  timestamp,
        'log_ctr':    log_ctr,
        'h0_stored':  h0_stored.hex(),
        'h0_computed': h0_comp.hex(),
        'h0_ok':      h0_comp == bytes(h0_stored),
    }


def check_structure(raw: bytes) -> tuple:
    if raw[:2] != SIGNED_MAGIC:
        return False, 'Not a signed log'
    if len(raw) < TRAILER_SIZE:
        return False, 'File too small to contain trailer'
    trailer = raw[-TRAILER_SIZE:]
    if trailer[:4] != TRAILER_MAGIC:
        return False, 'Trailer magic missing — file truncated or not a signed log'
    data_len   = struct.unpack_from('<I', trailer, 4)[0]
    data_start = struct.unpack_from('<I', trailer, 8)[0]
    expected   = data_start + data_len
    actual     = len(raw) - TRAILER_SIZE
    if expected != actual:
        return False, (
            f'STRUCTURE CORRUPT: data_start({data_start}) + data_len({data_len:,}) '
            f'= {expected:,} but file body ends at {actual:,}. '
            f'Bytes were added or removed after signing.'
        )
    return True, f'Structure intact — signed range [{data_start}:{data_start + data_len:,}]'


def compute_hashes(raw: bytes) -> dict:
    trailer    = raw[-TRAILER_SIZE:]
    data_len   = struct.unpack_from('<I', trailer, 4)[0]
    data_start = struct.unpack_from('<I', trailer, 8)[0]
    signed     = raw[data_start: data_start + data_len]
    return {
        'sha256_signed': hashlib.sha256(signed).hexdigest(),
        'sha256_full':   hashlib.sha256(raw).hexdigest(),
        'header_mac':    raw[16:48].hex(),
        'key_id':        raw[4:8].hex(),
        'sig_a':         trailer[16:80].hex(),
        'sig_b':         trailer[80:144].hex(),
        'data_start':    data_start,
        'data_len':      data_len,
    }


def check_fingerprint(raw: bytes, pubkey_bytes: bytes) -> str:
    header_mac = raw[16:48]
    sha_key    = hashlib.sha256(pubkey_bytes).digest()
    return 'MATCH' if sha_key[:16] == header_mac[:16] else 'MISMATCH'


def extract_signed_data(raw: bytes) -> Optional[bytes]:
    """
    For a secure (signed) log, return the concatenation of the data ranges
    referenced by the hash-chain chunk records, excluding the interspersed
    CHUNK records and the END record. This is the original DataFlash message
    stream with the signature infrastructure removed, so the parser never reads
    chunk-magic bytes as telemetry.

    Returns None if the log is not signed or contains no chunk records (caller
    should then parse the raw stream as-is). Works on truncated logs (missing
    END/trailer) because chunk records are still present and self-describing.

    Shares the chunk-detection contract with _scan_hash_chain (same magics and
    record sizes) so the parser and verifier agree on chunk boundaries.
    """
    if raw[:2] != SIGNED_MAGIC or len(raw) < 64:
        return None
    n = len(raw)
    pos = 64  # skip signed header
    parts: list = []
    found = False
    # T1: jump to the next CHUNK record via C-level memchr instead of scanning
    # byte-by-byte. Only CHUNK records contribute to the output, and they are
    # visited in the same order with the same bounds checks, so the result is
    # byte-identical to the previous pos+=1 scan (END/data gaps contribute nothing).
    chunk_magic_b = struct.pack('<I', CHUNK_MAGIC)
    while pos <= n - 4:
        m = struct.unpack_from('<I', raw, pos)[0]
        if m == CHUNK_MAGIC:
            if pos + CHUNK_RECORD_SIZE > n:
                break
            _, off, ln, _ = struct.unpack_from('<III32s', raw, pos)
            if off + ln > n:
                break
            parts.append(raw[off:off + ln])
            found = True
            pos += CHUNK_RECORD_SIZE
        elif m == END_MAGIC:
            if pos + END_RECORD_SIZE > n:
                break
            pos += END_RECORD_SIZE
        else:
            nxt = raw.find(chunk_magic_b, pos + 1)
            if nxt < 0:
                break
            pos = nxt
    return b''.join(parts) if found else None


def _scan_hash_chain(raw: bytes) -> dict:
    if len(raw) < 64:
        return {'ok': False, 'chunks': 0, 'end_rec': None, 'errors': []}
    algorithm = raw[2]
    h0_comp   = _header_hash(algorithm, bytes(raw[0:16]))
    prev      = h0_comp
    chunks    = 0
    end_rec   = None
    errors    = []
    pos       = 64  # skip header
    n         = len(raw)

    # T1: jump to the next CHUNK/END record via C-level memchr instead of scanning
    # byte-by-byte through the data gaps between records. We seek the *nearest* of
    # the two magics so no END record is skipped — identical visit order and bounds
    # checks to the previous pos+=1 scan, just without touching every data byte.
    # The END magic is sparse (one record near the file tail), so we cache its next
    # position and only re-search after consuming one — otherwise scanning to the
    # far-off END on every chunk gap would be O(n²) on large logs.
    chunk_magic_b = struct.pack('<I', CHUNK_MAGIC)
    end_magic_b   = struct.pack('<I', END_MAGIC)
    next_end      = raw.find(end_magic_b, pos)
    while pos <= n - 4:
        m = struct.unpack_from('<I', raw, pos)[0]
        if m == CHUNK_MAGIC:
            if pos + CHUNK_RECORD_SIZE > n:
                errors.append(f'Truncated chunk at {pos}')
                break
            _, off, ln, stored = struct.unpack_from('<III32s', raw, pos)
            if off + ln > n:
                errors.append(f'Chunk {chunks} out of range')
                break
            computed = _chain_hash(algorithm, raw[off:off + ln], prev)
            if computed != bytes(stored):
                errors.append(
                    f'Chunk {chunks} MISMATCH at {pos} '
                    f'(computed {computed.hex()[:12]}... stored {bytes(stored).hex()[:12]}...)'
                )
            prev    = computed
            chunks += 1
            pos    += CHUNK_RECORD_SIZE
        elif m == END_MAGIC:
            if pos + END_RECORD_SIZE > n:
                errors.append(f'Truncated end record at {pos}')
                break
            fh  = bytes(raw[pos + 4: pos + 36])
            sl  = raw[pos + 36]
            sig = bytes(raw[pos + 37: pos + 37 + sl]) if sl > 0 else b''
            end_rec = {'offset': pos, 'final_hash': fh, 'sig_len': sl, 'sig': sig,
                       'chain_tail': prev, 'hash_match': fh == prev}
            pos += END_RECORD_SIZE
            next_end = raw.find(end_magic_b, pos)   # consumed; find the next one
        else:
            nc = raw.find(chunk_magic_b, pos + 1)
            if next_end != -1 and next_end <= pos:
                next_end = raw.find(end_magic_b, pos + 1)
            ne = next_end
            if nc < 0 and ne < 0:
                break
            if nc < 0:
                pos = ne
            elif ne < 0:
                pos = nc
            else:
                pos = nc if nc < ne else ne

    return {'ok': len(errors) == 0, 'chunks': chunks, 'end_rec': end_rec,
            'errors': errors, 'algorithm': algorithm}


def verify_ed25519(raw: bytes, pubkey_b64: str) -> tuple:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        key_data = pubkey_b64.strip()
        if key_data.startswith('PUBLIC_KEYV1:'):
            key_data = key_data[len('PUBLIC_KEYV1:'):]
        pubkey_bytes = base64.b64decode(key_data)
    except Exception as e:
        return 'KEY_MISMATCH', f'Failed to load public key: {e}'

    # Try Blake2b-based hash chain first (ArduPilot DGCA secure log)
    chain = _scan_hash_chain(raw)
    if chain['end_rec'] is not None:
        er = chain['end_rec']
        if er['hash_match'] and er['sig_len'] == 64:
            if _ed25519_blake2b_verify(pubkey_bytes, er['sig'], er['final_hash']):
                return 'VERIFIED', (
                    f'Ed25519-Blake2b valid — {chain["chunks"]} chunks, '
                    f'{er["sig_len"]}-byte signature'
                )

    # Fallback: try standard Ed25519 variants against signed range
    try:
        pubkey = Ed25519PublicKey.from_public_bytes(pubkey_bytes)
    except Exception as e:
        return 'KEY_MISMATCH', f'Invalid public key: {e}'

    if len(raw) < TRAILER_SIZE:
        return 'STRUCTURE_ERROR', 'File too small'

    trailer    = raw[-TRAILER_SIZE:]
    data_len   = struct.unpack_from('<I', trailer, 4)[0]
    data_start = struct.unpack_from('<I', trailer, 8)[0]

    sig_a = trailer[16:80]
    sig_b = trailer[80:144]
    msg_a = raw[data_start: data_start + data_len]
    msg_b = hashlib.sha256(msg_a).digest()
    msg_c = raw[0: data_start + data_len]
    msg_d = raw[64: data_start + data_len]

    for sig in (sig_a, sig_b):
        for msg in (msg_a, msg_b, msg_c, msg_d):
            try:
                pubkey.verify(sig, msg)
                return 'VERIFIED', 'Ed25519 signature valid'
            except Exception:
                pass

    fp = check_fingerprint(raw, pubkey_bytes)
    if fp == 'MISMATCH':
        return 'KEY_MISMATCH', 'Key fingerprint mismatch — wrong public key for this log unit'
    return 'TAMPERED', 'Key fingerprint plausible but all signature checks failed — content may have changed'


def full_verify(raw: bytes, pubkey_b64: Optional[str] = None) -> dict:
    """Classify a log into one operational verification state.

    States (see core.verification_model): VERIFIED, PARTIAL, UNSIGNED, INVALID,
    CORRUPTED, UNKNOWN, WRONG_KEY. The hash chain is scanned even when structure
    validation fails, so a truncated-but-intact log (power loss → PARTIAL) is
    distinguished from genuine corruption (CORRUPTED) and tampering (INVALID).
    """
    from core import verification_model as vmodel

    result = {
        'state':              vmodel.UNSIGNED,
        'detail':             '',
        'structure_ok':       False,
        'structure_message':  '',
        'hashes':             {},
        'fingerprint':        '',
        'header_info':        {},
        'chain_chunks':       0,
        'chain_ok':           False,
        'chain_valid':        False,   # keyless chain integrity for chunks present
        'closed':             False,   # END record present (log closed cleanly)
        'algo_name':          '',
    }

    if len(raw) < 2 or raw[:2] != SIGNED_MAGIC:
        result['state']  = vmodel.UNSIGNED
        result['detail'] = 'No signed-log magic (0xA5 0x01) — standard unsigned DataFlash log'
        return result

    # Parse rich header
    result['header_info'] = parse_header(raw)
    result['algo_name']   = result['header_info'].get('algo_name', '')

    struct_ok, struct_msg = check_structure(raw)
    result['structure_ok']      = struct_ok
    result['structure_message'] = struct_msg

    # Always scan the chain — its evidence is what tells truncation from corruption.
    chain = _scan_hash_chain(raw)
    result['chain_chunks'] = chain['chunks']
    result['chain_valid']  = chain['ok']
    result['closed']       = chain['end_rec'] is not None
    result['chain_ok']     = chain['ok'] and result['closed'] and \
                              chain['end_rec']['hash_match']

    # A structurally-valid log, OR a cleanly-closed chain-consistent log (END record
    # carries the signature even if the file trailer is absent), proceeds to signature
    # verification. Otherwise we classify the structural failure from chain evidence.
    if struct_ok or (result['closed'] and result['chain_ok']):
        if struct_ok:
            result['hashes'] = compute_hashes(raw)

        # Keyless integrity first: on a cleanly-closed log (real END record), a broken
        # hash chain proves the signed data was altered, independent of any public key,
        # so it is INVALID — never UNKNOWN (no key) or WRONG_KEY (the key-fingerprint
        # heuristic is unreliable here). Gated on `closed` so it never fires on a
        # degenerate stub whose trailer magic aliases a chunk record.
        if result['closed'] and result['chain_chunks'] > 0 and not result['chain_valid']:
            result['state']  = vmodel.INVALID
            result['detail'] = (
                'Hash-chain mismatch within signed data — possible tampering or corruption.'
            )
            return result

        if pubkey_b64 is None:
            result['state']  = vmodel.UNKNOWN
            result['detail'] = 'No public key loaded'
            return result

        try:
            key_data = pubkey_b64.strip()
            if key_data.startswith('PUBLIC_KEYV1:'):
                key_data = key_data[len('PUBLIC_KEYV1:'):]
            pubkey_bytes = base64.b64decode(key_data)
            result['fingerprint'] = check_fingerprint(raw, pubkey_bytes)
        except Exception:
            result['fingerprint'] = 'ERROR'

        state, detail = verify_ed25519(raw, pubkey_b64)
        result['state']  = vmodel.normalize_state(state)   # VERIFIED / WRONG_KEY / INVALID
        result['detail'] = detail
        return result

    # ── Structure failed and the log is not a closed, consistent chain ──────────
    msg = struct_msg.lower()
    if result['chain_chunks'] > 0 and result['chain_valid'] and not result['closed']:
        # Hash chain intact for every written chunk but never closed → truncation.
        result['state']  = vmodel.PARTIAL
        result['detail'] = (
            f'Signed log interrupted before closure — {result["chain_chunks"]:,} chunks '
            f'valid, END record / trailer not written.'
        )
    elif result['chain_chunks'] > 0 and not result['chain_valid']:
        # A chunk hash did not match → data altered within the signed range.
        result['state']  = vmodel.INVALID
        result['detail'] = (
            'Hash-chain mismatch within signed data — possible tampering or corruption.'
        )
    elif 'added or removed' in msg or 'structure corrupt' in msg:
        # Trailer present but signed-range length altered after signing.
        result['state']  = vmodel.INVALID
        result['detail'] = struct_msg
    else:
        # Verification records unreadable / insufficient to determine integrity.
        result['state']  = vmodel.CORRUPTED
        result['detail'] = struct_msg
    return result


def load_pubkey_file(filepath: str) -> Optional[str]:
    try:
        with open(filepath, 'r') as f:
            return f.read().strip()
    except Exception:
        return None
