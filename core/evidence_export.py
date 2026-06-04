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


def build_report(snapshots: list, meta: dict | None = None, report=None) -> dict:
    meta = dict(meta or {})
    out = {
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
    if report is not None:
        out['flight_assessment'] = report.to_dict()
    return out


def to_json(snapshots: list, meta: dict | None = None, report=None) -> str:
    return json.dumps(build_report(snapshots, meta, report), indent=2, default=str)


def _conclusion_md(report) -> str:
    q = report.quality
    sc = report.scorecard
    score = '—' if q.score is None else f'{q.score:.0f}'
    lines = ['## Conclusion', '',
             f'**Verdict: {q.verdict} ({score}/100)**', '',
             q.headline, '']
    if q.factors:
        lines.append('Drivers: ' + ' · '.join(q.factors))
        lines.append('')
    lines += ['| Category | Score | Grade |', '|---|---|---|']
    if sc.overall is not None:
        lines.append(f'| **Overall** | **{sc.overall:.0f}** | **{sc.grade}** |')
    for c in sc.categories:
        s = '—' if c.score is None else f'{c.score:.0f}'
        lines.append(f'| {c.name} | {s} | {c.grade or "—"} |')
    lines += ['',
              f'**Flight:** {report.flight_count} flight(s), '
              f'{report.armed_duration_s:.0f} s armed.', '', '---', '']
    return '\n'.join(lines)


def _findings_md(report, plot_paths: dict | None) -> str:
    if not report.findings:
        return '## Findings\n\n_No automated findings — clean flight._\n\n---\n'
    out = [f'## Findings ({len(report.findings)})', '']
    for i, f in enumerate(report.findings):
        when = f' @ {f.t_start:.1f} s' if f.t_start is not None else ''
        out += [f'### {i + 1}. [{f.severity}] {f.category} — {f.title}', '',
                f'{f.detail}{when}', '']
        if f.evidence:
            out.append('**Supporting evidence:** ' + ', '.join(f'`{e}`' for e in f.evidence))
            out.append('')
        if plot_paths and i in plot_paths:
            out.append(f'![{f.title}]({plot_paths[i]})')
            out.append('')
        out.append('---'); out.append('')
    return '\n'.join(out)


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
        _provenance_table(s),
        '---',
    ]
    return '\n'.join(lines)


def _provenance_table(s) -> str:
    """Data provenance for every SampleService-derived value (P2.1): source field,
    sample timestamp, interpolated flag, bracketing sample times."""
    prov = getattr(s, 'provenance', None) or {}
    if not prov:
        return ''
    rows = ['<details><summary>Data provenance ({} sampled values)</summary>'.format(len(prov)),
            '', '| Field | Source | Value | Sample t (s) | Interp. | Bracket (s) |',
            '|---|---|---|---|---|---|']
    for key, p in prov.items():
        val = '—' if p['value'] is None else '{:.4g}'.format(p['value'])
        st = '—' if p['sample_timestamp'] is None else '{:.3f}'.format(p['sample_timestamp'])
        br = '—'
        if p.get('bracket'):
            br = '{:.3f}–{:.3f}'.format(p['bracket'][0], p['bracket'][1])
        rows.append('| {} | {}.{} | {} | {} | {} | {} |'.format(
            key, p['msg'], p['col'], val, st, 'yes' if p['interpolated'] else 'no', br))
    rows.append('')
    rows.append('</details>')
    rows.append('')
    return '\n'.join(rows)


def to_markdown(snapshots: list, meta: dict | None = None, report=None,
                plot_paths: dict | None = None) -> str:
    meta = dict(meta or {})
    verdict = ''
    if report is not None and report.quality.score is not None:
        verdict = f"**Assessment:** {report.quality.verdict} " \
                  f"({report.quality.score:.0f}/100)  "
    head = [
        f'# {_APP} — Investigation Evidence',
        '',
        f"**Log:** {meta.get('log_path', '—')}  ",
        f"**Generated:** {datetime.now().isoformat(timespec='seconds')}  ",
        f"**Aircraft:** {meta.get('serial_number', '—')} · "
        f"{meta.get('firmware', '—')} · {meta.get('frame_type', '—')}  ",
        f"**Verification:** {meta.get('verification_state', '—')}  ",
    ]
    if verdict:
        head.append(verdict)
    head += [f"**Snapshots:** {len(snapshots)}", '', '---', '']

    body = []
    if report is not None:
        body.append(_conclusion_md(report))
        body.append(_findings_md(report, plot_paths))
    if snapshots:
        body.append('## Investigation Snapshots')
        body.append('')
        body.append('\n'.join(_snapshot_md(s) for s in snapshots))
    elif report is None:
        body.append('_No snapshots captured._')
    return '\n'.join(head) + '\n' + '\n'.join(body)
