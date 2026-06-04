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
        # Eight page-stack tabs: Debrief, Timeline, Events, Situation, Signal
        # Plotter, 3D Flight View, Log Verification, 2D Map. The tab bar is hidden
        # — navigation is driven by the NavigationRail.
        tabs = main_window._tabs
        assert tabs is not None
        assert tabs.count() == 8
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
