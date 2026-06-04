"""P2 tests: diagnostics aids, Investigation Snapshot, evidence export
(JSON/Markdown/PDF), AppState snapshot store, and the Evidence module."""
import json
import numpy as np
import pandas as pd
import pytest


def _data():
    """Flight with attitude, RC, GPS, BARO climb-rate, CTUN throttle, and EKF
    innovation/variance messages — enough to exercise every diagnostic + field."""
    n = 200
    t = np.linspace(0.0, 100.0, n)
    return {
        'ATT': pd.DataFrame({'TimeS': t, 'DesRoll': np.zeros(n), 'Roll': np.zeros(n),
                             'DesPitch': np.zeros(n), 'Pitch': np.zeros(n),
                             'DesYaw': np.full(n, 90.0), 'Yaw': np.full(n, 90.0)}),
        'RCIN': pd.DataFrame({'TimeS': t, 'C1': np.full(n, 1500.0), 'C2': np.full(n, 1500.0),
                              'C3': np.full(n, 1450.0), 'C4': np.full(n, 1500.0)}),
        'RCOU': pd.DataFrame({'TimeS': t, 'C1': np.full(n, 1550.0), 'C2': np.full(n, 1550.0),
                              'C3': np.full(n, 1500.0), 'C4': np.full(n, 1550.0)}),
        'PARM': pd.DataFrame({'Name': ['RCMAP_ROLL'], 'Value': [1.0]}),
        'POS': pd.DataFrame({'TimeS': t, 'Lat': np.linspace(-35.36, -35.355, n),
                             'Lng': np.linspace(149.16, 149.165, n),
                             'RelHomeAlt': np.clip(t, 0, 40)}),
        'BARO[0]': pd.DataFrame({'TimeS': t, 'Alt': np.clip(t, 0, 40),
                                 'CRt': np.full(n, 1.5)}),
        'CTUN': pd.DataFrame({'TimeS': t, 'ThO': np.full(n, 0.55)}),
        'GPS[0]': pd.DataFrame({'TimeS': t, 'Status': np.full(n, 6), 'NSats': np.full(n, 12),
                                'Spd': np.full(n, 2.0)}),
        'XKF4[0]': pd.DataFrame({'TimeS': t, 'SV': np.full(n, 0.1), 'SP': np.full(n, 0.1),
                                 'SH': np.full(n, 0.1), 'SM': np.full(n, 0.1),
                                 'FS': np.zeros(n)}),
        'XKF3[0]': pd.DataFrame({'TimeS': t, 'IPN': np.full(n, 0.1), 'IPE': np.full(n, 0.1),
                                 'IPD': np.full(n, 0.05)}),
        'ARM': pd.DataFrame({'TimeS': [10.0, 95.0], 'ArmState': [1, 0]}),
        'MODE': pd.DataFrame({'TimeS': [10.0, 30.0], 'Mode': [0, 5]}),
        'ERR': pd.DataFrame({'TimeS': [60.0], 'Subsys': [11], 'ECode': [2]}),
    }


def _svc(data):
    from core.sample_service import SampleService
    return SampleService(data)


# ── diagnostics ──────────────────────────────────────────────────────────────

class TestDiagnostics:
    def test_vertical_speed_from_baro(self):
        from core import diagnostics as d
        data = _data(); r = d.vertical_speed_at(_svc(data), data, 50.0)
        assert r['value'] == pytest.approx(1.5)
        assert r['source'] == 'BARO[0].CRt'

    def test_vertical_speed_fallback_derivative(self):
        from core import diagnostics as d
        data = _data(); del data['BARO[0]']; del data['CTUN']; del data['GPS[0]']
        r = d.vertical_speed_at(_svc(data), data, 20.0)   # RelHomeAlt ramps 1 m/s
        assert r['value'] == pytest.approx(1.0, abs=0.05)
        assert 'RelHomeAlt' in r['source']

    def test_ekf_ok_caution_critical(self):
        from core import diagnostics as d
        data = _data()
        assert d.ekf_status_at(_svc(data), data, 50.0)['state'] == 'OK'
        data['XKF4[0]']['SP'] = 0.7
        assert d.ekf_status_at(_svc(data), data, 50.0)['state'] == 'CAUTION'
        data['XKF4[0]']['SP'] = 1.3
        assert d.ekf_status_at(_svc(data), data, 50.0)['state'] == 'CRITICAL'

    def test_ekf_fault_flag_forces_critical(self):
        from core import diagnostics as d
        data = _data(); data['XKF4[0]']['FS'] = 2          # fault bitmask set
        r = d.ekf_status_at(_svc(data), data, 50.0)
        assert r['state'] == 'CRITICAL' and r['faults'] == 2

    def test_position_divergence(self):
        from core import diagnostics as d
        data = _data()
        assert d.position_divergence_at(_svc(data), data, 50.0)['state'] == 'OK'
        data['XKF3[0]']['IPN'] = 3.0; data['XKF3[0]']['IPE'] = 4.0   # 5 m
        r = d.position_divergence_at(_svc(data), data, 50.0)
        assert r['value'] == pytest.approx(5.0)
        assert r['state'] == 'CRITICAL'

    def test_absent_sources_are_safe(self):
        from core import diagnostics as d
        svc = _svc({});
        assert d.ekf_status_at(svc, {}, 0.0)['state'] == 'OK'
        assert d.position_divergence_at(svc, {}, 0.0)['value'] is None
        assert d.vertical_speed_at(svc, {}, 0.0)['value'] is None


# ── snapshot ─────────────────────────────────────────────────────────────────

class TestSnapshot:
    def _build(self, t=50.0, **kw):
        from core.snapshot import build_snapshot
        from core.timeline_model import TimelineModel
        from core.rc_model import RCModel
        data = _data()
        return build_snapshot(index=1, svc=_svc(data), tm=TimelineModel(data),
                              rc=RCModel.from_data(data), data=data, t=t,
                              verification_state='VERIFIED', log_path='x.bin', **kw)

    def test_all_fields_captured(self):
        s = self._build(50.0, notes='n', status='FLAGGED')
        assert s.flight_index == 0 and s.flight_total == 1
        assert s.phase == 'HOVER' and s.mode == 'LOITER'
        assert s.altitude_agl is not None and s.altitude_source.startswith('POS')
        assert s.vertical_speed == pytest.approx(1.5)
        assert s.gps_fix == 'RTK_FIXED' and s.gps_sats == 12
        assert s.position and 'lat' in s.position
        assert s.ekf['state'] == 'OK'
        assert s.position_divergence['state'] == 'OK'
        assert s.pilot and s.demand and s.response and s.divergence
        assert s.verification_state == 'VERIFIED'
        assert s.notes == 'n' and s.status == 'FLAGGED'

    def test_nearest_event_within_window(self):
        s = self._build(60.0)                 # ERR at 60
        assert s.event and s.event['type'] == 'ERR'

    def test_no_event_far_from_any(self):
        s = self._build(45.0)                 # >5 s from any event
        assert s.event is None

    def test_to_dict_serializable(self):
        s = self._build()
        json.dumps(s.to_dict(), default=str)  # must not raise

    def test_provenance_for_sampleservice_values(self):
        # t between samples → interpolation with bracket
        s = self._build(50.3)
        prov = s.provenance
        # every required SampleService-derived value is recorded
        for key in ('demand_roll', 'response_roll', 'altitude_agl', 'ground_speed',
                    'gps_status', 'pilot_throttle', 'ekf_worst', 'posdiv_ipn'):
            assert key in prov
        r = prov['demand_roll']
        assert r['msg'] == 'ATT' and r['col'] == 'DesRoll'
        assert r['interpolated'] is True
        assert r['bracket'] is not None and len(r['bracket']) == 2
        assert r['sample_timestamp'] is None          # interpolated → no single sample
        # discrete GPS status: held sample, not interpolated
        g = prov['gps_status']
        assert g['interpolated'] is False
        assert g['sample_timestamp'] is not None and g['bracket'] is None

    def test_provenance_exact_sample(self):
        # t exactly on a sample (t=0.0 is the first ATT sample) → not interpolated
        s = self._build(0.0)
        r = s.provenance['response_roll']
        assert r['interpolated'] is False
        assert r['sample_timestamp'] is not None and r['bracket'] is None


# ── evidence export ──────────────────────────────────────────────────────────

class TestExport:
    def _snaps(self):
        from core.snapshot import build_snapshot
        from core.timeline_model import TimelineModel
        from core.rc_model import RCModel
        data = _data()
        return [build_snapshot(index=1, svc=_svc(data), tm=TimelineModel(data),
                               rc=RCModel.from_data(data), data=data, t=60.0,
                               verification_state='VERIFIED', notes='hit')]

    def test_json_round_trips(self):
        from core import evidence_export as ex
        report = json.loads(ex.to_json(self._snaps(), {'log_path': 'x.bin'}))
        assert report['snapshot_count'] == 1
        assert report['snapshots'][0]['ekf']['state'] == 'OK'

    def test_markdown_contains_key_fields(self):
        from core import evidence_export as ex
        md = ex.to_markdown(self._snaps(), {'verification_state': 'VERIFIED'})
        assert 'Investigation Evidence' in md
        assert 'EKF health' in md and 'Pilot' in md and 'Vertical speed' in md
        assert 'hit' in md

    def test_empty_report(self):
        from core import evidence_export as ex
        assert 'No snapshots' in ex.to_markdown([], {})

    def test_pdf_written(self, qtbot, tmp_path):
        from core import evidence_export as ex
        from ui.modules.mod_evidence import export_pdf
        p = tmp_path / 'ev.pdf'
        export_pdf(ex.to_markdown(self._snaps(), {}), str(p))
        assert p.exists() and p.stat().st_size > 0
        assert p.read_bytes()[:4] == b'%PDF'


def _osc_report():
    """Analytics report on a flight with an injected roll oscillation (→ a finding)."""
    from core.flight_analytics import analyze
    n = 4000; t = np.linspace(0.0, 80.0, n)
    agl = np.interp(t, [0, 5, 10, 50, 72, 80], [0, 0, 20, 20, 0, 0])
    z = np.zeros(n)
    data = {
        'ARM': pd.DataFrame({'TimeS': [5.0, 75.0], 'ArmState': [1, 0]}),
        'MODE': pd.DataFrame({'TimeS': [5.0], 'Mode': [5]}),
        'PARM': pd.DataFrame({'Name': ['RCMAP_ROLL', 'MOT_PWM_MIN', 'MOT_PWM_MAX'],
                              'Value': [1.0, 1000.0, 2000.0]}),
        'ATT': pd.DataFrame({'TimeS': t, 'DesRoll': z.copy(),
                             'Roll': 6.0 * np.sin(2 * np.pi * 4 * t),
                             'DesPitch': z.copy(), 'Pitch': z.copy(),
                             'DesYaw': np.full(n, 90.0), 'Yaw': np.full(n, 90.0)}),
        'RCIN': pd.DataFrame({'TimeS': t, 'C1': np.full(n, 1500.0)}),
        'RCOU': pd.DataFrame({'TimeS': t, 'C1': np.full(n, 1500.0)}),
        'BARO[0]': pd.DataFrame({'TimeS': t, 'Alt': agl, 'CRt': np.gradient(agl, t)}),
        'POS': pd.DataFrame({'TimeS': t, 'RelHomeAlt': agl}),
    }
    return analyze(data), data


class TestNarrativeReport:
    def test_markdown_has_conclusion_and_findings(self):
        from core import evidence_export as ex
        report, _ = _osc_report()
        md = ex.to_markdown([], {'log_path': 'x.bin'}, report)
        assert '## Conclusion' in md and '## Findings' in md
        assert 'Verdict:' in md and 'Roll oscillation' in md
        assert 'Supporting evidence:' in md

    def test_json_includes_flight_assessment(self):
        from core import evidence_export as ex
        report, _ = _osc_report()
        rep = json.loads(ex.to_json([], {}, report))
        assert 'flight_assessment' in rep
        assert rep['flight_assessment']['quality']['verdict'] in (
            'MARGINAL', 'POOR', 'ACCEPTABLE', 'GOOD')

    def test_finding_plot_renders_png(self, qtbot, tmp_path):
        from ui.evidence_plots import render_finding_plot, can_plot
        report, data = _osc_report()
        osc = next(f for f in report.findings if f.category == 'OSCILLATION')
        assert can_plot(data, osc)
        p = tmp_path / 'finding.png'
        assert render_finding_plot(data, osc, str(p))
        assert p.exists() and p.read_bytes()[:8] == b'\x89PNG\r\n\x1a\n'

    def test_markdown_embeds_plot_reference(self):
        from core import evidence_export as ex
        report, _ = _osc_report()
        i = next(k for k, f in enumerate(report.findings) if f.category == 'OSCILLATION')
        md = ex.to_markdown([], {}, report, {i: 'plots/finding.png'})
        assert '![' in md and 'plots/finding.png' in md

    def test_pdf_with_embedded_plots(self, qtbot, tmp_path):
        from core import evidence_export as ex
        from ui.evidence_plots import render_finding_plot
        from ui.modules.mod_evidence import export_pdf
        from PyQt6.QtCore import QUrl
        report, data = _osc_report()
        urls, resources = {}, []
        for i, f in enumerate(report.findings):
            fp = tmp_path / f'f{i}.png'
            if render_finding_plot(data, f, str(fp)):
                u = QUrl.fromLocalFile(str(fp)); urls[i] = u.toString(); resources.append((u, str(fp)))
        out = tmp_path / 'report.pdf'
        export_pdf(ex.to_markdown([], {}, report, urls), str(out), image_resources=resources)
        assert out.read_bytes()[:4] == b'%PDF' and out.stat().st_size > 0


# ── AppState snapshot store ──────────────────────────────────────────────────

class TestAppStateSnapshots:
    def test_capture_appends_and_signals(self, qtbot):
        from ui.app_state import AppState
        st = AppState(); st.set_parsed_data(_data(), b'', 'x.bin')
        fired = []
        st.snapshots_changed.connect(lambda: fired.append(1))
        st.set_cursor_time(50.0)
        s = st.capture_snapshot(notes='a')
        assert s is not None and len(st.snapshots) == 1 and fired
        assert s.index == 1

    def test_remove_and_clear(self, qtbot):
        from ui.app_state import AppState
        st = AppState(); st.set_parsed_data(_data(), b'', '')
        st.capture_snapshot(); st.capture_snapshot()
        st.remove_snapshot(0); assert len(st.snapshots) == 1
        st.clear_snapshots(); assert len(st.snapshots) == 0

    def test_cleared_on_reload(self, qtbot):
        from ui.app_state import AppState
        st = AppState(); st.set_parsed_data(_data(), b'', '')
        st.capture_snapshot(); assert len(st.snapshots) == 1
        st.set_parsed_data(_data(), b'', '')         # reload
        assert len(st.snapshots) == 0

    def test_capture_without_data_returns_none(self):
        from ui.app_state import AppState
        st = AppState()
        assert st.capture_snapshot() is None


# ── Evidence module ──────────────────────────────────────────────────────────

@pytest.fixture
def evidence(qtbot):
    from ui.app_state import AppState
    from ui.modules.mod_evidence import EvidenceModule
    st = AppState()
    m = EvidenceModule(st)
    qtbot.addWidget(m)
    st.set_parsed_data(_data(), b'', 'x.bin')
    return m, st


class TestEvidenceModule:
    def test_capture_button_adds_row(self, evidence):
        m, st = evidence
        st.set_cursor_time(50.0)
        m._b_capture.click()
        assert m._list.rowCount() == 1

    def test_select_shows_detail_and_moves_cursor(self, evidence):
        m, st = evidence
        st.set_cursor_time(60.0); st.capture_snapshot()
        st.set_cursor_time(80.0); st.capture_snapshot()
        st.set_cursor_time(0.0)
        m._list.selectRow(1)                           # selection change → re-investigate
        assert len(m._detail.toPlainText()) > 50
        assert st.cursor_time == pytest.approx(80.0)

    def test_status_and_notes_edit_persist(self, evidence):
        m, st = evidence
        st.set_cursor_time(50.0); st.capture_snapshot()
        m._list.selectRow(0)
        m._status.setCurrentText('FLAGGED')
        assert st.snapshots.all()[0].status == 'FLAGGED'
        m._notes.setText('xyz'); m._on_notes_changed()
        assert st.snapshots.all()[0].notes == 'xyz'

    def test_delete(self, evidence):
        m, st = evidence
        st.capture_snapshot(); m._list.selectRow(0)
        m._delete_selected()
        assert len(st.snapshots) == 0

    def test_export_writes_all_formats(self, evidence, tmp_path, monkeypatch):
        from PyQt6.QtWidgets import QFileDialog
        m, st = evidence
        st.set_cursor_time(60.0); st.capture_snapshot(notes='hit')
        for kind, ext in (('json', 'json'), ('md', 'md'), ('pdf', 'pdf')):
            out = tmp_path / f'r.{ext}'
            monkeypatch.setattr(QFileDialog, 'getSaveFileName',
                                staticmethod(lambda *a, **k: (str(out), '')))
            m._export(kind)
            assert out.exists() and out.stat().st_size > 0
