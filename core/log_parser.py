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

INSTANCE_COLUMNS = {'I', 'Instance', 'C', 'IMU'}
MAX_VALID_INSTANCE = 15
_INST_PAT = re.compile(r'^(.+)\[(\d+)\]$')

INSTANCE_BOUNDS = {
    'ESC':  (0, 11), 'ESCX': (0, 11),
    'IMU':  (0, 3),  'VIBE': (0, 3),
    'BARO': (0, 3),  'MAG':  (0, 3),
    'GPS':  (0, 3),  'GPA':  (0, 3),
    'SURF': (0, 3),
}
_DEFAULT_INSTANCE_BOUNDS = (0, 15)


def get_instance_col(col_list: list) -> 'str | None':
    for col in col_list:
        if col in INSTANCE_COLUMNS:
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
            self.signals.finished.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))


class DataFlashParser:
    HEAD1 = 0xA3
    HEAD2 = 0x95
    FMT_TYPE = 128
    SIGNED_MAGIC = bytes([0xA5, 0x01])
    UNSIGNED_MAGIC = bytes([0xA3, 0x95])
    TRAILER_MAGIC = b'1HCH'
    HEADER_SIZE = 64
    TRAILER_SIZE = 145

    def parse(self, filepath: str, signals: Optional[ParserSignals] = None) -> dict:
        with open(filepath, 'rb') as f:
            raw = f.read()

        if raw[:2] == self.SIGNED_MAGIC:
            data_start = self.HEADER_SIZE
        else:
            data_start = 0

        data = raw[data_start:]
        if len(raw) > self.TRAILER_SIZE and raw[-self.TRAILER_SIZE: -self.TRAILER_SIZE + 4] == self.TRAILER_MAGIC:
            data = raw[data_start: len(raw) - self.TRAILER_SIZE]

        fmt_map = {}
        self._pass1_collect_fmt(data, fmt_map)

        records = {}
        instanced_cols: dict[str, str] = {}   # base_name -> instance col name
        self._pass2_parse_all(data, fmt_map, records, signals, instanced_cols)

        result = {}
        for name, rows in records.items():
            if not rows:
                continue
            m = _INST_PAT.match(name)
            if m:
                base_name = m.group(1)
                all_cols = fmt_map.get(base_name, {}).get('columns', [])
                inst_col = instanced_cols.get(base_name)
                cols = [c for c in all_cols if c != inst_col] if inst_col else all_cols
            else:
                cols = fmt_map.get(name, {}).get('columns', [])
            if not cols:
                continue
            try:
                df = pd.DataFrame(rows, columns=cols)
                if 'TimeUS' in df.columns:
                    df = df[(df['TimeUS'] > 0) & (df['TimeUS'] < 3e8)]
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
                result[name] = df
            except Exception:
                pass
        return result

    def _pass1_collect_fmt(self, data: bytes, fmt_map: dict):
        i = 0
        n = len(data)
        while i < n - 2:
            if data[i] != self.HEAD1 or data[i + 1] != self.HEAD2:
                i += 1
                continue
            if i + 3 > n:
                break
            msg_type = data[i + 2]
            if msg_type != self.FMT_TYPE:
                i += 1
                continue
            body_start = i + 3
            if body_start + 87 > n:
                break
            try:
                type_id = data[body_start]
                length = data[body_start + 1]
                name = data[body_start + 2: body_start + 6].rstrip(b'\x00').decode('ascii', errors='replace')
                fmt_str = data[body_start + 6: body_start + 22].rstrip(b'\x00').decode('ascii', errors='replace')
                cols_raw = data[body_start + 22: body_start + 86].rstrip(b'\x00').decode('ascii', errors='replace')
                columns = [c.strip() for c in cols_raw.split(',') if c.strip()]
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
            i += 3 + 87

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
                i += 3 + 87
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
                    inst_col = get_instance_col(columns)
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
            if signals and count % 10000 == 0:
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


