"""
T1 validation: byte-identical output + before/after timing for the find-based
chunk scan and FMT discovery, on the 4/193/440 MB logs.

The OLD (byte-by-byte) implementations are inlined here and compared against the NEW
(module) functions. extract_signed_data feeds the parser its input bytes, and
_pass1_collect_fmt builds the FMT map; pass2/DataFrame stages are unchanged, so
identical (input bytes, FMT map) ⇒ byte-identical parse output.
"""
import os
import sys
import time
import struct
import resource

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import signature_verifier as sv               # noqa: E402
from core.log_parser import (DataFlashParser, _build_fmt_struct,  # noqa: E402
                             _VALID_COL)

LOGS = {'4': 'logs/00000002.BIN', '11': 'logs/00000011.BIN', '12': 'logs/00000012.BIN'}
CRS, ERS = sv.CHUNK_RECORD_SIZE, sv.END_RECORD_SIZE
CHUNK, END = sv.CHUNK_MAGIC, sv.END_MAGIC


def old_chunk(raw):
    if raw[:2] != sv.SIGNED_MAGIC or len(raw) < 64:
        return None
    n = len(raw); pos = 64; parts = []; found = False
    while pos <= n - 4:
        m = struct.unpack_from('<I', raw, pos)[0]
        if m == CHUNK:
            if pos + CRS > n:
                break
            _, off, ln, _ = struct.unpack_from('<III32s', raw, pos)
            if off + ln > n:
                break
            parts.append(raw[off:off + ln]); found = True; pos += CRS
        elif m == END:
            if pos + ERS > n:
                break
            pos += ERS
        else:
            pos += 1
    return b''.join(parts) if found else None


def old_pass1(data):
    p = DataFlashParser(); fmt_map = {}
    i = 0; n = len(data)
    while i < n - 2:
        if data[i] != p.HEAD1 or data[i + 1] != p.HEAD2:
            i += 1; continue
        if i + 3 > n:
            break
        if data[i + 2] != p.FMT_TYPE:
            i += 1; continue
        bs = i + 3
        if bs + p.FMT_BODY_SIZE > n:
            break
        try:
            type_id = data[bs]; length = data[bs + 1]
            name = data[bs + 2: bs + 6].rstrip(b'\x00').decode('ascii', 'replace')
            fmt_str = data[bs + 6: bs + 22].rstrip(b'\x00').decode('ascii', 'replace')
            cb = data[bs + 22: bs + 86]; fn = cb.find(b'\x00')
            cols_raw = cb[:fn if fn >= 0 else 64].decode('ascii', 'replace')
            columns = [c.strip() for c in cols_raw.split(',')
                       if c.strip() and _VALID_COL.match(c.strip())]
            s, _sz, scales = _build_fmt_struct(fmt_str)
            if s is not None:
                e = {'name': name, 'type_id': type_id, 'length': length,
                     'fmt_str': fmt_str, 'columns': columns, 'struct': s, 'scales': scales}
                fmt_map[name] = e; fmt_map[type_id] = e
        except Exception:
            pass
        i += p.FMT_RECORD_SIZE
    return fmt_map


def fmview(fm):
    return {k: (e['name'], e['type_id'], e['length'], e['fmt_str'],
                tuple(e['columns']), tuple(e['scales']), e['struct'].format)
            for k, e in fm.items()}


def _t(fn):
    t = time.perf_counter(); r = fn(); return r, time.perf_counter() - t


def main():
    tags = sys.argv[1:] or list(LOGS)
    print(f'{"log":<5}{"stage":<14}{"old s":>9}{"new s":>9}{"speedup":>9}  identical')
    print('-' * 60)
    for tag in tags:
        path = LOGS[tag]
        if not os.path.isfile(path):
            print(f'{tag}: missing'); continue
        raw = open(path, 'rb').read()
        mb = len(raw) / 1e6

        old_data, t_oc = _t(lambda: old_chunk(raw))
        new_data, t_nc = _t(lambda: sv.extract_signed_data(raw))
        ok_chunk = old_data == new_data
        print(f'{tag:<5}{"chunk scan":<14}{t_oc:>9.3f}{t_nc:>9.4f}'
              f'{t_oc/max(t_nc,1e-9):>8.0f}x  {ok_chunk}')

        data = new_data if new_data is not None else raw
        old_fm, t_of = _t(lambda: old_pass1(data))
        p = DataFlashParser(); new_fm = {}
        _, t_nf = _t(lambda: p._pass1_collect_fmt(data, new_fm))
        ok_fmt = fmview(old_fm) == fmview(new_fm)
        print(f'{tag:<5}{"FMT discovery":<14}{t_of:>9.3f}{t_nf:>9.4f}'
              f'{t_of/max(t_nf,1e-9):>8.0f}x  {ok_fmt}')

        # full parse (NEW) total + peak RSS
        rss0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
        _, t_full = _t(lambda: DataFlashParser().parse(path))
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
        print(f'{tag:<5}{"FULL parse":<14}{"":>9}{t_full:>9.2f}{"":>9}  '
              f'peakRSS={rss:.0f}MB ({rss/mb:.1f}x)  [{mb:.0f}MB]')
        print('-' * 60)


if __name__ == '__main__':
    main()
