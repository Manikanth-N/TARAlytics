import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BIN = os.path.join(os.path.dirname(__file__), '00000001.BIN')
KEY = os.path.join(os.path.dirname(__file__), 'SN-01_log_public_key.dat')

PASS = '\033[92mPASS\033[0m'
FAIL = '\033[91mFAIL\033[0m'

def check(label, got, expected):
    ok = str(got) == str(expected)
    status = PASS if ok else FAIL
    print(f'  [{status}] {label}')
    if not ok:
        print(f'          got:      {got}')
        print(f'          expected: {expected}')

print('=' * 65)
print('STEP 1 — File & Header')
print('=' * 65)

with open(BIN, 'rb') as f:
    raw = f.read()
with open(KEY) as f:
    pubkey = f.read().strip()

check('File size', len(raw), 1_887_719)
check('Signed magic', raw[:2].hex(), 'a501')
check('Pubkey prefix', pubkey[:13], 'PUBLIC_KEYV1:')

print()
print('=' * 65)
print('STEP 2 — Signature Verification')
print('=' * 65)

from core.signature_verifier import (
    check_structure, compute_hashes, check_fingerprint, verify_ed25519
)
import base64

ok, msg = check_structure(raw)
check('Structure check', ok, True)
print(f'  msg: {msg}')

h = compute_hashes(raw)
check('data_start', h['data_start'], 298)
check('data_len',   h['data_len'],   1_887_276)
check('SHA256 signed', h['sha256_signed'],
      '0021879cca8e1cfeaa2b9d2082b54cab630bea586587964707d0786044a56b78')
check('SHA256 full',   h['sha256_full'],
      '35e7a0cfcf45dd467c3b5822c9fcffac47062c962dd064269fbd99b4ce12f87c')
check('Header MAC',    h['header_mac'],
      'c809835f77863a2f6f5759969f5416c739aaf405a872283fdc89b57162a4bd05')
ki = ' '.join(h['key_id'][i:i+2] for i in range(0, len(h['key_id']), 2))
check('Key ID', ki, '66 33 06 04')

pubkey_bytes = base64.b64decode(pubkey.removeprefix('PUBLIC_KEYV1:'))
fp = check_fingerprint(raw, pubkey_bytes)
check('Key fingerprint', fp, 'MISMATCH')   # SHA256-prefix fingerprint mismatch is expected

state, detail = verify_ed25519(raw, pubkey)
check('Ed25519 state', state, 'VERIFIED')  # Blake2b hash chain + Ed25519-Blake2b passes
print(f'  detail: {detail}')

print()
print('=' * 65)
print('STEP 3 — Log Parser')
print('=' * 65)

from core.log_parser import DataFlashParser
import numpy as np

parser = DataFlashParser()
print('  Parsing 00000001.BIN ...')
data = parser.parse(BIN)

check('Message types parsed >= 10', len(data) >= 10, True)
print(f'  Types found ({len(data)}): {sorted(data.keys())}')

# Time range
all_t = []
for df in data.values():
    if 'TimeS' in df.columns:
        all_t.extend(df['TimeS'].dropna().values)
t_min = float(np.min(all_t))
t_max = float(np.max(all_t))
check('t_min ~40.146', round(t_min, 2), 40.15)
check('t_max ~65.143', round(t_max, 2), 65.14)
print(f'  Time range: {t_min:.3f}s to {t_max:.3f}s')

# MSG
msg_df = data.get('MSG')
print()
check('MSG exists', msg_df is not None, True)
if msg_df is not None:
    check('MSG row count >= 8', len(msg_df) >= 8, True)
    msg_col = next((c for c in ('Message', 'Msg') if c in msg_df.columns), None)
    if msg_col:
        print('  MSG messages:')
        for _, row in msg_df.iterrows():
            print(f'    t={row["TimeS"]:.3f}s  {str(row[msg_col])[:75]}')
        texts = ' '.join(str(v) for v in msg_df[msg_col])
        check('Firmware in MSG', 'ArduCopter' in texts, True)
        check('Frame in MSG',    'Frame:' in texts, True)

# MODE
mode_df = data.get('MODE')
print()
check('MODE exists', mode_df is not None, True)
if mode_df is not None:
    check('MODE row count', len(mode_df), 2)
    print(f'  MODE rows: t={list(mode_df["TimeS"].round(3))}')

# EV
ev_df = data.get('EV')
print()
check('EV exists', ev_df is not None, True)
if ev_df is not None:
    check('EV row count >= 1', len(ev_df) >= 1, True)
    id_col = next((c for c in ('Id','ID','id') if c in ev_df.columns), None)
    if id_col:
        print(f'  EV id={int(ev_df[id_col].iloc[0])} at t={ev_df["TimeS"].iloc[0]:.3f}s')

# ERR
err_df = data.get('ERR')
print()
check('ERR row count', len(err_df) if err_df is not None else 0, 0)

# ATT
att_df = data.get('ATT')
print()
check('ATT exists', att_df is not None, True)
if att_df is not None and not att_df.empty:
    row = att_df.iloc[(att_df['TimeS'] - 40.147).abs().argsort()[:1]]
    for col, exp in [('Roll', 0.07), ('Pitch', 0.06), ('Yaw', 355.50)]:
        if col in row.columns:
            v = float(row[col].values[0])
            check(f'ATT.{col} at t~40.147', round(v, 2), exp)

# GPS
gps_df = data.get('GPS')
print()
if gps_df is not None and not gps_df.empty:
    lat_col = next((c for c in ('Lat','lat') if c in gps_df.columns), None)
    lng_col = next((c for c in ('Lng','lng','Lon','lon') if c in gps_df.columns), None)
    if lat_col:
        check('GPS Lat home ~-35.363', round(float(gps_df[lat_col].iloc[0]), 3), -35.363)
    if lng_col:
        check('GPS Lng home ~149.165', round(float(gps_df[lng_col].iloc[0]), 3), 149.165)
else:
    sim2_present = data.get('SIM2') is not None or data.get('SIM') is not None
    check('GPS absent -> SITL SIM2 fallback present', sim2_present, True)
    print('  (SITL log: no GPS messages, using SIM2 trajectory)')

# SIM2
sim2_df = data.get('SIM2')
print()
check('SIM2 exists', sim2_df is not None, True)
if sim2_df is not None and not sim2_df.empty:
    for col in ('PN','PE','PD'):
        if col in sim2_df.columns:
            print(f'  SIM2.{col}: min={sim2_df[col].min():.3f}  max={sim2_df[col].max():.3f}')

# ESCX
escx_df = data.get('ESCX')
print()
check('ESCX exists', escx_df is not None, True)
if escx_df is not None and not escx_df.empty:
    pct_col = next((c for c in ('outpct','OutPct','Outpct') if c in escx_df.columns), None)
    if pct_col:
        mn = escx_df[pct_col].min()
        mx = escx_df[pct_col].max()
        check('ESCX outpct min >= 1%', mn >= 1.0, True)
        check('ESCX outpct max <= 100%', mx <= 100.0, True)
        print(f'  outpct range: {mn:.1f}% to {mx:.1f}%')

print()
print('=' * 65)
print('STEP 4 — GPS Converter (SITL fallback to SIM2)')
print('=' * 65)
from core.gps_converter import best_trajectory
traj = best_trajectory(data)
check('Trajectory found', traj is not None, True)
if traj is not None:
    print(f'  Source: {"SIM2" if "SIM2" in str(traj) else "GPS/other"}')
    print(f'  Points: {len(traj["east"])}')
    print(f'  East range:  {traj["east"].min():.3f} to {traj["east"].max():.3f} m')
    print(f'  North range: {traj["north"].min():.3f} to {traj["north"].max():.3f} m')
    print(f'  Up range:    {traj["up"].min():.3f} to {traj["up"].max():.3f} m')

print()
print('=' * 65)
print('DONE')
print('=' * 65)
