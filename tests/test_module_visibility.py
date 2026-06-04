"""Module visibility / configurable navigation tests."""
import json
import pytest
from PyQt6.QtCore import Qt, QSettings

from ui import nav_modules as NM


# ── Registry & helpers ────────────────────────────────────────────────────────

class TestRegistry:
    def test_page_indices_match_tab_order(self):
        expected = {'debrief': 0, 'timeline': 1, 'events': 2, 'situation': 3,
                    'signals': 4, 'replay': 5, 'verify': 6, 'map': 7,
                    'evidence': 8, 'workspace': 9}
        assert {m.id: m.page_index for m in NM.MODULES} == expected

    def test_presets_exact(self):
        assert NM.PRESETS['minimal'] == ['debrief', 'workspace', 'verify', 'replay', 'map']
        assert NM.PRESETS['flighttest'] == ['debrief', 'workspace', 'signals', 'replay',
                                            'verify', 'map', 'timeline', 'events']
        assert NM.PRESETS['full'] == NM.ALL_IDS

    def test_sanitize_drops_unknown_and_dupes_and_guards_empty(self):
        assert NM.sanitize(['debrief', 'bogus', 'debrief', 'map']) == ['debrief', 'map']
        assert NM.sanitize([]) == NM.PRESETS['minimal']      # never empty

    def test_detect_preset(self):
        assert NM.detect_preset(NM.PRESETS['minimal']) == 'minimal'
        assert NM.detect_preset(NM.PRESETS['full']) == 'full'
        assert NM.detect_preset(['debrief', 'map']) == 'custom'

    def test_order_to_navitems_and_hidden(self):
        items = NM.order_to_navitems(['debrief', 'map', 'verify'])
        assert items == [(0, 'DEBRIEF'), (7, 'MAP'), (6, 'VERIFY')]
        assert 'signals' in NM.hidden_ids(['debrief', 'map'])


# ── NavigationRail ─────────────────────────────────────────────────────────────

class TestNavigationRail:
    def test_set_modules_filters_and_routes(self, qtbot):
        from ui.widgets.navigation import NavigationRail
        rail = NavigationRail(); qtbot.addWidget(rail)
        rail.set_modules(NM.order_to_navitems(['debrief', 'map', 'verify']))
        assert rail.visible_pages() == [0, 7, 6]
        got = []
        rail.module_requested.connect(got.append)
        rail._items[1].clicked.emit(rail._items[1].page_index)   # the MAP item
        assert got == [7]                                        # emits page index, not position

    def test_set_active_highlights_by_page(self, qtbot):
        from ui.widgets.navigation import NavigationRail
        rail = NavigationRail(NM.order_to_navitems(['debrief', 'map', 'verify']))
        qtbot.addWidget(rail)
        rail.set_active(7)
        assert [it._active for it in rail._items] == [False, True, False]


# ── MainWindow integration ─────────────────────────────────────────────────────

@pytest.fixture
def clean_settings():
    s = QSettings('TARAlyticsAnalyzer', 'MainWindow'); s.clear(); s.sync()
    yield s
    s.clear(); s.sync()


class TestMainWindowVisibility:
    def test_fresh_install_defaults_minimal(self, qtbot, clean_settings):
        from ui.main_window import MainWindow
        w = MainWindow(); qtbot.addWidget(w)
        assert w._visible_modules == NM.PRESETS['minimal']
        assert w._nav_rail.visible_pages() == [0, 9, 6, 5, 7]

    def test_existing_install_defaults_full(self, qtbot, clean_settings):
        clean_settings.setValue('bin_path', '/some/old.bin')   # marks a prior install
        from ui.main_window import MainWindow
        w = MainWindow(); qtbot.addWidget(w)
        assert w._visible_modules == NM.PRESETS['full']

    def test_apply_persists_and_rebuilds(self, qtbot, clean_settings):
        from ui.main_window import MainWindow
        w = MainWindow(); qtbot.addWidget(w)
        w._apply_visible_modules(['debrief', 'map', 'verify'])
        assert w._nav_rail.visible_pages() == [0, 7, 6]
        saved = json.loads(QSettings('TARAlyticsAnalyzer', 'MainWindow').value('nav/visible_modules'))
        assert saved == ['debrief', 'map', 'verify']

    def test_navigate_to_hidden_module_still_routes(self, qtbot, clean_settings):
        from ui.main_window import MainWindow
        w = MainWindow(); qtbot.addWidget(w)
        w._apply_visible_modules(['debrief', 'map'])     # events (page 2) hidden
        w._on_module_requested(2)                        # e.g. a Debrief quick-jump
        assert w._tabs.currentIndex() == 2               # page exists & is shown

    def test_hiding_active_module_falls_back(self, qtbot, clean_settings):
        from ui.main_window import MainWindow
        w = MainWindow(); qtbot.addWidget(w)
        w._on_module_requested(7)                        # go to Map
        w._apply_visible_modules(['debrief', 'verify'])  # Map now hidden
        assert w._tabs.currentIndex() == 0               # fell back to first visible


# ── Manager dialog ─────────────────────────────────────────────────────────────

class TestVisibilityDialog:
    def test_selected_ids_in_order(self, qtbot):
        from ui.widgets.module_visibility import ModuleVisibilityDialog
        dlg = ModuleVisibilityDialog(['debrief', 'map', 'verify']); qtbot.addWidget(dlg)
        assert dlg.selected_ids() == ['debrief', 'map', 'verify']

    def test_preset_selection_sets_modules(self, qtbot):
        from ui.widgets.module_visibility import ModuleVisibilityDialog
        dlg = ModuleVisibilityDialog(['debrief']); qtbot.addWidget(dlg)
        dlg._preset.setCurrentIndex(dlg._preset.findData('flighttest'))
        dlg._on_preset_chosen(0)
        assert dlg.selected_ids() == NM.PRESETS['flighttest']

    def test_guard_blocks_unchecking_last(self, qtbot, monkeypatch):
        from PyQt6.QtWidgets import QMessageBox
        from ui.widgets.module_visibility import ModuleVisibilityDialog
        monkeypatch.setattr(QMessageBox, 'information', lambda *a, **k: None)
        dlg = ModuleVisibilityDialog(['debrief']); qtbot.addWidget(dlg)
        dlg._list.item(0).setCheckState(Qt.CheckState.Unchecked)
        assert dlg.selected_ids() == ['debrief']         # reverted — never empty

    def test_saved_layout_roundtrip(self, qtbot, monkeypatch):
        from PyQt6.QtWidgets import QInputDialog
        from ui.widgets.module_visibility import ModuleVisibilityDialog
        monkeypatch.setattr(QInputDialog, 'getText', lambda *a, **k: ('Triage', True))
        dlg = ModuleVisibilityDialog(['debrief', 'replay', 'map']); qtbot.addWidget(dlg)
        dlg._save_as()
        assert dlg.saved_layouts()['Triage'] == ['debrief', 'replay', 'map']
        dlg._saved_combo.setCurrentIndex(dlg._saved_combo.findData('Triage'))
        dlg._delete_saved()
        assert 'Triage' not in dlg.saved_layouts()
