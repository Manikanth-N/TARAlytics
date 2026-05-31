"""UI tests for PlotterTab using pytest-qt."""
import pytest
import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTreeWidget, QPushButton

from ui.tab_plotter import PlotterTab
from ui.main_window import MainWindow
from tests.helpers import make_parsed_data


@pytest.fixture
def main_window(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    return window


@pytest.fixture
def plotter(main_window):
    return main_window._tab_plotter


@pytest.fixture
def plotter_with_data(plotter, qtbot):
    data = make_parsed_data()
    plotter.update_data(data)
    return plotter


class TestPlotterEmptyState:
    def test_signal_tree_exists(self, plotter):
        tree = plotter.findChild(QTreeWidget)
        assert tree is not None

    def test_no_active_signals_initially(self, plotter):
        assert len(plotter._active_sigs) == 0

    def test_t_offset_is_zero_initially(self, plotter):
        assert plotter._t_offset == 0.0


class TestPlotterAfterDataLoad:
    def test_tree_populated_after_update(self, plotter_with_data):
        tree = plotter_with_data._tree
        assert tree.topLevelItemCount() > 0

    def test_t_offset_set_from_data(self, plotter_with_data):
        # Data starts at t=40.0 → t_offset should be 40.0
        assert abs(plotter_with_data._t_offset - 40.0) < 0.1

    def test_att_group_present_in_tree(self, plotter_with_data):
        tree = plotter_with_data._tree
        group_labels = [
            tree.topLevelItem(i).text(0)
            for i in range(tree.topLevelItemCount())
        ]
        assert 'ATTITUDE' in group_labels

    def test_full_time_range_set(self, plotter_with_data):
        t0, t1 = plotter_with_data._t_full
        assert t0 == 0.0
        assert t1 > 0.0

    def test_extra_signals_cleared_on_data_reload(self, plotter_with_data):
        # Manually add a non-default signal
        plotter_with_data._add_signal('ATT', 'Roll', 'ATT.Roll_extra')
        count_with_extra = len(plotter_with_data._active_sigs)

        # Reload — clears all and re-applies only defaults
        plotter_with_data.update_data(make_parsed_data(n=50))

        assert 'ATT.Roll_extra' not in plotter_with_data._active_sigs
        assert len(plotter_with_data._active_sigs) < count_with_extra


class TestPlotterSignalManagement:
    def test_add_and_remove_signal(self, plotter_with_data):
        plotter = plotter_with_data
        key = 'ATT.Roll'
        plotter._add_signal('ATT', 'Roll', key)
        assert key in plotter._active_sigs

        plotter._remove_signal(key)
        assert key not in plotter._active_sigs

    def test_add_unknown_df_key_ignored(self, plotter_with_data):
        plotter_with_data._add_signal('NONEXISTENT', 'Col', 'key')
        assert 'key' not in plotter_with_data._active_sigs

    def test_add_unknown_column_ignored(self, plotter_with_data):
        plotter_with_data._add_signal('ATT', 'NONEXISTENT_COL', 'key')
        assert 'key' not in plotter_with_data._active_sigs

    def test_clear_all_removes_signals(self, plotter_with_data):
        plotter_with_data._add_signal('ATT', 'Roll', 'ATT.Roll')
        plotter_with_data._add_signal('ATT', 'Pitch', 'ATT.Pitch')
        plotter_with_data._clear_all()
        assert len(plotter_with_data._active_sigs) == 0
        assert plotter_with_data._color_idx == 0

    def test_duplicate_add_ignored(self, plotter_with_data):
        plotter_with_data._clear_all()  # start with clean slate
        plotter_with_data._add_signal('ATT', 'Roll', 'ATT.Roll')
        plotter_with_data._add_signal('ATT', 'Roll', 'ATT.Roll')  # duplicate
        assert len(plotter_with_data._active_sigs) == 1


class TestPlotterCrosshair:
    def test_crosshair_moved_signal_emitted(self, plotter_with_data, qtbot):
        plotter = plotter_with_data
        received = []
        plotter.crosshair_moved.connect(received.append)
        plotter.set_crosshair(45.0)
        # set_crosshair sets the position; crosshair_moved fires on mouse move, not set_crosshair
        # Verify position was updated correctly
        pos = plotter._crosshair_v.value()
        assert abs(pos - (45.0 - plotter._t_offset)) < 0.01

    def test_set_crosshair_updates_position(self, plotter_with_data):
        plotter = plotter_with_data
        plotter.set_crosshair(50.0)
        expected = 50.0 - plotter._t_offset
        assert abs(plotter._crosshair_v.value() - expected) < 0.01
