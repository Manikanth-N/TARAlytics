"""
FlightIdentityBar — persistent 28px strip showing flight identity.

Sits below the application header. Always visible regardless of the active
module. Updates from AppState meta_changed / verification_changed signals.
"""
from __future__ import annotations
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QSizePolicy
from PyQt6.QtGui import QPainter, QColor, QPen, QFont
from PyQt6.QtCore import Qt

from ui.design.tokens import T
from ui.widgets.badge import StatusBadge
from ui.app_state import AppState, FlightMeta, VerifyResult
from core import verification_model as vmodel


class FlightIdentityBar(QWidget):
    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self._app_state = app_state
        self.setFixedHeight(T.layout.flight_bar_height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(T.spacing.px16, 0, T.spacing.px16, 0)
        layout.setSpacing(0)

        self._mono = QFont(T.font.data, T.size.sm)

        # Single composite label keeps separators simple and bug-free.
        self._text = QLabel('NO LOG LOADED')
        self._text.setFont(self._mono)
        self._text.setStyleSheet(f'color: {T.text.secondary};')

        self._badge = StatusBadge('UNKNOWN', vmodel.label('UNKNOWN'))

        layout.addWidget(self._text)
        layout.addStretch()
        layout.addWidget(self._badge)

        app_state.meta_changed.connect(self._on_meta)
        app_state.verification_changed.connect(self._on_verify)

    def _on_meta(self, meta: FlightMeta):
        parts = []
        sn = meta.serial_number if meta.serial_number not in ('', '—') else None
        if sn:
            parts.append(sn)
        if meta.frame_type not in ('', '—'):
            parts.append(meta.frame_type)
        if meta.firmware not in ('', '—'):
            parts.append(meta.firmware)
        if meta.log_counter:
            parts.append(f'#{meta.log_counter:03d}')
        if meta.duration_s:
            parts.append(f'{meta.duration_s:.1f} s')
        if meta.max_alt_m:
            parts.append(f'{meta.max_alt_m:.2f} m')
        self._text.setText('   ·   '.join(parts) if parts else 'LOG LOADED')

    def _on_verify(self, result: VerifyResult):
        self._badge.set_state(result.state, vmodel.label(result.state))

    def paintEvent(self, _):
        p = QPainter(self)
        r = self.rect()
        p.fillRect(r, QColor(T.surface.panel))
        p.setPen(QPen(QColor(T.border.subtle), 1))
        p.drawLine(r.left(), r.bottom(), r.right(), r.bottom())
        p.end()
