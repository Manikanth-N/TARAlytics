"""
TimelineModule — the primary navigation surface (Module ②, Step 4.2).

A thin shell around TimelineCanvas: a ModuleHeader with fit / flight-step /
event-step controls, and the canvas itself driving the shared cursor. All flight
structure comes from AppState.timeline_model; all navigation flows through
AppState.set_cursor_time, so every other surface stays in sync.
"""
from __future__ import annotations
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton
from PyQt6.QtCore import Qt

from ui.design.tokens import T
from ui.app_state import AppState
from ui.widgets.module_header import ModuleHeader
from ui.widgets.timeline_canvas import TimelineCanvas


def _tool_button(text: str, tip: str) -> QPushButton:
    b = QPushButton(text)
    b.setToolTip(tip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFixedHeight(24)
    b.setStyleSheet(
        f'QPushButton {{ background: {T.surface.card}; color: {T.text.secondary}; '
        f'border: 1px solid {T.border.default}; border-radius: 3px; '
        f'padding: 2px 9px; font-family: {T.font.brand}; font-size: {T.size.sm}px; '
        f'font-weight: {T.weight.semibold}; }} '
        f'QPushButton:hover {{ color: {T.brand.blue_bright}; '
        f'border-color: {T.border.active}; }}'
    )
    return b


class TimelineModule(QWidget):
    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self._app = app_state
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = ModuleHeader('Timeline')
        self._b_prev_flight = _tool_button('◀ Flight', 'Previous flight window')
        self._b_next_flight = _tool_button('Flight ▶', 'Next flight window')
        self._b_prev_ev = _tool_button('◀ Event', 'Previous event')
        self._b_next_ev = _tool_button('Event ▶', 'Next event')
        self._b_fit = _tool_button('⤢ Fit', 'Reset zoom to whole log')
        for b in (self._b_prev_flight, self._b_next_flight,
                  self._b_prev_ev, self._b_next_ev, self._b_fit):
            header.add_action(b)
        root.addWidget(header)

        self._canvas = TimelineCanvas(self._app)
        root.addWidget(self._canvas, 1)

        self._b_fit.clicked.connect(self._canvas.fit)
        self._b_prev_flight.clicked.connect(lambda: self._canvas.step_flight(-1))
        self._b_next_flight.clicked.connect(lambda: self._canvas.step_flight(+1))
        self._b_prev_ev.clicked.connect(lambda: self._canvas.step_event(-1))
        self._b_next_ev.clicked.connect(lambda: self._canvas.step_event(+1))

    @property
    def canvas(self) -> TimelineCanvas:
        return self._canvas
