"""
SituationModule — the Situational Awareness surface (P1.5).

Hosts the Artificial Horizon (actual attitude + desired ghost) and the RC
Visualization (pilot sticks vs servo output) side by side. Both are cursor-synced,
so the moment you move the shared cursor anywhere, this module shows what the
aircraft and the pilot were doing at that instant — no plot required.
"""
from __future__ import annotations
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel

from ui.design.tokens import T
from ui.app_state import AppState
from ui.widgets.module_header import ModuleHeader
from ui.widgets.horizon import ArtificialHorizon
from ui.widgets.rc_viz import RCVisualization


def _panel(title: str, body: QWidget) -> QWidget:
    w = QWidget()
    w.setStyleSheet(f'background: {T.surface.card}; border-radius: 4px;')
    lay = QVBoxLayout(w)
    lay.setContentsMargins(T.spacing.px8, T.spacing.px8, T.spacing.px8, T.spacing.px8)
    lay.setSpacing(T.spacing.px4)
    cap = QLabel(title.upper())
    from PyQt6.QtGui import QFont
    f = QFont(T.font.brand, T.size.xs); f.setWeight(T.weight.bold)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.8)
    cap.setFont(f); cap.setStyleSheet(f'color: {T.text.muted};')
    lay.addWidget(cap)
    lay.addWidget(body, 1)
    return w


class SituationModule(QWidget):
    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self._app = app_state
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        root.addWidget(ModuleHeader('Situation'))

        body = QHBoxLayout()
        body.setContentsMargins(T.spacing.px16, T.spacing.px16,
                                T.spacing.px16, T.spacing.px16)
        body.setSpacing(T.spacing.px16)
        self._horizon = ArtificialHorizon(app_state)
        self._rc = RCVisualization(app_state)
        body.addWidget(_panel('Artificial Horizon', self._horizon), 1)
        body.addWidget(_panel('RC / Pilot Input', self._rc), 1)
        root.addLayout(body, 1)

    @property
    def horizon(self) -> ArtificialHorizon:
        return self._horizon

    @property
    def rc(self) -> RCVisualization:
        return self._rc
