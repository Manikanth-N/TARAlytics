"""PlaybackController Phase A — isolated unit tests.

The controller is the single playback engine (one timer, one play flag, one speed)
that drives the shared cursor. Phase A only adds it + AppState.playback; it is not yet
wired to any view, so these tests exercise it directly. _tick() is called explicitly for
determinism (no reliance on the live QTimer).
"""
import pytest

from ui.app_state import AppState


@pytest.fixture
def app_state(qtbot):
    return AppState()


class TestLazyWiring:
    def test_appstate_playback_is_lazy_singleton(self, app_state):
        pb = app_state.playback
        assert pb is app_state.playback              # same instance on repeat
        assert pb.is_playing is False and pb.speed == 1.0

    def test_two_appstates_have_independent_controllers(self, qtbot):
        a, b = AppState(), AppState()
        a.playback.set_span(0, 10); a.playback.play()
        assert a.playback.is_playing is True
        assert b.playback.is_playing is False         # multi-instance isolation


class TestPlayState:
    def test_play_pause_toggle_and_signal(self, app_state):
        pb = app_state.playback; pb.set_span(0, 10)
        seen = []
        pb.playing_changed.connect(seen.append)
        pb.play();   assert pb.is_playing is True
        pb.toggle(); assert pb.is_playing is False
        assert seen == [True, False]

    def test_tick_advances_cursor_by_speed(self, app_state):
        pb = app_state.playback; pb.set_span(0, 100)
        app_state.set_cursor_time(0.0)
        pb.play(); pb._tick()
        assert app_state.cursor_time == pytest.approx(0.033, abs=1e-6)
        pb.set_speed(2.0); pb._tick()
        assert app_state.cursor_time == pytest.approx(0.033 + 0.066, abs=1e-6)

    def test_speed_change_emits(self, app_state):
        pb = app_state.playback
        seen = []
        pb.speed_changed.connect(seen.append)
        pb.set_speed(5.0); pb.set_speed(5.0)          # second is a no-op
        assert seen == [5.0] and pb.speed == 5.0


class TestSeekStepBounds:
    def test_seek_clamps_to_span(self, app_state):
        pb = app_state.playback; pb.set_span(2, 8)
        pb.seek(100); assert app_state.cursor_time == 8.0
        pb.seek(-5);  assert app_state.cursor_time == 2.0

    def test_step_moves_relative(self, app_state):
        pb = app_state.playback; pb.set_span(0, 10)
        app_state.set_cursor_time(5.0)
        pb.step(0.5);  assert app_state.cursor_time == pytest.approx(5.5)
        pb.step(-1.0); assert app_state.cursor_time == pytest.approx(4.5)

    def test_tick_stops_at_end_of_span(self, app_state):
        pb = app_state.playback; pb.set_span(0, 1)
        app_state.set_cursor_time(0.99)
        pb.play(); pb._tick()                          # 0.99 + 0.033 > 1.0
        assert app_state.cursor_time == 1.0
        assert pb.is_playing is False                  # auto-paused at the end

    def test_play_from_end_restarts(self, app_state):
        pb = app_state.playback; pb.set_span(0, 5)
        app_state.set_cursor_time(5.0)
        pb.play()
        assert app_state.cursor_time == 0.0            # parked at end → restart
        assert pb.is_playing is True
