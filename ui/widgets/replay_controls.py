from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QSlider,
    QLabel, QCheckBox,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer


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
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)

        self._reset_btn = QPushButton('⏮ Reset')
        self._reset_btn.setFixedWidth(72)
        self._reset_btn.setStyleSheet(
            'QPushButton { background: #495057; color: white; border-radius: 3px; padding: 3px 6px; }'
        )
        self._reset_btn.clicked.connect(self._reset)
        layout.addWidget(self._reset_btn)

        self._play_btn = QPushButton('▶ Play')
        self._play_btn.setFixedWidth(72)
        self._play_btn.setStyleSheet(
            'QPushButton { background: #198754; color: white; border-radius: 3px; padding: 3px 6px; }'
        )
        self._play_btn.clicked.connect(self._toggle_play)
        layout.addWidget(self._play_btn)

        self._scrubber = QSlider(Qt.Orientation.Horizontal)
        self._scrubber.setRange(0, 10000)
        self._scrubber.setValue(0)
        self._scrubber.sliderMoved.connect(self._on_scrub)
        layout.addWidget(self._scrubber, 1)

        self._time_lbl = QLabel('0.00 s')
        self._time_lbl.setFixedWidth(70)
        self._time_lbl.setStyleSheet('color: #e0e0e0; font-size: 11px;')
        layout.addWidget(self._time_lbl)

        layout.addWidget(QLabel('Speed:'))
        self._speed_btns = []
        for spd in SPEEDS:
            label = f'{spd:g}x'
            btn = QPushButton(label)
            btn.setFixedWidth(42)
            btn.setCheckable(True)
            btn.setChecked(spd == 1.0)
            btn.setStyleSheet(
                'QPushButton { background: #343a40; color: white; border-radius: 3px; padding: 2px; }'
                'QPushButton:checked { background: #0d6efd; }'
            )
            btn.clicked.connect(lambda checked, s=spd: self._set_speed(s))
            layout.addWidget(btn)
            self._speed_btns.append((spd, btn))

        self._follow_cb = QCheckBox('Follow')
        self._follow_cb.setChecked(True)
        self._follow_cb.setStyleSheet('color: #e0e0e0;')
        self._follow_cb.stateChanged.connect(
            lambda s: self.follow_changed.emit(bool(s))
        )
        layout.addWidget(self._follow_cb)

    def set_range(self, t_min: float, t_max: float):
        self._t_min = t_min
        self._t_max = t_max if t_max > t_min else t_min + 1.0
        self._current = t_min
        self._scrubber.setValue(0)
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
        self._time_lbl.setText(f'{self._current:.2f} s')

    def set_time(self, t: float):
        t = max(self._t_min, min(self._t_max, t))
        self._current = t
        self._scrubber.blockSignals(True)
        self._scrubber.setValue(self._t_to_slider(t))
        self._scrubber.blockSignals(False)
        self._update_time_label()
