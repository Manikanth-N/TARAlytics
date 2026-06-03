"""
Theme system for TARAlytics.

Generates the application QSS stylesheet from design tokens and loads the
bundled Rajdhani / JetBrains Mono fonts. Call `apply_theme(app)` once at
startup, after the QApplication is created and before any window is shown.
"""
from __future__ import annotations
import os
import logging

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFontDatabase, QFont

from ui.design.tokens import T

_log = logging.getLogger(__name__)

FONTS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'assets', 'fonts')


def build_qss() -> str:
    """Return the complete application stylesheet built from design tokens."""
    return f"""
* {{ font-family: "{T.font.brand}"; font-size: {T.size.md}px;
     color: {T.text.primary}; outline: none; }}

QMainWindow, QWidget {{ background-color: {T.surface.base}; border: none; }}

QScrollBar:vertical {{
    background: {T.surface.panel}; width: 6px; border-radius: 3px; border: none; }}
QScrollBar::handle:vertical {{
    background: {T.border.active}; border-radius: 3px; min-height: 32px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}

QScrollBar:horizontal {{
    background: {T.surface.panel}; height: 6px; border-radius: 3px; border: none; }}
QScrollBar::handle:horizontal {{
    background: {T.border.active}; border-radius: 3px; min-width: 32px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}

QLabel {{ background: transparent; color: {T.text.primary}; }}

QPushButton {{
    background-color: {T.surface.elevated}; color: {T.text.primary};
    border: 1px solid {T.border.default}; border-radius: 3px;
    padding: 4px 12px; font-weight: {T.weight.semibold}; font-size: {T.size.sm}px; }}
QPushButton:hover {{ border-color: {T.border.active}; }}
QPushButton:pressed {{ background-color: {T.surface.card}; }}
QPushButton:disabled {{ color: {T.text.muted}; border-color: {T.border.subtle}; }}
QPushButton[role="primary"] {{
    background-color: {T.brand.blue}; color: {T.brand.white}; border: none; }}
QPushButton[role="primary"]:hover {{ background-color: {T.brand.blue_bright}; }}
QPushButton[role="primary"]:pressed {{ background-color: {T.brand.blue_deep}; }}

QLineEdit {{
    background-color: {T.surface.card}; color: {T.text.primary};
    border: 1px solid {T.border.default}; border-radius: 3px;
    padding: 4px 8px; font-family: "{T.font.data}";
    selection-background-color: {T.brand.blue}; }}
QLineEdit:focus {{ border-color: {T.brand.blue}; }}
QLineEdit[readOnly="true"] {{
    background-color: {T.surface.panel}; color: {T.text.secondary}; }}

QComboBox {{
    background-color: {T.surface.card}; color: {T.text.primary};
    border: 1px solid {T.border.default}; border-radius: 3px; padding: 4px 8px; }}
QComboBox:focus {{ border-color: {T.brand.blue}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background-color: {T.surface.elevated}; border: 1px solid {T.border.active};
    selection-background-color: rgba(26,159,213,0.15); }}

QDoubleSpinBox, QSpinBox {{
    background-color: {T.surface.card}; color: {T.text.primary};
    border: 1px solid {T.border.default}; border-radius: 3px; padding: 2px 6px;
    font-family: "{T.font.data}"; }}
QDoubleSpinBox:focus, QSpinBox:focus {{ border-color: {T.brand.blue}; }}

QToolTip {{
    background-color: {T.surface.elevated}; color: {T.text.primary};
    border: 1px solid {T.border.default}; padding: 4px 8px;
    font-size: {T.size.sm}px; }}

QStatusBar {{ background-color: {T.surface.panel}; color: {T.text.muted};
              font-size: {T.size.sm}px; border-top: 1px solid {T.border.subtle}; }}
QStatusBar::item {{ border: none; }}

QSplitter::handle {{ background-color: {T.border.subtle}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}

QTabWidget::pane {{ border: none; background: {T.surface.base}; }}

QTableWidget {{
    background-color: {T.surface.card}; color: {T.text.primary};
    gridline-color: {T.border.subtle}; border: 1px solid {T.border.subtle};
    selection-background-color: rgba(26,159,213,0.12); font-size: {T.size.sm}px; }}
QTableWidget::item {{ padding: 5px 10px; border: none; }}
QTableWidget::item:hover {{ background-color: rgba(26,159,213,0.08); }}
QHeaderView::section {{
    background-color: {T.surface.elevated}; color: {T.text.secondary};
    font-weight: {T.weight.bold}; font-size: {T.size.sm}px;
    padding: 5px 10px; border: none;
    border-bottom: 1px solid {T.border.default}; }}

QCheckBox {{ color: {T.text.secondary}; font-size: {T.size.sm}px; spacing: 6px; }}
QCheckBox::indicator {{
    width: 14px; height: 14px; border: 1px solid {T.border.default};
    border-radius: 2px; background: {T.surface.card}; }}
QCheckBox::indicator:checked {{
    background: {T.brand.blue}; border-color: {T.brand.blue}; }}

QSlider::groove:horizontal {{
    background: {T.border.default}; height: 4px; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {T.brand.blue}; width: 14px; height: 14px;
    margin: -5px 0; border-radius: 7px; }}
QSlider::sub-page:horizontal {{ background: {T.brand.blue}; border-radius: 2px; }}

QTreeWidget {{
    background-color: {T.surface.panel}; color: {T.text.primary};
    border: none; }}
QTreeWidget::item:hover {{ background-color: rgba(26,159,213,0.08); }}
QTreeWidget::item:selected {{ background-color: rgba(26,159,213,0.15); }}

QProgressBar {{
    background-color: {T.border.default}; border-radius: 3px; border: none;
    text-align: center; }}
QProgressBar::chunk {{ background-color: {T.brand.blue}; border-radius: 3px; }}
    """


def load_fonts() -> list[str]:
    """Load bundled .ttf/.otf fonts. Returns list of loaded family names."""
    loaded: list[str] = []
    if not os.path.isdir(FONTS_DIR):
        _log.warning('Fonts directory not found: %s', FONTS_DIR)
        return loaded
    for fname in sorted(os.listdir(FONTS_DIR)):
        if not fname.lower().endswith(('.ttf', '.otf')):
            continue
        fid = QFontDatabase.addApplicationFont(os.path.join(FONTS_DIR, fname))
        if fid >= 0:
            loaded.extend(QFontDatabase.applicationFontFamilies(fid))
        else:
            _log.warning('Font failed to load: %s', fname)
    return loaded


def apply_theme(app: QApplication) -> None:
    """Load fonts and apply the QSS theme to the application."""
    families = load_fonts()
    brand_family = T.font.brand if T.font.brand in families else 'Sans Serif'
    if brand_family != T.font.brand:
        _log.warning('Brand font "%s" not available; using "%s"',
                     T.font.brand, brand_family)
    app.setFont(QFont(brand_family, T.size.md))
    app.setStyleSheet(build_qss())
