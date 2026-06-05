"""UI Refinement Sprint — stable transport clock + Verify simplification."""
import re

import numpy as np
import pandas as pd
import pytest

from core import verification_model as vmodel

_CLOCK = re.compile(r'^\d{2}:\d{2}(:\d{2})? / \d{2}:\d{2}(:\d{2})?$')


def _data(n=200, dur=120.0):
    t = np.linspace(0.0, dur, n)
    return {
        'POS': pd.DataFrame({'TimeS': t, 'RelHomeAlt': np.clip(t, 0, 40),
                             'Lat': np.linspace(-35.36, -35.355, n),
                             'Lng': np.linspace(149.16, 149.165, n)}),
        'GPS[0]': pd.DataFrame({'TimeS': t, 'Status': np.full(n, 6), 'NSats': np.full(n, 12),
                                'Spd': np.full(n, 2.0), 'Lat': np.linspace(-35.36, -35.355, n),
                                'Lng': np.linspace(149.16, 149.165, n)}),
        'ARM': pd.DataFrame({'TimeS': [5.0, dur - 5], 'ArmState': [1, 0]}),
        'MODE': pd.DataFrame({'TimeS': [5.0], 'Mode': [5]}),
    }


# ── 1. Transport clock: fixed width, monospace, no jitter ────────────────────
class TestTransportClock:
    @pytest.fixture
    def transport(self, qtbot):
        from ui.app_state import AppState
        from ui.widgets.timeline_transport import TimelineTransport
        st = AppState()
        tr = TimelineTransport(st); qtbot.addWidget(tr); tr.resize(800, 74)
        st.set_parsed_data(_data(), b'', '')
        return tr, st

    def test_clock_format_mmss(self, transport):
        tr, st = transport
        st.set_cursor_time(9.0)
        assert _CLOCK.match(tr._time_lbl.text())
        assert tr._time_lbl.text().startswith('00:09 / ')

    def test_width_fixed_across_playback(self, transport):
        tr, st = transport
        st.set_cursor_time(9.0)      # 00:09 / 02:00
        w1 = tr._time_lbl.width()
        st.set_cursor_time(70.0)     # 01:10 / 02:00  (digit count grows)
        w2 = tr._time_lbl.width()
        assert w1 == w2              # never resizes → no jitter
        assert tr._time_lbl.minimumWidth() == tr._time_lbl.maximumWidth()

    def test_monospace_font(self, transport):
        tr, st = transport
        assert tr._time_lbl.font().styleHint() == tr._time_lbl.font().StyleHint.Monospace


# ── 2. Replay controls clock ─────────────────────────────────────────────────
class TestReplayClock:
    def test_mmss_and_fixed_width(self, qtbot):
        from ui.widgets.replay_controls import ReplayControls
        rc = ReplayControls(); qtbot.addWidget(rc)
        rc.set_range(0.0, 120.0)
        rc.set_time(75.0)
        assert rc._time_lbl.text() == '01:15 / 02:00'
        assert rc._time_lbl.minimumWidth() == rc._time_lbl.maximumWidth()

    def test_hours_format_for_long_logs(self, qtbot):
        from ui.widgets.replay_controls import ReplayControls
        rc = ReplayControls(); qtbot.addWidget(rc)
        rc.set_range(0.0, 7200.0)            # 2h → HH:MM:SS
        rc.set_time(3661.0)
        assert rc._time_lbl.text() == '01:01:01 / 02:00:00'


# ── 3/4. Verify carries only integrity content ───────────────────────────────
class TestVerifySimplified:
    @pytest.fixture
    def verify(self, qtbot):
        from ui.tab_verification import VerificationTab

        class _MW:
            def set_key_path_from_panel(self, p): pass
        tab = VerificationTab(_MW()); qtbot.addWidget(tab)
        return tab

    def test_no_analytics_widgets(self, verify):
        # the flight-analysis widgets are gone from Verify
        for attr in ('_cards', '_summary', '_event_table', '_timeline'):
            assert not hasattr(verify, attr), f'Verify still has {attr}'
        assert hasattr(verify, '_sig_panel')

    def test_update_data_injects_no_events_or_faults(self, verify):
        verify.update_data(_data(), b'rawbytes')
        # nothing analytic created; only raw/data retained for verification
        assert verify._raw == b'rawbytes'
        assert not hasattr(verify, '_event_table')

    def test_shows_status_meaning_guidance(self, verify):
        verify.update_verification({'state': 'VERIFIED'})
        sp = verify._sig_panel
        assert sp._badge.text() == vmodel.info('VERIFIED').label
        assert sp._op_lbl.text() == vmodel.info('VERIFIED').operational_meaning
        assert sp._guidance_lbl.text().startswith('Investigator guidance:')
        assert vmodel.info('VERIFIED').investigator_guidance in sp._guidance_lbl.text()

    def test_partial_state_presentation(self, verify):
        verify.update_verification({'state': 'PARTIAL'})
        sp = verify._sig_panel
        assert sp._badge.text() == vmodel.info('PARTIAL').label
        assert sp._op_lbl.text() == vmodel.info('PARTIAL').operational_meaning


# ── Transport is the single playback controller (directional) ────────────────
class TestTransportDirectional:
    @pytest.fixture
    def transport(self, qtbot):
        from ui.app_state import AppState
        from ui.widgets.timeline_transport import TimelineTransport
        st = AppState()
        tr = TimelineTransport(st); qtbot.addWidget(tr); tr.resize(900, 74)
        st.set_parsed_data(_data(dur=120.0), b'', '')
        return tr, st

    def test_all_directional_controls_present_and_visible(self, transport):
        tr, _ = transport
        for a in ('_start_btn', '_stepback_btn', '_rev_btn', '_play_btn',
                  '_fwd_btn', '_stepfwd_btn', '_speed_cb'):
            assert hasattr(tr, a), a
        # restored — no longer hidden
        for w in (tr._start_btn, tr._rev_btn, tr._play_btn, tr._fwd_btn,
                  tr._stepfwd_btn, tr._speed_cb):
            assert not w.isHidden()

    def test_forward_play_advances(self, transport):
        tr, st = transport
        st.set_cursor_time(10.0); tr._speed = 5.0
        tr._play(1); tr._tick(); tr._stop()
        assert st.cursor_time > 10.0

    def test_reverse_play_decreases(self, transport):
        tr, st = transport
        st.set_cursor_time(50.0); tr._speed = 5.0
        tr._play(-1); tr._tick(); tr._stop()
        assert st.cursor_time < 50.0

    def test_step_forward_and_back(self, transport):
        tr, st = transport
        st.set_cursor_time(20.0)
        tr.step(0.5); assert st.cursor_time == pytest.approx(20.5)
        tr.step(-0.5); assert st.cursor_time == pytest.approx(20.0)

    def test_to_start(self, transport):
        tr, st = transport
        st.set_cursor_time(40.0)
        tr._to_start()
        t0, _ = tr._span()
        assert st.cursor_time == pytest.approx(t0)

    def test_play_pause_icon_toggles(self, transport):
        tr, _ = transport
        tr._play(1); assert tr._play_btn.text() == '⏸'
        tr._stop(); assert tr._play_btn.text() == '▶'


# ── Replay window is view-only (no playback) ─────────────────────────────────
class TestReplayViewOnly:
    def test_replay_has_no_playback_controls(self, qtbot):
        from ui.tab_3d_view import View3DTab

        class _MW:
            pass
        v = View3DTab(_MW()); qtbot.addWidget(v)
        assert not hasattr(v, '_replay')          # playback removed from Replay
        assert hasattr(v, '_follow_cb')           # Follow kept (view control)
        assert hasattr(v, '_arrows_cb')           # heading kept

    def test_follow_toggle_updates_state(self, qtbot):
        from ui.tab_3d_view import View3DTab

        class _MW:
            pass
        v = View3DTab(_MW()); qtbot.addWidget(v)
        v._follow_cb.setChecked(False)
        assert v._follow_vehicle is False
        v._follow_cb.setChecked(True)
        assert v._follow_vehicle is True
