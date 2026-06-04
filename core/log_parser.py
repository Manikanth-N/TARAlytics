import re
import struct
import hashlib
from typing import Optional
import numpy as np
import pandas as pd
from PyQt6.QtCore import QRunnable, QObject, pyqtSignal, QThreadPool


FIELD_BOUNDS = {
    'AccX': (-200, 200), 'AccY': (-200, 200), 'AccZ': (-200, 200),
    'GyrX': (-35, 35),   'GyrY': (-35, 35),   'GyrZ': (-35, 35),
    'Roll': (-180, 180), 'Pitch': (-90, 90),   'Yaw': (-360, 360),
    'DesRoll': (-180, 180), 'DesPitch': (-90, 90), 'DesYaw': (-360, 360),
    'Volt': (0, 60),     'Curr': (-5, 500),
    'RPM': (0, 100_000), 'outpct': (0, 100),   'inpct': (0, 100),
}

FORMAT_MAP = {
    'b': ('b', 1),   'B': ('B', 1),
    'h': ('h', 2),   'H': ('H', 2),
    'i': ('i', 4),   'I': ('I', 4),
    'q': ('q', 8),   'Q': ('Q', 8),
    'f': ('f', 4),   'd': ('d', 8),
    'e': ('f', 4),   'c': ('h', 2),
    'C': ('H', 2),   'L': ('i', 4),
    'M': ('B', 1),   'n': ('4s', 4),
    'N': ('16s', 16), 'Z': ('64s', 64),
    'a': ('64s', 64),
}

SCALE_C = {'c', 'C'}
SCALE_L = {'L'}

# T2: numpy dtype per DataFlash format char — byte layout matches the packed
# little-endian struct produced by _build_fmt_struct (FORMAT_MAP), so a structured
# np.dtype over the format decodes a whole message type in one frombuffer/view.
NP_TYPE = {
    'b': '<i1', 'B': '<u1', 'h': '<i2', 'H': '<u2',
    'i': '<i4', 'I': '<u4', 'q': '<i8', 'Q': '<u8',
    'f': '<f4', 'd': '<f8', 'e': '<f4', 'c': '<i2',
    'C': '<u2', 'L': '<i4', 'M': '<u1',
    'n': 'S4', 'N': 'S16', 'Z': 'S64', 'a': 'S64',
}
_STR_FMTS = {'n', 'N', 'Z'}

INSTANCE_COLUMNS = {'I', 'Instance', 'C', 'IMU'}
# Only integer-typed formats can be instance discriminators; a float column
# named 'I' (e.g. the PID integral term) is data, not an instance index.
INTEGER_FMTS = {'b', 'B', 'h', 'H', 'i', 'I', 'q', 'Q', 'M'}
MAX_VALID_INSTANCE = 15
_INST_PAT = re.compile(r'^(.+)\[(\d+)\]$')
_VALID_COL = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

INSTANCE_BOUNDS = {
    'ESC':  (0, 11), 'ESCX': (0, 11),
    'IMU':  (0, 3),  'VIBE': (0, 3),
    'BARO': (0, 3),  'MAG':  (0, 3),
    'GPS':  (0, 3),  'GPA':  (0, 3),
    'SURF': (0, 3),
}
_DEFAULT_INSTANCE_BOUNDS = (0, 15)


def get_instance_col(col_list: list, scales: list = None) -> 'str | None':
    for idx, col in enumerate(col_list):
        if col in INSTANCE_COLUMNS:
            if scales is not None and idx < len(scales) and scales[idx] not in INTEGER_FMTS:
                continue  # float column with an instance-like name (PID I-term) — not an instance
            return col
    return None


def is_valid_instance(msg_name: str, inst_val: int) -> bool:
    lo, hi = INSTANCE_BOUNDS.get(msg_name, _DEFAULT_INSTANCE_BOUNDS)
    return lo <= inst_val <= hi


def _build_fmt_struct(fmt_str: str):
    struct_chars = []
    sizes = []
    scales = []
    for ch in fmt_str:
        if ch not in FORMAT_MAP:
            return None, None, None
        sc, sz = FORMAT_MAP[ch]
        struct_chars.append(sc)
        sizes.append(sz)
        scales.append(ch)
    try:
        s = struct.Struct('<' + ''.join(struct_chars))
    except struct.error:
        return None, None, None
    return s, sizes, scales


class ParserSignals(QObject):
    progress = pyqtSignal(int)
    stage = pyqtSignal(str)        # human-readable current parse stage
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)


class ParseRunnable(QRunnable):
    def __init__(self, filepath: str, signals: ParserSignals):
        super().__init__()
        self.filepath = filepath
        self.signals = signals

    def run(self):
        try:
            parser = DataFlashParser()
            result = parser.parse(self.filepath, self.signals)
            _malloc_trim()      # return the parse's large transient arenas to the OS
            self.signals.finished.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))


def _malloc_trim():
    """Hint glibc to release freed memory back to the OS after a parse's heavy
    transient allocations. No-op off Linux/glibc (e.g. Windows)."""
    try:
        import ctypes
        ctypes.CDLL('libc.so.6').malloc_trim(0)
    except Exception:
        pass


class VerifySignals(QObject):
    finished = pyqtSignal(dict, str)   # (result, key_path)


class VerifyRunnable(QRunnable):
    def __init__(self, raw_bytes: bytes, pubkey_str, key_path: str, signals: 'VerifySignals'):
        super().__init__()
        self._raw = raw_bytes
        self._pubkey = pubkey_str
        self._key_path = key_path
        self._signals = signals

    def run(self):
        from core import signature_verifier
        result = signature_verifier.full_verify(self._raw, self._pubkey)
        self._signals.finished.emit(result, self._key_path)


class DataFlashParser:
    HEAD1 = 0xA3
    HEAD2 = 0x95
    FMT_TYPE = 128
    SIGNED_MAGIC = bytes([0xA5, 0x01])
    UNSIGNED_MAGIC = bytes([0xA3, 0x95])
    TRAILER_MAGIC = b'1HCH'
    HEADER_SIZE = 64
    TRAILER_SIZE = 145
    # sizeof(log_Format) per AP_Logger/LogStructure.h:
    #   header(3) + type(1) + length(1) + name[4] + format[16] + labels[64] = 89
    # The body after the 3-byte packet header is 86 bytes.
    FMT_BODY_SIZE = 86
    FMT_RECORD_SIZE = 3 + FMT_BODY_SIZE   # 89

    def _stage(self, signals, text, pct=None):
        if signals:
            signals.stage.emit(text)
            if pct is not None:
                signals.progress.emit(pct)

    def parse(self, filepath: str, signals: Optional[ParserSignals] = None) -> dict:
        self._stage(signals, 'Reading log file', 2)
        with open(filepath, 'rb') as f:
            raw = f.read()

        if raw[:2] == self.SIGNED_MAGIC:
            self._stage(signals, 'Extracting signed data', 8)
            # Secure log: parse ONLY the data ranges referenced by the hash-chain
            # chunk records, excluding the interleaved 44-byte CHUNK records and
            # the END record. Otherwise chunk-magic bytes ("1HCH") leak into
            # telemetry as garbage (e.g. 199968.766). Reuses the verifier's
            # chunk detection so parser and verifier agree on boundaries.
            from core import signature_verifier
            clean = signature_verifier.extract_signed_data(raw)
            if clean is not None:
                data = clean
            else:
                # Signed magic but no chunk records recovered — fall back to the
                # legacy header/trailer strip so we never lose a parseable log.
                data = raw[self.HEADER_SIZE:]
                if len(raw) > self.TRAILER_SIZE and \
                        raw[-self.TRAILER_SIZE: -self.TRAILER_SIZE + 4] == self.TRAILER_MAGIC:
                    data = raw[self.HEADER_SIZE: len(raw) - self.TRAILER_SIZE]
        else:
            # Unsigned log: no chunk records; parse the whole stream as-is.
            data = raw

        # For signed logs `data` is a separate extracted copy, so the original
        # file bytes are no longer needed — free them to halve peak RSS.
        if data is not raw:
            raw = None

        self._stage(signals, 'Discovering message formats', 16)
        fmt_map = {}
        self._pass1_collect_fmt(data, fmt_map)

        # T2: collect per-type record offsets in one lean walk, then decode each
        # message type with a structured-dtype numpy view (no per-record Python
        # objects). Scaling, instance routing, and field-bounds filtering are
        # applied exactly as before.
        self._stage(signals, 'Decoding flight records', 20)
        offsets = self._collect_offsets(data, fmt_map, signals)
        self._stage(signals, 'Building data tables', 92)
        result = {}
        for type_id, off in offsets.items():
            entry = fmt_map.get(type_id)
            if entry is None or off.size == 0:
                continue
            try:
                for dict_key, df in self._decode_type(data, entry, off):
                    df = self._apply_filters(df)
                    result[dict_key] = df
            except Exception:
                pass
        self._stage(signals, 'Finalizing', 100)
        return dict(sorted(result.items()))

    # ── T2 vectorized decode ──────────────────────────────────────────────────

    @staticmethod
    def _np_dtype(scales):
        """Packed structured np.dtype matching the '<'-packed struct for these
        format chars; or None if any char is unsupported."""
        fields = []
        for j, ch in enumerate(scales):
            t = NP_TYPE.get(ch)
            if t is None:
                return None
            fields.append((f'f{j}', t))
        return np.dtype(fields)

    def _collect_offsets(self, data: bytes, fmt_map: dict,
                         signals: Optional[ParserSignals] = None) -> dict:
        """One sequential walk: per type_id, the body-start offsets of its records.
        Mirrors the old pass2 record walk (same header/length/skip rules) without
        decoding — so the set of records is identical."""
        n = len(data)
        HEAD1, HEAD2, FMT = self.HEAD1, self.HEAD2, self.FMT_TYPE
        get = fmt_map.get
        lists: dict[int, list] = {}
        i = 0
        count = 0
        while i < n - 2:
            if data[i] != HEAD1 or data[i + 1] != HEAD2:
                i += 1
                continue
            mt = data[i + 2]
            if mt == FMT:
                i += self.FMT_RECORD_SIZE
                count += 1
                continue
            entry = get(mt)
            if entry is None:
                i += 1
                continue
            length = entry['length']
            if i + length > n:
                i += 1
                continue
            lst = lists.get(mt)
            if lst is None:
                lst = lists[mt] = []
            lst.append(i + 3)
            i += length
            count += 1
            if signals and count % 200000 == 0:
                signals.progress.emit(min(99, int(i / n * 90)))
        return {mt: np.array(v, dtype=np.int64) for mt, v in lists.items()}

    def _decode_type(self, data: bytes, entry: dict, off: np.ndarray):
        """Yield (dict_key, DataFrame) for one message type, decoded in bulk.
        Reproduces the old per-record behavior: struct size <= body, column
        truncation, c/C and L scaling, n/N/Z/a decode, and instance routing."""
        s = entry['struct']
        scales = entry['scales']
        columns = entry['columns']
        name = entry.get('name', '')
        length = entry['length']
        # type usable only if the struct fits the declared body and there are at
        # least as many decoded fields as columns (old code skips otherwise).
        if s.size > length - 3 or len(columns) > len(scales) or not columns:
            return
        dt = self._np_dtype(scales)
        if dt is None or dt.itemsize != s.size:
            return
        L = s.size

        valid = off + L <= len(data)
        off = off[valid]
        if off.size == 0:
            return
        nrec = off.size
        u8 = np.frombuffer(data, dtype=np.uint8)
        ncols = len(columns)

        # Preallocate one output array per column (compact numpy dtype; float for
        # scaled c/C/L; object for string/array fields), then fill in record chunks.
        # Chunking + int32 indices bound the gather/index transient regardless of
        # how many records a type has, keeping peak RSS low.
        col_arrays = {}
        for j in range(ncols):
            ch = scales[j]
            if ch in SCALE_C or ch in SCALE_L:
                col_arrays[columns[j]] = np.empty(nrec, np.float64)
            elif ch in _STR_FMTS or ch == 'a':
                col_arrays[columns[j]] = np.empty(nrec, object)
            else:
                col_arrays[columns[j]] = np.empty(nrec, dt[f'f{j}'])

        ar_L = np.arange(L, dtype=np.int32)
        CHUNK = 1_000_000
        for start in range(0, nrec, CHUNK):
            co = off[start:start + CHUNK].astype(np.int32)
            end = start + co.size
            idx = co[:, None] + ar_L[None, :]
            sa = u8[idx].reshape(-1).view(dt)     # structured view of this chunk
            for j in range(ncols):
                ch = scales[j]
                field = sa[f'f{j}']
                out = col_arrays[columns[j]]
                if ch in SCALE_C:
                    out[start:end] = field.astype(np.float64) / 100.0
                elif ch in SCALE_L:
                    out[start:end] = field.astype(np.float64) / 1e7
                elif ch in _STR_FMTS:
                    out[start:end] = [b.rstrip(b'\x00').decode('utf-8', errors='replace')
                                      for b in field]
                elif ch == 'a':
                    out[start:end] = [list(struct.unpack('<32h', b)) for b in field]
                else:
                    out[start:end] = field

        inst_col = get_instance_col(columns, scales)
        if inst_col is None:
            yield name, pd.DataFrame({c: col_arrays[c] for c in columns})
            return

        # instance routing: split rows by the (integer) instance column, validate,
        # drop the instance column.
        inst_vals = col_arrays[inst_col]
        out_cols = [c for c in columns if c != inst_col]
        for uval in np.unique(inst_vals):
            iv = int(uval)
            if not is_valid_instance(name, iv):
                continue
            mask = inst_vals == uval
            df = pd.DataFrame({c: col_arrays[c][mask] for c in out_cols})
            yield f'{name}[{iv}]', df

    @staticmethod
    def _apply_filters(df: pd.DataFrame) -> pd.DataFrame:
        """The exact post-decode filtering from the old df-build loop: TimeUS range +
        TimeS, FIELD_BOUNDS clamping, and the |x|<1e9 float sanity filter."""
        if 'TimeUS' in df.columns:
            df = df[(df['TimeUS'] > 0) & (df['TimeUS'] < 3e11)].copy()
            df['TimeS'] = df['TimeUS'] / 1e6
        for col in df.columns:
            if col in FIELD_BOUNDS:
                lo, hi = FIELD_BOUNDS[col]
                df[col] = df[col].where((df[col] >= lo) & (df[col] <= hi))
        float_cols = [c for c in df.columns
                      if c not in ('TimeUS', 'TimeS')
                      and hasattr(df[c], 'dtype')
                      and df[c].dtype.kind == 'f'
                      and c not in FIELD_BOUNDS]
        if float_cols:
            mask = (df[float_cols].abs() < 1e9).all(axis=1)
            df = df[mask]
        if not df.empty:
            df = df.reset_index(drop=True)
        return df

    def _pass1_collect_fmt(self, data: bytes, fmt_map: dict):
        n = len(data)
        # T1: jump directly to each FMT header (A3 95 80) via C-level memchr instead
        # of scanning byte-by-byte. The previous scan jumped FMT_RECORD_SIZE after
        # every A3 95 80 it saw, so find()ing the next header at i+FMT_RECORD_SIZE
        # visits the identical set of candidate positions → byte-identical fmt_map.
        hdr = bytes([self.HEAD1, self.HEAD2, self.FMT_TYPE])
        i = data.find(hdr, 0)
        while i != -1:
            body_start = i + 3
            if body_start + self.FMT_BODY_SIZE > n:
                break
            try:
                type_id = data[body_start]
                length = data[body_start + 1]
                name = data[body_start + 2: body_start + 6].rstrip(b'\x00').decode('ascii', errors='replace')
                fmt_str = data[body_start + 6: body_start + 22].rstrip(b'\x00').decode('ascii', errors='replace')
                cols_bytes = data[body_start + 22: body_start + 86]
                first_null = cols_bytes.find(b'\x00')
                cols_raw = cols_bytes[:first_null if first_null >= 0 else 64].decode('ascii', errors='replace')
                columns = [c.strip() for c in cols_raw.split(',')
                           if c.strip() and _VALID_COL.match(c.strip())]
                s, sizes, scales = _build_fmt_struct(fmt_str)
                if s is not None:
                    entry = {
                        'name': name,
                        'type_id': type_id,
                        'length': length,
                        'fmt_str': fmt_str,
                        'columns': columns,
                        'struct': s,
                        'scales': scales,
                    }
                    fmt_map[name] = entry
                    fmt_map[type_id] = entry
            except Exception:
                pass
            i = data.find(hdr, i + self.FMT_RECORD_SIZE)

    def _pass2_parse_all(self, data: bytes, fmt_map: dict, records: dict,
                         signals: Optional[ParserSignals],
                         instanced_cols: Optional[dict] = None):
        i = 0
        n = len(data)
        count = 0
        while i < n - 2:
            if data[i] != self.HEAD1 or data[i + 1] != self.HEAD2:
                i += 1
                continue
            if i + 3 > n:
                break
            msg_type = data[i + 2]
            if msg_type == self.FMT_TYPE:
                i += self.FMT_RECORD_SIZE
                count += 1
                continue
            entry = fmt_map.get(msg_type)
            if entry is None:
                i += 1
                continue
            length = entry['length']
            body_len = length - 3
            body_start = i + 3
            if body_start + body_len > n:
                i += 1
                continue
            body = data[body_start: body_start + body_len]
            s = entry['struct']
            scales = entry['scales']
            columns = entry['columns']
            name_key = entry.get('name', f'TYPE_{msg_type}')
            try:
                if s.size <= len(body):
                    vals = list(s.unpack(body[:s.size]))
                    for idx, sc in enumerate(scales):
                        if idx >= len(vals):
                            break
                        if sc in SCALE_C:
                            vals[idx] = vals[idx] / 100.0
                        elif sc in SCALE_L:
                            vals[idx] = vals[idx] / 1e7
                        elif sc in ('n', 'N', 'Z'):
                            try:
                                vals[idx] = vals[idx].rstrip(b'\x00').decode('utf-8', errors='replace')
                            except Exception:
                                vals[idx] = ''
                        elif sc == 'a':
                            try:
                                vals[idx] = list(struct.unpack('<32h', vals[idx]))
                            except Exception:
                                vals[idx] = []

                    row = vals[:len(columns)]
                    inst_col = get_instance_col(columns, scales)
                    if inst_col is not None:
                        inst_idx = columns.index(inst_col)
                        try:
                            inst_val = int(row[inst_idx])
                        except (TypeError, ValueError, IndexError):
                            i += length
                            count += 1
                            continue
                        if not is_valid_instance(name_key, inst_val):
                            i += length
                            count += 1
                            continue
                        dict_key = f'{name_key}[{inst_val}]'
                        row = [v for j, v in enumerate(row) if columns[j] != inst_col]
                        if instanced_cols is not None:
                            instanced_cols[name_key] = inst_col
                    else:
                        dict_key = name_key

                    if dict_key not in records:
                        records[dict_key] = []
                    records[dict_key].append(row)
            except Exception:
                pass
            i += length
            count += 1
            if signals and count % 5000 == 0:
                pct = min(99, int(i / n * 100))
                signals.progress.emit(pct)
        if signals:
            signals.progress.emit(100)

    def get_header_info(self, filepath: str) -> dict:
        with open(filepath, 'rb') as f:
            raw = f.read()

        result = {
            'is_signed': False,
            'version': 0,
            'key_id': '',
            'header_mac': '',
            'has_trailer': False,
            'data_start': 0,
            'data_len': 0,
            'trailer_magic_valid': False,
            'structure_ok': False,
            'structure_message': 'Not a signed log',
        }

        if raw[:2] == self.SIGNED_MAGIC:
            result['is_signed'] = True
            result['version'] = raw[2] if len(raw) > 2 else 0
            if len(raw) >= 48:
                key_id_bytes = raw[4:8]
                result['key_id'] = ' '.join(f'{b:02x}' for b in key_id_bytes)
                result['header_mac'] = raw[16:48].hex()

        if len(raw) >= self.TRAILER_SIZE:
            trailer = raw[-self.TRAILER_SIZE:]
            if trailer[:4] == self.TRAILER_MAGIC:
                result['has_trailer'] = True
                result['trailer_magic_valid'] = True
                data_len = struct.unpack_from('<I', trailer, 4)[0]
                data_start = struct.unpack_from('<I', trailer, 8)[0]
                result['data_len'] = data_len
                result['data_start'] = data_start
                expected = data_start + data_len
                actual = len(raw) - self.TRAILER_SIZE
                if expected == actual:
                    result['structure_ok'] = True
                    result['structure_message'] = (
                        f'Structure intact — signed range [{data_start}:{data_start + data_len:,}]'
                    )
                else:
                    result['structure_ok'] = False
                    result['structure_message'] = (
                        f'STRUCTURE CORRUPT: data_start({data_start}) + data_len({data_len:,}) '
                        f'= {expected:,} but file body ends at {actual:,}. '
                        f'Bytes were added or removed after signing.'
                    )
        return result


