"""
Failure Testing Sprint — adversarial / robustness tests (RC hardening).

Areas: corrupted logs, truncated logs, missing messages, invalid signatures,
workspace persistence, pop-out panels, replay transitions, cancel/reload flows.
(Huge-log + long soak live in scripts/soak_test.py.)

Goal: no crashes, hangs, or state corruption; degraded inputs degrade gracefully.
"""
import os
import struct
import numpy as np
import pandas as pd
import pytest

from core.log_parser import DataFlashParser
from core import signature_verifier as sv
from core.flight_analytics import analyze
from core.snapshot import build_snapshot
from core.timeline_model import TimelineModel
from core.rc_model import RCModel
from core.sample_service import SampleService

LOG02 = 'logs/00000002.BIN'
_HAS_LOG = os.path.isfile(LOG02)


def _raw():
    return open(LOG02, 'rb').read()


# ── 1. Corrupted logs ────────────────────────────────────────────────────────

class TestCorrupted:
    def test_pure_random_bytes(self):
        for n in (0, 1, 63, 64, 1000, 100_000):
            data = os.urandom(n)
            with open('/tmp/_corrupt.bin', 'wb') as f:
                f.write(data)
            r = DataFlashParser().parse('/tmp/_corrupt.bin')
            assert isinstance(r, dict)            # never crashes; returns a dict

    def test_signed_magic_then_garbage(self):
        data = sv.SIGNED_MAGIC + os.urandom(200_000)
        open('/tmp/_corrupt.bin', 'wb').write(data)
        r = DataFlashParser().parse('/tmp/_corrupt.bin')
        assert isinstance(r, dict)

    @pytest.mark.skipif(not _HAS_LOG, reason='log 02 missing')
    def test_bitflipped_real_log(self):
        raw = bytearray(_raw())
        rng = np.random.default_rng(0)
        for idx in rng.integers(0, len(raw), size=4000):
            raw[idx] ^= 0xFF
        open('/tmp/_corrupt.bin', 'wb').write(bytes(raw))
        r = DataFlashParser().parse('/tmp/_corrupt.bin')
        assert isinstance(r, dict)               # partial or empty, no crash

    def test_garbage_fmt_records(self):
        # A3 95 80 header followed by random format/labels
        blob = bytes([0xA3, 0x95, 0x80]) + os.urandom(86)
        blob *= 50
        open('/tmp/_corrupt.bin', 'wb').write(blob)
        r = DataFlashParser().parse('/tmp/_corrupt.bin')
        assert isinstance(r, dict)

    def test_analytics_on_corrupt(self):
        open('/tmp/_corrupt.bin', 'wb').write(os.urandom(50_000))
        data = DataFlashParser().parse('/tmp/_corrupt.bin')
        rep = analyze(data)                      # must not crash on junk
        assert rep.quality.verdict in ('NO DATA', 'GOOD', 'ACCEPTABLE', 'MARGINAL', 'POOR')


# ── 2. Truncated logs ────────────────────────────────────────────────────────

class TestTruncated:
    @pytest.mark.skipif(not _HAS_LOG, reason='log 02 missing')
    def test_truncate_at_many_offsets(self):
        raw = _raw()
        for frac in (0.0, 0.001, 0.01, 0.1, 0.5, 0.9, 0.999):
            cut = int(len(raw) * frac)
            open('/tmp/_trunc.bin', 'wb').write(raw[:cut])
            r = DataFlashParser().parse('/tmp/_trunc.bin')
            assert isinstance(r, dict)
            # any frames present must still have valid TimeS
            for df in r.values():
                if 'TimeS' in df.columns and not df.empty:
                    assert np.isfinite(df['TimeS']).all()

    @pytest.mark.skipif(not _HAS_LOG, reason='log 02 missing')
    def test_truncated_signed_extract(self):
        raw = _raw()
        # chop the trailer + tail → still extracts the chunks present
        out = sv.extract_signed_data(raw[: int(len(raw) * 0.8)])
        assert out is None or isinstance(out, (bytes, bytearray))


# ── 3. Missing messages ──────────────────────────────────────────────────────

def _full():
    n = 300; t = np.linspace(0, 100, n)
    return {
        'ATT': pd.DataFrame({'TimeS': t, 'DesRoll': np.zeros(n), 'Roll': np.sin(t),
                             'DesPitch': np.zeros(n), 'Pitch': np.zeros(n),
                             'DesYaw': np.full(n, 90.0), 'Yaw': np.full(n, 90.0)}),
        'RCIN': pd.DataFrame({'TimeS': t, 'C1': np.full(n, 1500.0)}),
        'RCOU': pd.DataFrame({'TimeS': t, 'C1': np.full(n, 1500.0)}),
        'PARM': pd.DataFrame({'Name': ['RCMAP_ROLL'], 'Value': [1.0]}),
        'POS': pd.DataFrame({'TimeS': t, 'RelHomeAlt': np.clip(t, 0, 40)}),
        'GPS[0]': pd.DataFrame({'TimeS': t, 'Status': np.full(n, 6), 'NSats': np.full(n, 12),
                                'Spd': np.full(n, 2.0)}),
        'ARM': pd.DataFrame({'TimeS': [5.0, 95.0], 'ArmState': [1, 0]}),
        'MODE': pd.DataFrame({'TimeS': [5.0], 'Mode': [5]}),
    }


class TestMissingMessages:
    @pytest.mark.parametrize('drop', [[], ['ATT'], ['GPS[0]'], ['MODE'], ['ARM'],
                                      ['POS'], ['ATT', 'GPS[0]', 'MODE', 'ARM', 'POS'],
                                      ['RCIN', 'RCOU', 'PARM']])
    def test_analytics_degrade(self, drop):
        data = {k: v for k, v in _full().items() if k not in drop}
        rep = analyze(data)
        assert rep.quality.verdict in ('NO DATA', 'GOOD', 'ACCEPTABLE', 'MARGINAL', 'POOR')

    def test_empty_data_everywhere(self):
        data = {}
        assert analyze(data).quality.verdict == 'NO DATA'
        tm = TimelineModel(data); tm.build(); tm.phase_at(0); tm.mode_at(0)
        svc = SampleService(data); assert svc.value_at('ATT', 'Roll', 0) is None
        rc = RCModel.from_data(data)
        s = build_snapshot(index=1, svc=svc, tm=tm, rc=rc, data=data, t=0.0,
                           verification_state='NONE')
        assert s.provenance is not None

    def test_snapshot_with_missing(self):
        data = {k: v for k, v in _full().items() if k not in ('GPS[0]', 'ATT')}
        tm = TimelineModel(data); svc = SampleService(data); rc = RCModel.from_data(data)
        s = build_snapshot(index=1, svc=svc, tm=tm, rc=rc, data=data, t=50.0,
                           verification_state='X')
        assert s.gps_fix is None and s.position is None


# ── 4. Invalid signatures ────────────────────────────────────────────────────

class TestSignatures:
    def test_full_verify_on_random(self):
        for n in (0, 64, 200, 10_000):
            res = sv.full_verify(os.urandom(n), None)
            assert isinstance(res, dict) and 'state' in res

    @pytest.mark.skipif(not _HAS_LOG, reason='log 02 missing')
    def test_tampered_signed_log(self):
        raw = bytearray(_raw())
        # flip bytes inside the signed body
        for i in range(2000, 5000, 7):
            raw[i] ^= 0x55
        res = sv.full_verify(bytes(raw), None)
        assert res['state'] != 'VERIFIED'           # tamper not silently accepted

    @pytest.mark.skipif(not _HAS_LOG, reason='log 02 missing')
    def test_wrong_pubkey_fingerprint(self):
        raw = _raw()
        res = sv.full_verify(raw, 'AAAA' * 16)       # bogus key
        assert isinstance(res, dict) and 'state' in res

    def test_extract_handles_bad_chunk_offsets(self):
        # signed header + a CHUNK record pointing out of range
        body = bytearray(sv.SIGNED_MAGIC + bytes(62))
        body += struct.pack('<III32s', sv.CHUNK_MAGIC, 10**9, 10**9, b'\x00' * 32)
        out = sv.extract_signed_data(bytes(body))
        assert out is None or isinstance(out, bytes)   # no crash, no over-read


# ── 6. Workspace persistence ─────────────────────────────────────────────────

def _ui_data(n=200, dur=80.0, roll_amp=1.0):
    t = np.linspace(0, dur, n)
    return {
        'ATT': pd.DataFrame({'TimeS': t, 'DesRoll': np.zeros(n), 'Roll': roll_amp*np.sin(t),
                             'DesPitch': np.zeros(n), 'Pitch': np.zeros(n),
                             'DesYaw': np.full(n, 90.0), 'Yaw': np.full(n, 90.0)}),
        'RCIN': pd.DataFrame({'TimeS': t, 'C1': np.full(n, 1500.0)}),
        'RCOU': pd.DataFrame({'TimeS': t, 'C1': np.full(n, 1500.0)}),
        'PARM': pd.DataFrame({'Name': ['RCMAP_ROLL'], 'Value': [1.0]}),
        'POS': pd.DataFrame({'TimeS': t, 'RelHomeAlt': np.clip(t, 0, 40),
                             'Lat': np.linspace(-35.36, -35.355, n),
                             'Lng': np.linspace(149.16, 149.165, n)}),
        'GPS[0]': pd.DataFrame({'TimeS': t, 'Status': np.full(n, 6), 'NSats': np.full(n, 12),
                                'Spd': np.full(n, 2.0), 'Lat': np.linspace(-35.36, -35.355, n),
                                'Lng': np.linspace(149.16, 149.165, n)}),
        'ARM': pd.DataFrame({'TimeS': [5.0, 75.0], 'ArmState': [1, 0]}),
        'MODE': pd.DataFrame({'TimeS': [5.0, 40.0], 'Mode': [0, 5]}),
        'ERR': pd.DataFrame({'TimeS': [50.0], 'Subsys': [11], 'ECode': [2]}),
    }


class TestWorkspacePersistence:
    def test_save_survives_new_instance(self, qtbot):
        from ui.app_state import AppState
        from ui.modules.mod_workspace import WorkspaceModule
        from PyQt6.QtCore import QSettings
        QSettings('TARAlyticsAnalyzer', 'Workspace').remove('layouts')
        st = AppState(); st.set_parsed_data(_ui_data(), b'', '')
        ws = WorkspaceModule(st, None); qtbot.addWidget(ws)
        ws._custom['Bench'] = ['signals', 'map']; ws._store_custom()
        ws2 = WorkspaceModule(st, None); qtbot.addWidget(ws2)
        assert 'Bench' in ws2._custom
        QSettings('TARAlyticsAnalyzer', 'Workspace').remove('layouts')

    def test_corrupt_settings_no_crash(self, qtbot):
        from ui.app_state import AppState
        from ui.modules.mod_workspace import WorkspaceModule
        from PyQt6.QtCore import QSettings
        QSettings('TARAlyticsAnalyzer', 'Workspace').setValue('layouts', '{not valid json')
        st = AppState()
        ws = WorkspaceModule(st, None); qtbot.addWidget(ws)   # must not raise
        assert ws._custom == {}
        QSettings('TARAlyticsAnalyzer', 'Workspace').remove('layouts')


# ── 7. Pop-out panels ────────────────────────────────────────────────────────

class TestPopOutStress:
    def test_repeated_popout_redock(self, qtbot):
        from ui.main_window import MainWindow
        w = MainWindow(); qtbot.addWidget(w)
        w.data_ready.emit(_ui_data())
        ws = w._mod_workspace; ws.set_layout('Pilot Analysis')
        for _ in range(12):
            ws._popout('horizon')
            assert 'horizon' in ws._floating
            ws._floating['horizon'].close()
            assert 'horizon' not in ws._floating
        # still synced and not crashed
        w._app_state.set_cursor_time(40.0)
        assert ws._panels['horizon']._has

    def test_multiple_floating_then_relayout(self, qtbot):
        from ui.main_window import MainWindow
        w = MainWindow(); qtbot.addWidget(w)
        w.data_ready.emit(_ui_data())
        ws = w._mod_workspace; ws.set_layout('Pilot Analysis')
        ws._popout('horizon'); ws._popout('rc')
        ws.set_layout('Accident Investigation')      # relayout while floating
        ws.set_layout('Pilot Analysis')
        for k in list(ws._floating):
            ws._floating[k].close()
        assert ws._floating == {}


# ── 8. Replay state transitions ──────────────────────────────────────────────

class TestReplayTransitions:
    def test_transport_rapid_transitions(self, qtbot):
        from ui.app_state import AppState
        from ui.widgets.timeline_transport import TimelineTransport
        st = AppState(); tr = TimelineTransport(st); qtbot.addWidget(tr)
        st.set_parsed_data(_ui_data(), b'', '')
        for _ in range(5):
            tr.toggle_play(); tr._tick(); tr.toggle_play()
            tr._reset(); tr._tick()
        # play to the very end repeatedly
        t0, t1 = tr._span(); st.set_cursor_time(t1)
        tr.toggle_play(); tr._tick()
        assert st.cursor_time <= t1 + 1e-6

    def test_reload_during_play(self, qtbot):
        from ui.app_state import AppState
        from ui.widgets.timeline_transport import TimelineTransport
        st = AppState(); tr = TimelineTransport(st); qtbot.addWidget(tr)
        st.set_parsed_data(_ui_data(dur=80), b'', '')
        tr.toggle_play(); tr._tick()
        st.set_parsed_data(_ui_data(dur=200), b'', '')   # reload mid-play
        tr._tick()                                       # must not crash on new span
        assert tr._span()[1] == pytest.approx(200.0, abs=1.0)

    def test_replay_controls_rapid(self, qtbot):
        from ui.widgets.replay_controls import ReplayControls
        rc = ReplayControls(); qtbot.addWidget(rc)
        rc.set_range(0.0, 100.0)
        for _ in range(20):
            rc.toggle_play(); rc.step(0.5); rc.step(-0.5); rc._reset()
        # no crash; current within range
        assert 0.0 <= rc._current <= 100.0


# ── 9. Cancel / reload flows ─────────────────────────────────────────────────

class TestReloadFlows:
    def test_mainwindow_reload_different_logs(self, qtbot):
        from ui.main_window import MainWindow
        w = MainWindow(); qtbot.addWidget(w)
        w.data_ready.emit(_ui_data(dur=80, roll_amp=1.0))
        w._app_state.set_cursor_time(40.0)
        subs1 = sorted(w._app_state.cursor_debug_info()['subscribers'])
        w.data_ready.emit(_ui_data(dur=200, roll_amp=20.0))   # reload
        assert w._app_state.cursor_time == 0.0               # cursor reset
        assert w._app_state.timeline_model.log_span()[1] == pytest.approx(200.0, abs=1.0)
        # no subscriber leak across reload (signals re-used, not duplicated)
        subs2 = sorted(w._app_state.cursor_debug_info()['subscribers'])
        assert subs2 == subs1

    def test_reload_clears_snapshots(self, qtbot):
        from ui.app_state import AppState
        st = AppState(); st.set_parsed_data(_ui_data(), b'', '')
        st.set_cursor_time(40.0); st.capture_snapshot()
        assert len(st.snapshots) == 1
        st.set_parsed_data(_ui_data(), b'', '')
        assert len(st.snapshots) == 0

    def test_reload_while_workspace_floating(self, qtbot):
        from ui.main_window import MainWindow
        w = MainWindow(); qtbot.addWidget(w)
        w.data_ready.emit(_ui_data())
        ws = w._mod_workspace; ws.set_layout('Pilot Analysis'); ws._popout('horizon')
        w.data_ready.emit(_ui_data(dur=150))   # reload with a panel floating
        w._app_state.set_cursor_time(70.0)
        assert ws._panels['horizon']._has      # floating panel got new data + cursor
        ws._floating['horizon'].close()

    def test_parse_error_recovers(self, qtbot):
        from ui.main_window import MainWindow
        w = MainWindow(); qtbot.addWidget(w)
        w._overlay.start()
        w._on_parse_error('boom')
        assert not w._overlay.isVisible()
        assert w._parse_btn.isEnabled()


# ── 10. Long-duration soak (object-count leak detector) ──────────────────────

class TestSoakNoLeak:
    def test_no_object_leak_across_reloads(self, qtbot):
        """Live DataFrame / widget counts must stay bounded across many reloads +
        cursor moves + layout switches + pop-out/redock (RSS may fluctuate with the
        allocator, but live objects must not grow)."""
        import gc
        from ui.main_window import MainWindow
        w = MainWindow(); qtbot.addWidget(w)
        ws = w._mod_workspace
        layouts = ['Pilot Analysis', 'Accident Investigation', 'Certification']

        def live_counts():
            gc.collect()
            dfs = sum(1 for o in gc.get_objects() if type(o) is pd.DataFrame)
            frames = len(ws._frames)
            return dfs, frames

        for c in range(1, 9):                       # warm up
            w.data_ready.emit(_ui_data(seed=c) if False else _ui_data())
        base_df, _ = live_counts()
        for c in range(9, 25):
            w.data_ready.emit(_ui_data())
            sp = w._app_state.timeline_model.log_span()
            for tt in np.linspace(sp[0], sp[1], 15):
                w._app_state.set_cursor_time(float(tt))
            ws.set_layout(layouts[c % 3])
            ws._popout('horizon'); ws._floating['horizon'].close()
            w._app_state.capture_snapshot()
        end_df, end_frames = live_counts()
        # exactly one log's worth of DataFrames is retained (no accumulation)
        assert end_df <= base_df + 2
        # frame cache is bounded by the number of distinct surfaces (not per-cycle)
        assert end_frames <= 10
        # snapshots cleared on each reload → bounded
        assert len(w._app_state.snapshots) <= 1


# ── 5. Huge log (smoke; skipped if absent) ───────────────────────────────────

class TestHuge:
    @pytest.mark.skipif(not os.path.isfile('logs/00000012.BIN'), reason='440MB log absent')
    @pytest.mark.slow
    def test_huge_parse_and_analyze(self):
        data = DataFlashParser().parse('logs/00000012.BIN')
        assert len(data) > 50
        rep = analyze(data)
        assert rep.quality.verdict in ('GOOD', 'ACCEPTABLE', 'MARGINAL', 'POOR')
