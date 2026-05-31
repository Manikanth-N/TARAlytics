"""UI tests for ReplayControls using pytest-qt."""
import pytest
from PyQt6.QtCore import Qt

from ui.widgets.replay_controls import ReplayControls


@pytest.fixture
def replay(qtbot):
    ctrl = ReplayControls()
    qtbot.addWidget(ctrl)
    ctrl.show()
    return ctrl


@pytest.fixture
def replay_with_range(replay):
    replay.set_range(10.0, 60.0)
    return replay


class TestReplayControlsInit:
    def test_not_playing_initially(self, replay):
        assert replay._playing is False

    def test_timer_not_active_initially(self, replay):
        assert not replay._timer.isActive()

    def test_default_speed_is_1x(self, replay):
        assert replay._speed == 1.0

    def test_play_button_shows_play(self, replay):
        assert 'Play' in replay._play_btn.text()


class TestReplaySetRange:
    def test_range_stored(self, replay_with_range):
        assert replay_with_range._t_min == 10.0
        assert replay_with_range._t_max == 60.0

    def test_current_set_to_t_min(self, replay_with_range):
        assert replay_with_range._current == 10.0

    def test_scrubber_at_zero(self, replay_with_range):
        assert replay_with_range._scrubber.value() == 0

    def test_degenerate_range_handled(self, replay):
        replay.set_range(5.0, 5.0)  # t_max == t_min → should not crash
        assert replay._t_max > replay._t_min


class TestReplayPlayPause:
    def test_play_starts_timer(self, replay_with_range, qtbot):
        qtbot.mouseClick(replay_with_range._play_btn, Qt.MouseButton.LeftButton)
        assert replay_with_range._playing is True
        assert replay_with_range._timer.isActive()

    def test_play_button_shows_pause_when_playing(self, replay_with_range, qtbot):
        qtbot.mouseClick(replay_with_range._play_btn, Qt.MouseButton.LeftButton)
        assert 'Pause' in replay_with_range._play_btn.text()

    def test_pause_stops_timer(self, replay_with_range, qtbot):
        qtbot.mouseClick(replay_with_range._play_btn, Qt.MouseButton.LeftButton)
        qtbot.mouseClick(replay_with_range._play_btn, Qt.MouseButton.LeftButton)
        assert replay_with_range._playing is False
        assert not replay_with_range._timer.isActive()

    def test_play_button_shows_play_after_pause(self, replay_with_range, qtbot):
        qtbot.mouseClick(replay_with_range._play_btn, Qt.MouseButton.LeftButton)
        qtbot.mouseClick(replay_with_range._play_btn, Qt.MouseButton.LeftButton)
        assert 'Play' in replay_with_range._play_btn.text()

    def test_reset_stops_playback(self, replay_with_range, qtbot):
        qtbot.mouseClick(replay_with_range._play_btn, Qt.MouseButton.LeftButton)
        qtbot.mouseClick(replay_with_range._reset_btn, Qt.MouseButton.LeftButton)
        assert replay_with_range._playing is False
        assert replay_with_range._current == 10.0

    def test_play_restarts_from_min_if_at_end(self, replay_with_range, qtbot):
        replay_with_range._current = replay_with_range._t_max
        qtbot.mouseClick(replay_with_range._play_btn, Qt.MouseButton.LeftButton)
        assert replay_with_range._current == replay_with_range._t_min


class TestReplayScrubber:
    def test_scrub_emits_time_changed(self, replay_with_range, qtbot):
        received = []
        replay_with_range.time_changed.connect(received.append)
        replay_with_range._scrubber.sliderMoved.emit(5000)  # mid-point
        assert len(received) == 1
        assert abs(received[0] - 35.0) < 0.5  # mid of [10, 60]

    def test_set_time_clamps_to_range(self, replay_with_range):
        replay_with_range.set_time(0.0)   # below t_min
        assert replay_with_range._current == 10.0
        replay_with_range.set_time(999.0)  # above t_max
        assert replay_with_range._current == 60.0

    def test_set_time_updates_slider(self, replay_with_range):
        replay_with_range.set_time(35.0)  # midpoint of [10, 60]
        val = replay_with_range._scrubber.value()
        assert 4900 <= val <= 5100  # approximately 5000

    def test_set_time_updates_label(self, replay_with_range):
        replay_with_range.set_time(25.0)
        assert '25.00' in replay_with_range._time_lbl.text()


class TestReplaySpeed:
    def test_speed_buttons_exist(self, replay):
        assert len(replay._speed_btns) == 5

    def test_default_1x_checked(self, replay):
        for spd, btn in replay._speed_btns:
            if spd == 1.0:
                assert btn.isChecked()
            else:
                assert not btn.isChecked()

    def test_set_speed_updates_state(self, replay):
        replay._set_speed(2.0)
        assert replay._speed == 2.0
        for spd, btn in replay._speed_btns:
            assert btn.isChecked() == (spd == 2.0)

    def test_tick_advances_by_speed_x_dt(self, replay_with_range):
        replay_with_range._speed = 2.0
        before = replay_with_range._current
        replay_with_range._tick()
        after = replay_with_range._current
        # dt = 0.033s × speed 2.0 = 0.066s advance
        assert abs((after - before) - 0.066) < 0.005


class TestReplayFollowCheckbox:
    def test_follow_checked_by_default(self, replay):
        assert replay._follow_cb.isChecked()

    def test_follow_signal_emitted_on_toggle(self, replay, qtbot):
        received = []
        replay.follow_changed.connect(received.append)
        replay._follow_cb.setChecked(False)
        assert len(received) == 1
        assert received[0] is False
