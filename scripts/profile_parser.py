"""
Parser performance profiler (P-investigation). No UI, no parser changes.

Times each parse stage on the 4 / 193 / 440 MB logs:
  1. file read
  2. signature chunk scan  (signature_verifier.extract_signed_data)
  3. FMT discovery          (_pass1_collect_fmt)
  4. record decode + msg construction (_pass2_parse_all)
  5. DataFrame generation   (the result-build loop, reproduced verbatim)
  6. memory                 (peak RSS delta + parsed row count)

Run:
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 scripts/profile_parser.py [4|11|12|all]
"""
import os
import sys
import time
import resource
import cProfile
import pstats
import io

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np                                     # noqa: E402
import pandas as pd                                    # noqa: E402
from core.log_parser import DataFlashParser, _INST_PAT, FIELD_BOUNDS  # noqa: E402
from core import signature_verifier                    # noqa: E402

LOGS = {'4': 'logs/00000002.BIN', '11': 'logs/00000011.BIN', '12': 'logs/00000012.BIN'}


def _rss_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0  # KB→MB on Linux


def _df_build(records, fmt_map, instanced_cols):
    """Verbatim copy of DataFlashParser.parse()'s result-build loop."""
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
                df = df[(df['TimeUS'] > 0) & (df['TimeUS'] < 3e11)]
                df['TimeS'] = df['TimeUS'] / 1e6
            for col in df.columns:
                if col in FIELD_BOUNDS:
                    lo, hi = FIELD_BOUNDS[col]
                    df[col] = df[col].where((df[col] >= lo) & (df[col] <= hi))
            float_cols = [c for c in df.columns
                          if c not in ('TimeUS', 'TimeS')
                          and hasattr(df[c], 'dtype') and df[c].dtype.kind == 'f'
                          and c not in FIELD_BOUNDS]
            if float_cols:
                mask = (df[float_cols].abs() < 1e9).all(axis=1)
                df = df[mask]
            if not df.empty:
                df = df.reset_index(drop=True)
            result[name] = df
        except Exception:
            pass
    return dict(sorted(result.items()))


def profile_log(tag, path):
    p = DataFlashParser()
    size_mb = os.path.getsize(path) / 1e6
    print(f'\n{"="*64}\nLOG {tag}: {os.path.basename(path)}  ({size_mb:.1f} MB)\n{"="*64}')
    rss0 = _rss_mb()

    t = time.perf_counter()
    with open(path, 'rb') as f:
        raw = f.read()
    t_read = time.perf_counter() - t

    t = time.perf_counter()
    if raw[:2] == p.SIGNED_MAGIC:
        clean = signature_verifier.extract_signed_data(raw)
        data = clean if clean is not None else raw[p.HEADER_SIZE:]
        signed = True
    else:
        data = raw; signed = False
    t_chunk = time.perf_counter() - t

    fmt_map = {}
    t = time.perf_counter()
    p._pass1_collect_fmt(data, fmt_map)
    t_fmt = time.perf_counter() - t

    records, instanced = {}, {}
    t = time.perf_counter()
    p._pass2_parse_all(data, fmt_map, records, None, instanced)
    t_pass2 = time.perf_counter() - t
    n_rows = sum(len(v) for v in records.values())

    t = time.perf_counter()
    result = _df_build(records, fmt_map, instanced)
    t_df = time.perf_counter() - t

    rss_peak = _rss_mb()
    total = t_read + t_chunk + t_fmt + t_pass2 + t_df

    rows = [('1 file read', t_read), ('2 chunk scan', t_chunk),
            ('3 FMT discovery', t_fmt), ('4 decode+construct (pass2)', t_pass2),
            ('5 DataFrame gen', t_df)]
    print(f'{"stage":<30}{"sec":>9}{"%":>8}')
    print('-' * 47)
    for name, sec in rows:
        print(f'{name:<30}{sec:>9.2f}{100*sec/total:>7.1f}%')
    print('-' * 47)
    print(f'{"TOTAL":<30}{total:>9.2f}{100:>7.1f}%')
    print(f'\nsigned={signed}  msg_types={len(result)}  parsed_rows={n_rows:,}  '
          f'file_MB={size_mb:.0f}  rows/s={n_rows/max(t_pass2,1e-9):,.0f}')
    print(f'peak_RSS={rss_peak:.0f} MB  (delta {rss_peak-rss0:.0f} MB, '
          f'{(rss_peak-rss0)/size_mb:.1f}x file)')
    return total


def cprofile_small(path):
    print(f'\n{"="*64}\ncPROFILE (function breakdown) on {os.path.basename(path)}\n{"="*64}')
    pr = cProfile.Profile()
    pr.enable()
    DataFlashParser().parse(path)
    pr.disable()
    s = io.StringIO()
    pstats.Stats(pr, stream=s).sort_stats('cumulative').print_stats(18)
    out = s.getvalue()
    # trim to the table
    for line in out.splitlines():
        if line.strip().startswith(('ncalls', 'core/', 'logs')) or 'log_parser' in line \
                or 'signature_verifier' in line or 'function calls' in line or 'struct' in line:
            print(line)


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else 'all'
    tags = list(LOGS) if which == 'all' else [which]
    for tag in tags:
        if os.path.isfile(LOGS[tag]):
            profile_log(tag, LOGS[tag])
        else:
            print(f'missing {LOGS[tag]}')
    if '4' in tags and os.path.isfile(LOGS['4']):
        cprofile_small(LOGS['4'])


if __name__ == '__main__':
    main()
