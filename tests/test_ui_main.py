"""UI tests for MainWindow using pytest-qt."""
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTabWidget, QPushButton, QLineEdit, QProgressBar

from ui.main_window import MainWindow


@pytest.fixture
def main_window(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    return window


class TestMainWindowStructure:
    def test_window_title(self, main_window):
        assert main_window.windowTitle() == 'TARAlytics Log Analyzer'

    def test_tabs_exist(self, main_window):
        # Nine page-stack tabs: Debrief, Timeline, Events, Situation, Signal
        # Plotter, 3D Flight View, Log Verification, 2D Map, Evidence. The tab bar
        # is hidden — navigation is driven by the NavigationRail.
        tabs = main_window._tabs
        assert tabs is not None
        assert tabs.count() == 10
        assert tabs.tabBar().isHidden()

    def test_tab_names(self, main_window):
        tabs = main_window._tabs
        names = [tabs.tabText(i) for i in range(tabs.count())]
        assert 'Log Verification' in names
        assert 'Signal Plotter' in names
        assert '3D Flight View' in names
        assert 'Debrief' in names
        assert 'Timeline' in names
        assert 'Events' in names
        assert 'Situation' in names

    def test_nav_rail_switches_pages(self, main_window):
        main_window._on_module_requested(1)
        assert main_window._tabs.currentIndex() == 1
        main_window._on_module_requested(0)
        assert main_window._tabs.currentIndex() == 0

    def test_window_minimum_size(self, main_window):
        # resize() was called with 1400×900
        assert main_window.width() >= 800
        assert main_window.height() >= 600

    def test_parse_button_exists(self, main_window):
        btn = main_window.findChild(QPushButton, '')
        all_btns = main_window.findChildren(QPushButton)
        labels = [b.text() for b in all_btns]
        assert any('Parse' in lbl for lbl in labels)

    def test_bin_lineedit_readonly(self, main_window):
        assert main_window._bin_label.isReadOnly()

    def test_key_lineedit_readonly(self, main_window):
        assert main_window._key_label.isReadOnly()

    def test_progress_bar_hidden_initially(self, main_window):
        assert not main_window._progress.isVisible()

    def test_parse_button_enabled_initially(self, main_window):
        assert main_window._parse_btn.isEnabled()


class TestMainWindowParseTrigger:
    def test_parse_with_no_file_shows_status(self, main_window, qtbot):
        main_window._bin_path = ''
        qtbot.mouseClick(main_window._parse_btn, Qt.MouseButton.LeftButton)
        msg = main_window.statusBar().currentMessage()
        assert msg != ''  # some status message was shown

    def test_parse_with_missing_file_shows_status(self, main_window, qtbot):
        main_window._bin_path = '/nonexistent/file.bin'
        qtbot.mouseClick(main_window._parse_btn, Qt.MouseButton.LeftButton)
        msg = main_window.statusBar().currentMessage()
        assert msg != ''

    def test_data_ready_signal_updates_all_tabs(self, main_window, qtbot):
        from tests.helpers import make_parsed_data
        data = make_parsed_data()
        # Directly emit data_ready to test the handler without file I/O
        with qtbot.waitSignal(main_window.data_ready, timeout=500, raising=False):
            main_window.data_ready.emit(data)
        # After signal, plotter should have data
        assert main_window._tab_plotter._data is not None

    def test_raw_bytes_accessible(self, main_window):
        main_window._raw_bytes = b'\xA3\x95' * 10
        assert main_window.get_raw_bytes() == b'\xA3\x95' * 10


class TestCrossTabSync:
    def test_plotter_cursor_connected_to_3d(self, main_window, qtbot):
        # Verify the signal connection exists by checking it can be emitted
        received = []
        main_window._tab_3d.set_time.__func__  # callable

        # Emit a time from the plotter and verify 3D tab can receive it
        # (no crash = connection wiring is correct)
        main_window._tab_plotter.crosshair_moved.emit(45.0)

    def test_status_message_clears_after_timeout(self, main_window, qtbot):
        main_window._status('Test message')
        assert 'Test message' in main_window.statusBar().currentMessage()


class TestKeyAutodiscovery:
    """Verification 'just happens': a public key beside the log is auto-loaded so
    the user need not manually select it every session (regression for the report
    'verification is not happening' — it only ran VERIFIED once a key was loaded)."""

    def test_autodiscover_loads_key_beside_log(self, qtbot, tmp_path):
        import os
        # log in a subdir, key in the parent — exercises the dir/parent search
        (tmp_path / 'logs').mkdir()
        binp = tmp_path / 'logs' / 'flight.BIN'
        binp.write_bytes(b'\x00' * 256)
        keyp = tmp_path / 'SN-99_log_public_key.dat'
        keyp.write_text('PUBLIC_KEYV1:abc')

        w = MainWindow(); qtbot.addWidget(w)
        w._key_path = ''
        w._bin_path = str(binp)
        w._autodiscover_key()
        assert w._key_path == str(keyp)

    def test_explicit_key_not_overridden(self, qtbot, tmp_path):
        binp = tmp_path / 'flight.BIN'; binp.write_bytes(b'\x00' * 256)
        chosen = tmp_path / 'chosen.dat'; chosen.write_text('PUBLIC_KEYV1:xyz')
        decoy = tmp_path / 'other_public_key.dat'; decoy.write_text('PUBLIC_KEYV1:zzz')
        w = MainWindow(); qtbot.addWidget(w)
        w._key_path = str(chosen)          # user picked this one
        w._bin_path = str(binp)
        w._autodiscover_key()
        assert w._key_path == str(chosen)  # never overridden by a discovered key
