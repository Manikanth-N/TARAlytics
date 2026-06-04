"""
T2 validation: prove the vectorized decode produces value-identical DataFrames to
the old per-record path, on 4/193/440 MB, and report timing + peak RSS.

OLD result is built from the retained _pass2_parse_all + the old df-build loop;
NEW result is DataFlashParser.parse(). Compares keys, shapes, and per-column values
(NaN-aware; dtype may legitimately differ — compact numpy vs boxed Python).
"""
import os
import sys
import time
import resource
import gc

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np                                     # noqa: E402
import pandas as pd                                    # noqa: E402
from core.log_parser import DataFlashParser, _INST_PAT, FIELD_BOUNDS  # noqa: E402
from core import signature_verifier as sv              # noqa: E402

LOGS = {'4': 'logs/00000002.BIN', '11': 'logs/00000011.BIN', '12': 'logs/00000012.BIN'}


def _data(raw, p):
    if raw[:2] == p.SIGNED_MAGIC:
        c = sv.extract_signed_data(raw)
        return c if c is not None else raw[p.HEADER_SIZE:]
    return raw


def old_parse(path):
    """The pre-T2 pipeline: pass2 record walk + per-type DataFrame build."""
    p = DataFlashParser()
    raw = open(path, 'rb').read()
    data = _data(raw, p)
    fmt_map = {}; p._pass1_collect_fmt(data, fmt_map)
    records, inst = {}, {}
    p._pass2_parse_all(data, fmt_map, records, None, inst)
    result = {}
    for name, rows in records.items():
        if not rows:
            continue
        m = _INST_PAT.match(name)
        if m:
            base = m.group(1)
            all_cols = fmt_map.get(base, {}).get('columns', [])
            ic = inst.get(base)
            cols = [c for c in all_cols if c != ic] if ic else all_cols
        else:
            cols = fmt_map.get(name, {}).get('columns', [])
        if not cols:
            continue
        try:
            df = pd.DataFrame(rows, columns=cols)
            df = p._apply_filters(df)
            result[name] = df
        except Exception:
            pass
    return dict(sorted(result.items()))


def _col_equal(a, b):
    if a.dtype == object or b.dtype == object:
        return list(a) == list(b)
    fa = np.asarray(a, dtype=np.float64)
    fb = np.asarray(b, dtype=np.float64)
    if fa.shape != fb.shape:
        return False
    return np.array_equal(fa, fb, equal_nan=True)


def compare(old, new):
    if set(old) != set(new):
        return False, f'keys differ: only-old={set(old)-set(new)} only-new={set(new)-set(old)}'
    for k in old:
        do, dn = old[k], new[k]
        if list(do.columns) != list(dn.columns):
            return False, f'{k}: columns differ {list(do.columns)} vs {list(dn.columns)}'
        if do.shape != dn.shape:
            return False, f'{k}: shape {do.shape} vs {dn.shape}'
        for c in do.columns:
            if not _col_equal(do[c].to_numpy(), dn[c].to_numpy()):
                return False, f'{k}.{c}: values differ'
    return True, 'identical'


def _rss():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def main():
    for tag in (sys.argv[1:] or list(LOGS)):
        path = LOGS[tag]
        if not os.path.isfile(path):
            print(f'{tag}: missing'); continue
        mb = os.path.getsize(path) / 1e6
        print(f'\n=== LOG {tag} ({mb:.0f} MB) ===')

        t = time.perf_counter(); old = old_parse(path); t_old = time.perf_counter() - t
        ok, msg = compare(old, new := DataFlashParser().parse(path))
        del old; gc.collect()

        # clean timing + RSS of NEW alone
        gc.collect(); rss0 = _rss()
        t = time.perf_counter(); res = DataFlashParser().parse(path); t_new = time.perf_counter() - t
        rss = _rss()
        rows = sum(len(v) for v in res.values())
        print(f'correctness: {"IDENTICAL" if ok else "DIFFER"}  ({msg})')
        print(f'old(pass2) parse: {t_old:.2f} s   |   NEW parse: {t_new:.2f} s  '
              f'({t_old/max(t_new,1e-9):.1f}x)')
        print(f'rows={rows:,}  msg_types={len(res)}  peak_RSS={rss:.0f} MB ({rss/mb:.1f}x file)')


if __name__ == '__main__':
    main()
