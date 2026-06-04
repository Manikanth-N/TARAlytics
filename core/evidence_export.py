"""
Evidence export (P2): render InvestigationSnapshots to JSON and Markdown.

Pure core — consumes InvestigationSnapshot.to_dict(). The PDF exporter lives in the
UI layer (Qt's QTextDocument renders the Markdown), so this module stays Qt-free and
unit-testable. JSON is the machine-readable record; Markdown is the human/PDF report.
"""
from __future__ import annotations
import json
from datetime import datetime

_APP = 'TARAlytics'


def _f(v, fmt='{:.2f}', unit='', none='—'):
    if v is None:
        return none
    s = fmt.format(v)
    if not unit:
        return s
    sep = '' if unit in ('°', '%') else ' '
    return f'{s}{sep}{unit}'


def build_report(snapshots: list, meta: dict | None = None) -> dict:
    meta = dict(meta or {})
    return {
        'application': _APP,
        'report_type': 'investigation_evidence',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'flight': {
            'log_path': meta.get('log_path', ''),
            'serial_number': meta.get('serial_number', ''),
            'firmware': meta.get('firmware', ''),
            'frame_type': meta.get('frame_type', ''),
            'verification_state': meta.get('verification_state', ''),
        },
        'snapshot_count': len(snapshots),
        'snapshots': [s.to_dict() for s in snapshots],
    }


def to_json(snapshots: list, meta: dict | None = None) -> str:
    return json.dumps(build_report(snapshots, meta), indent=2, default=str)


def _control_table(s) -> str:
    rows = ['| Axis | Pilot | Demand | Actual | Δ |', '|---|---|---|---|---|']
    deg = {'roll': '°', 'pitch': '°', 'yaw': '°'}
    for ax in ('roll', 'pitch', 'yaw'):
        p = s.pilot.get(ax); d = s.demand.get(ax); a = s.response.get(ax)
        dv = s.divergence.get(ax)
        rows.append(
            f'| {ax.capitalize()} | {_f(p, "{:+.2f}")} | {_f(d, "{:+.0f}", deg[ax])} '
            f'| {_f(a, "{:+.0f}", deg[ax])} | {_f(dv, "{:.0f}", deg[ax])} |')
    # throttle (0..1, no degrees)
    rows.append(
        f'| Throttle | {_f(s.pilot.get("throttle"), "{:.2f}")} '
        f'| {_f(s.demand.get("throttle"), "{:.2f}")} '
        f'| {_f(s.response.get("throttle"), "{:.2f}")} | — |')
    return '\n'.join(rows)


def _snapshot_md(s) -> str:
    ekf = s.ekf or {}
    pd = s.position_divergence or {}

    pos = '—'
    if s.position:
        pos = '{:.6f}, {:.6f}'.format(s.position['lat'], s.position['lng'])

    flight = ('{} / {}'.format(s.flight_index + 1, s.flight_total)
              if s.flight_index is not None else '— / {}'.format(s.flight_total))

    event_line = ''
    if s.event:
        event_line = '**Event:** {}: {} @ {:.2f} s\n\n'.format(
            s.event['type'], s.event['message'], s.event['time'])

    alt = _f(s.altitude_agl, '{:.1f}', 'm')
    if s.altitude_agl is not None and s.altitude_source:
        alt += ' ({})'.format(s.altitude_source)

    vs = _f(s.vertical_speed, '{:+.2f}', 'm/s')
    if s.vertical_speed is not None and s.vertical_speed_source:
        vs += ' ({})'.format(s.vertical_speed_source)

    gps = s.gps_fix or '—'
    if s.gps_sats is not None:
        gps += ' · {} sats'.format(s.gps_sats)

    ekf_txt = ekf.get('state', '—')
    if ekf.get('ratio') is not None:
        ekf_txt += ' (ratio {:.2f}, {})'.format(ekf['ratio'], ekf.get('worst', ''))

    posdiv = '{} ({})'.format(_f(pd.get('value'), '{:.2f}', 'm'), pd.get('state', '—'))

    lines = [
        '## Snapshot {} — {}'.format(s.index, s.title()),
        '',
        '**Status:** {}  ·  **Captured:** {}  ·  **Flight time:** {:.2f} s  ·  '
        '**Flight window:** {}'.format(s.status, s.captured_at, s.cursor_time, flight),
        '',
        event_line + '| Field | Value |',
        '|---|---|',
        '| Phase | {} |'.format(s.phase or '—'),
        '| Mode | {} |'.format(s.mode or '—'),
        '| Position | {} |'.format(pos),
        '| Altitude (AGL) | {} |'.format(alt),
        '| Vertical speed | {} |'.format(vs),
        '| Ground speed | {} |'.format(_f(s.ground_speed, '{:.1f}', 'm/s')),
        '| GPS | {} |'.format(gps),
        '| EKF health | {} |'.format(ekf_txt),
        '| Position divergence | {} |'.format(posdiv),
        '| Verification | {} |'.format(s.verification_state),
        '',
        '**Control — Pilot / Demand / Actual:**',
        '',
        _control_table(s),
        '',
        '**Notes:** {}'.format(s.notes or '—'),
        '',
        '---',
    ]
    return '\n'.join(lines)


def to_markdown(snapshots: list, meta: dict | None = None) -> str:
    meta = dict(meta or {})
    head = [
        f'# {_APP} — Investigation Evidence',
        '',
        f"**Log:** {meta.get('log_path', '—')}  ",
        f"**Generated:** {datetime.now().isoformat(timespec='seconds')}  ",
        f"**Aircraft:** {meta.get('serial_number', '—')} · "
        f"{meta.get('firmware', '—')} · {meta.get('frame_type', '—')}  ",
        f"**Verification:** {meta.get('verification_state', '—')}  ",
        f"**Snapshots:** {len(snapshots)}",
        '',
        '---',
        '',
    ]
    if not snapshots:
        head.append('_No snapshots captured._')
        return '\n'.join(head)
    return '\n'.join(head) + '\n'.join(_snapshot_md(s) for s in snapshots)
