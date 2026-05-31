"""Helpers for building synthetic DataFlash binary logs in tests."""
import struct
import numpy as np
import pandas as pd

HEAD1, HEAD2, FMT_TYPE = 0xA3, 0x95, 0x80

# Signature / trailer constants (must match signature_verifier.py)
SIGNED_MAGIC = bytes([0xA5, 0x01])
TRAILER_MAGIC = b'1HCH'
TRAILER_SIZE = 145


def make_fmt_record(type_id: int, msg_length: int, name: str, fmt: str, columns: str) -> bytes:
    """
    Build a DataFlash FMT message.
    Total size: 3 header bytes + 87 body bytes = 90 bytes.
    Body layout: type_id(1) + msg_length(1) + name(4) + fmt(16) + cols(64) + pad(1)
    """
    body = bytes([type_id, msg_length])
    body += name.encode('ascii').ljust(4, b'\x00')[:4]
    body += fmt.encode('ascii').ljust(16, b'\x00')[:16]
    body += columns.encode('ascii').ljust(64, b'\x00')[:64]
    body += b'\x00'  # 87th pad byte
    return bytes([HEAD1, HEAD2, FMT_TYPE]) + body


def make_data_record(type_id: int, packed_body: bytes) -> bytes:
    return bytes([HEAD1, HEAD2, type_id]) + packed_body


# ── ATT (attitude) records ─────────────────────────────────────────────────────
#   Format: qccc  →  TimeUS(q=int64), Roll(c=int16/100), Pitch(c), Yaw(c)
ATT_TYPE = 16
_ATT_STRUCT = struct.Struct('<qhhh')
ATT_MSG_LEN = 3 + _ATT_STRUCT.size  # 17


def make_att_fmt() -> bytes:
    return make_fmt_record(ATT_TYPE, ATT_MSG_LEN, 'ATT', 'qccc', 'TimeUS,Roll,Pitch,Yaw')


def make_att_record(time_us: int, roll: float, pitch: float, yaw: float) -> bytes:
    body = _ATT_STRUCT.pack(time_us, int(roll * 100), int(pitch * 100), int(yaw * 100))
    return make_data_record(ATT_TYPE, body)


def synthetic_att_log() -> bytes:
    """Three ATT records at 40 / 41 / 42 seconds."""
    return (
        make_att_fmt()
        + make_att_record(40_000_000, 1.5, -0.5, 90.0)
        + make_att_record(41_000_000, 2.0, -1.0, 91.0)
        + make_att_record(42_000_000, 1.0,  0.5, 89.0)
    )


# ── ESCX (instanced motor output) records ─────────────────────────────────────
#   Format: qBC  →  TimeUS(q), I/instance(B=uint8), outpct(C=uint16/100)
ESCX_TYPE = 17
_ESCX_STRUCT = struct.Struct('<qBH')
ESCX_MSG_LEN = 3 + _ESCX_STRUCT.size  # 14


def make_escx_fmt() -> bytes:
    return make_fmt_record(ESCX_TYPE, ESCX_MSG_LEN, 'ESCX', 'qBC', 'TimeUS,I,outpct')


def make_escx_record(time_us: int, instance: int, pct: float) -> bytes:
    body = _ESCX_STRUCT.pack(time_us, instance, int(pct * 100))
    return make_data_record(ESCX_TYPE, body)


def synthetic_escx_log() -> bytes:
    """Two instances (0, 1) of ESCX at 40 and 41 seconds."""
    return (
        make_escx_fmt()
        + make_escx_record(40_000_000, 0, 50.0)
        + make_escx_record(40_000_000, 1, 60.0)
        + make_escx_record(41_000_000, 0, 55.0)
        + make_escx_record(41_000_000, 1, 65.0)
    )


# ── Signed log fixture ─────────────────────────────────────────────────────────
def minimal_signed_log() -> bytes:
    """
    Bytes that pass check_structure() but have no valid hash chain or signature.
    Structure: 64-byte header + 100-byte payload + 145-byte trailer.
    """
    header = bytearray(64)
    header[0] = 0xA5
    header[1] = 0x01  # version
    header[2] = 0x02  # ALGORITHM_BLAKE2B

    payload = b'\xAB' * 100
    data_start = 64
    data_len = len(payload)

    trailer = bytearray(TRAILER_SIZE)
    trailer[0:4] = TRAILER_MAGIC
    struct.pack_into('<I', trailer, 4, data_len)
    struct.pack_into('<I', trailer, 8, data_start)

    return bytes(header) + payload + bytes(trailer)


# ── Plotter-ready parsed data dict ─────────────────────────────────────────────
def make_parsed_data(n: int = 100) -> dict:
    """Return a minimal parsed-data dict suitable for PlotterTab.update_data()."""
    t = np.linspace(40.0, 65.0, n)
    return {
        'ATT': pd.DataFrame({
            'TimeUS': (t * 1e6).astype(np.int64),
            'TimeS':  t,
            'Roll':   np.sin(t) * 30,
            'Pitch':  np.cos(t) * 15,
            'Yaw':    np.cumsum(np.ones(n) * 0.5) + 300,
        }),
        'ESCX[0]': pd.DataFrame({
            'TimeUS': (t * 1e6).astype(np.int64),
            'TimeS':  t,
            'outpct': np.clip(50 + 10 * np.sin(t), 0, 100),
        }),
        'SIM2': pd.DataFrame({
            'TimeUS': (t * 1e6).astype(np.int64),
            'TimeS':  t,
            'PN': np.linspace(0, 10, n),
            'PE': np.linspace(0, 10, n),
            'PD': np.linspace(0, -20, n),
            'VN': np.zeros(n),
            'VE': np.zeros(n),
            'VD': np.zeros(n),
        }),
    }
