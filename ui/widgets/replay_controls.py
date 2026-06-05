from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QSlider,
    QLabel, QCheckBox, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QFontMetrics


SPEEDS = [0.5, 1.0, 2.0, 5.0, 10.0]


class ReplayControls(QWidget):
    time_changed = pyqtSignal(float)
    follow_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._t_min = 0.0
        self._t_max = 1.0
        self._current = 0.0
        self._playing = False
        self._speed = 1.0

        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)

        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        # ── Transport group: Reset · Play (primary) ───────────────────────────
        self._reset_btn = QPushButton('⏮ Reset')
        self._reset_btn.setFixedSize(72, 26)
        self._reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reset_btn.setStyleSheet(
            'QPushButton { background: #495057; color: white; border-radius: 4px; padding: 3px 6px; }'
            'QPushButton:hover { background: #5a6268; }'
        )
        self._reset_btn.clicked.connect(self._reset)
        layout.addWidget(self._reset_btn)

        self._play_btn = QPushButton('▶ Play')              # primary action
        self._play_btn.setFixedSize(88, 26)
        self._play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._play_btn.setStyleSheet(
            'QPushButton { background: #198754; color: white; border-radius: 4px; '
            'padding: 3px 6px; font-weight: bold; }'
            'QPushButton:hover { background: #1aa15f; }'
        )
        self._play_btn.clicked.connect(self._toggle_play)
        layout.addWidget(self._play_btn)

        layout.addSpacing(12)

        # ── Scrubber + fixed-width clock ──────────────────────────────────────
        self._scrubber = QSlider(Qt.Orientation.Horizontal)
        self._scrubber.setRange(0, 10000)
        self._scrubber.setValue(0)
        self._scrubber.sliderMoved.connect(self._on_scrub)
        layout.addWidget(self._scrubber, 1)

        clock_font = QFont('JetBrains Mono', 11)
        clock_font.setStyleHint(QFont.StyleHint.Monospace)
        self._time_lbl = QLabel('00:00 / 00:00')
        self._time_lbl.setFont(clock_font)
        self._time_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._time_lbl.setStyleSheet('color: #e0e0e0;')
        self._use_hours = False
        self._size_clock()
        layout.addWidget(self._time_lbl)

        layout.addSpacing(12)
        layout.addWidget(self._vsep())

        # ── Speed group ───────────────────────────────────────────────────────
        self._speed_lbl = QLabel('Speed')
        self._speed_lbl.setStyleSheet('color: #9aa0a6;')
        layout.addWidget(self._speed_lbl)
        self._speed_btns = []
        for spd in SPEEDS:
            btn = QPushButton(f'{spd:g}x')
            btn.setFixedSize(40, 24)
            btn.setCheckable(True)
            btn.setChecked(spd == 1.0)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                'QPushButton { background: #343a40; color: white; border-radius: 3px; padding: 2px; }'
                'QPushButton:hover { background: #3f464d; }'
                'QPushButton:checked { background: #0d6efd; }'
            )
            btn.clicked.connect(lambda checked, s=spd: self._set_speed(s))
            layout.addWidget(btn)
            self._speed_btns.append((spd, btn))

        layout.addSpacing(12)
        layout.addWidget(self._vsep())

        self._follow_cb = QCheckBox('Follow')
        self._follow_cb.setChecked(True)
        self._follow_cb.setStyleSheet('color: #e0e0e0;')
        self._follow_cb.stateChanged.connect(
            lambda s: self.follow_changed.emit(bool(s))
        )
        layout.addWidget(self._follow_cb)

    @staticmethod
    def _vsep() -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.Shape.VLine)
        f.setStyleSheet('color: #3a3a4a;')
        f.setFixedHeight(20)
        return f

    def _fmt_clock(self, seconds: float) -> str:
        s = int(round(max(0.0, seconds)))
        if self._use_hours:
            return f'{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}'
        return f'{s // 60:02d}:{s % 60:02d}'

    def _size_clock(self):
        longest = '00:00:00 / 00:00:00' if self._use_hours else '00:00 / 00:00'
        w = QFontMetrics(self._time_lbl.font()).horizontalAdvance(longest) + 10
        self._time_lbl.setFixedWidth(w)

    def set_range(self, t_min: float, t_max: float):
        self._t_min = t_min
        self._t_max = t_max if t_max > t_min else t_min + 1.0
        self._current = t_min
        self._scrubber.setValue(0)
        self._use_hours = (self._t_max - self._t_min) >= 3600
        self._size_clock()
        self._update_time_label()

    def _t_to_slider(self, t: float) -> int:
        r = self._t_max - self._t_min
        if r == 0:
            return 0
        return int((t - self._t_min) / r * 10000)

    def _slider_to_t(self, v: int) -> float:
        return self._t_min + v / 10000.0 * (self._t_max - self._t_min)

    def _tick(self):
        dt = 0.033 * self._speed
        self._current += dt
        if self._current >= self._t_max:
            self._current = self._t_max
            self._playing = False
            self._timer.stop()
            self._play_btn.setText('▶ Play')
        self._scrubber.blockSignals(True)
        self._scrubber.setValue(self._t_to_slider(self._current))
        self._scrubber.blockSignals(False)
        self._update_time_label()
        self.time_changed.emit(self._current)

    def _toggle_play(self):
        if self._playing:
            self._playing = False
            self._timer.stop()
            self._play_btn.setText('▶ Play')
        else:
            if self._current >= self._t_max:
                self._current = self._t_min
            self._playing = True
            self._timer.start()
            self._play_btn.setText('⏸ Pause')

    def _reset(self):
        self._playing = False
        self._timer.stop()
        self._play_btn.setText('▶ Play')
        self._current = self._t_min
        self._scrubber.setValue(0)
        self._update_time_label()
        self.time_changed.emit(self._current)

    def _on_scrub(self, value: int):
        self._current = self._slider_to_t(value)
        self._update_time_label()
        self.time_changed.emit(self._current)

    def _set_speed(self, spd: float):
        self._speed = spd
        for s, btn in self._speed_btns:
            btn.setChecked(s == spd)

    def _update_time_label(self):
        elapsed = self._current - self._t_min
        total = self._t_max - self._t_min
        self._time_lbl.setText(f'{self._fmt_clock(elapsed)} / {self._fmt_clock(total)}')

    def set_time(self, t: float):
        t = max(self._t_min, min(self._t_max, t))
        self._current = t
        self._scrubber.blockSignals(True)
        self._scrubber.setValue(self._t_to_slider(t))
        self._scrubber.blockSignals(False)
        self._update_time_label()

    def toggle_play(self):
        """Public slot for keyboard shortcut."""
        self._toggle_play()

    def step(self, dt: float):
        """Step forward (dt>0) or backward (dt<0) by dt seconds."""
        new_t = max(self._t_min, min(self._t_max, self._current + dt))
        self._current = new_t
        self._scrubber.blockSignals(True)
        self._scrubber.setValue(self._t_to_slider(new_t))
        self._scrubber.blockSignals(False)
        self._update_time_label()
        self.time_changed.emit(new_t)
