import re
import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QTreeWidget, QTreeWidgetItem, QPushButton,
    QLabel, QColorDialog, QFileDialog, QApplication, QMenu,
)
from PyQt6.QtCore import Qt, pyqtSignal, QRectF, QPointF
from PyQt6.QtGui import QColor, QBrush, QAction, QFont

from core.colors import signal_color, SEVERITY_COLORS
from ui.widgets.stats_legend import StatsLegend
from ui.widgets.time_limit_controls import TimeLimitControls
from ui.widgets.event_overlay_panel import EventOverlayPanel, EVENT_COLORS, _event_category

pg.setConfigOption('background', '#1e1e2e')
pg.setConfigOption('foreground', '#e0e0e0')

MSG_GROUPS = {
    'ATTITUDE':   ['ATT', 'ANG', 'RATE', 'PIDR', 'PIDP', 'PIDY', 'PIDA'],
    'EKF':        ['XKF1', 'XKF2', 'XKF3', 'XKF4', 'XKF5', 'XKFS', 'XKQ', 'XKT', 'XKY0', 'XKY1'],
    'GPS/NAV':    ['GPS', 'GPA', 'AHR2', 'CTUN', 'PSCN', 'PSCE', 'PSCD'],
    'IMU':        ['IMU', 'ACC', 'GYR', 'VIBE'],
    'MOTORS':     ['ESCX', 'ESC', 'SURF', 'MOTB', 'RCIN', 'RCOU'],
    'POWER':      ['BAT', 'BCL', 'POWR', 'MCU'],
    'BARO':       ['BARO', 'ARSP'],
    'MAG':        ['MAG'],
    'SIMULATION': ['SIM', 'SIM2'],
}

DEFAULT_SIGNALS = [
    ('SIM2',    'VN'),     ('SIM2',    'VE'),     ('SIM2',    'VD'),
    ('ATT',     'Roll'),   ('ATT',     'Pitch'),   ('ATT',     'Yaw'),
    ('IMU[0]',  'AccZ'),   ('IMU[1]',  'AccZ'),
    ('ESCX[0]', 'outpct'), ('ESCX[1]', 'outpct'),
    ('ESCX[2]', 'outpct'), ('ESCX[3]', 'outpct'),
]

_INST_RE = re.compile(r'^(.+)\[(\d+)\]$')
_USER_ROLE_COL = Qt.ItemDataRole.UserRole + 1  # stores field/column name

# Unit heuristics for Y-axis label
_UNIT_MAP = [
    (('alt', 'Alt'),                          'm'),
    (('RPM', 'Rpm'),                          'RPM'),
    (('Roll', 'Pitch', 'Yaw', 'roll', 'pitch', 'yaw'), 'deg'),
    (('Volt', 'volt'),                        'V'),
    (('Curr', 'curr'),                        'A'),
    (('VN', 'VE', 'VD', 'spd', 'Spd'),       'm/s'),
    (('pct', 'Pct'),                          '%'),
]

EVENT_PEN = {
    'CRITICAL':    pg.mkPen(color='#dc3545', width=2, style=Qt.PenStyle.DashLine),
    'ERROR':       pg.mkPen(color='#fd7e14', width=1, style=Qt.PenStyle.DashLine),
    'WARNING':     pg.mkPen(color='#ffc107', width=1, style=Qt.PenStyle.DashLine),
    'INFO':        pg.mkPen(color='#4a90d9', width=1, style=Qt.PenStyle.DotLine),
    'MODE_CHANGE': pg.mkPen(color='#9932cc', width=1, style=Qt.PenStyle.DotLine),
    'ARM':         pg.mkPen(color='#28a745', width=1, style=Qt.PenStyle.DotLine),
    'DISARM':      pg.mkPen(color='#6c757d', width=1, style=Qt.PenStyle.DotLine),
}


def _make_short_label(etype: str, msg: str) -> str:
    if etype == 'MODE':
        mode = msg.replace('Mode: ', '').replace('Mode CHANGE: ', '')
        return f'◈ {mode[:8]}'
    if etype == 'ARM':
        return '⬆ ARMED' if 'arm' in msg.lower() and 'disarm' not in msg.lower() else '⬇ DISARM'
    if etype == 'EV':
        return msg.replace('EV: id=', 'EV:').replace('id=', 'EV:')[:12]
    if etype == 'ERR':
        return f'✖ {msg[:12]}'
    text = msg
    for prefix in ('ArduCopter', 'EKF3', 'GPS', 'RC Protocol', 'Frame', 'Param'):
        if text.startswith(prefix):
            return text[:14]
    return text[:14]


def _guess_unit(field: str) -> str:
    for keys, unit in _UNIT_MAP:
        if any(k in field for k in keys):
            return unit
    return ''


# ── Custom ViewBox ────────────────────────────────────────────────────────────

class CustomViewBox(pg.ViewBox):
    context_menu_requested = pyqtSignal(object)  # QPoint

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setMouseMode(pg.ViewBox.PanMode)
        self._rb_active = False

    def mouseDragEvent(self, ev, axis=None):
        if ev.button() == Qt.MouseButton.RightButton:
            ev.accept()
            self._rb_active = True
            if ev.isFinish():
                self.rbScaleBox.hide()
                self._rb_active = False
                r = QRectF(
                    pg.Point(ev.buttonDownPos(ev.button())),
                    pg.Point(ev.pos())
                )
                r = self.childGroup.mapRectFromScene(r)
                if r.width() > 0.001 and abs(r.height()) > 0.001:
                    self.showAxRect(r)
            else:
                self.updateScaleBox(ev.buttonDownPos(ev.button()), ev.pos())
        else:
            super().mouseDragEvent(ev, axis)

    def mouseClickEvent(self, ev):
        if ev.button() == Qt.MouseButton.RightButton and not self._rb_active:
            ev.accept()
            self.context_menu_requested.emit(ev.screenPos().toPoint())
        else:
            super().mouseClickEvent(ev)

    def mouseDoubleClickEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            ev.accept()
            self.autoRange()
        else:
            super().mouseDoubleClickEvent(ev)

    def wheelEvent(self, ev, axis=None):
        mods = ev.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier:
            super().wheelEvent(ev, axis=1)
        elif mods & Qt.KeyboardModifier.ShiftModifier:
            super().wheelEvent(ev, axis=None)
        else:
            super().wheelEvent(ev, axis=0)

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_Escape and self.rbScaleBox.isVisible():
            self.rbScaleBox.hide()
            self._rb_active = False
            ev.accept()
        else:
            super().keyPressEvent(ev)


# ── PlotterTab ────────────────────────────────────────────────────────────────

class PlotterTab(QWidget):
    crosshair_moved = pyqtSignal(float)   # absolute time

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self._mw          = main_window
        self._data        = {}
        self._active_sigs: dict[str, dict] = {}
        self._color_idx   = 0
        self._t_offset    = 0.0
        self._t_full      = (0.0, 1.0)   # (rel_start, rel_end) of full log
        self._syncing     = False
        self._event_items: list[dict] = []  # {ts, cat, line, visible}
        self._cat_visible: dict[str, bool] = {c: True for c in EVENT_COLORS}
        self._tooltip_text = ''
        self._setup_ui()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Signal tree
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setFixedWidth(210)
        self._tree.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self._tree.setStyleSheet(
            'QTreeWidget { background: #13131f; color: #e0e0e0; border: none; }'
            'QTreeWidget::item:hover { background: #2a2a3e; }'
            'QTreeWidget::item:selected { background: #3a3a5e; }'
        )

        # Right panel
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(2)

        # Toolbar
        toolbar_w = QWidget()
        toolbar_w.setStyleSheet('background: #13131f;')
        tb = QHBoxLayout(toolbar_w)
        tb.setContentsMargins(4, 3, 4, 3)
        tb.setSpacing(4)

        def _tb_btn(label, color='#495057'):
            b = QPushButton(label)
            b.setStyleSheet(
                f'QPushButton {{ background: {color}; color: white; border-radius: 3px; '
                f'padding: 3px 8px; font-size: 11px; }}'
                f'QPushButton:hover {{ opacity: 0.85; }}'
            )
            return b

        btn_autofit  = _tb_btn('Auto Fit')
        btn_zoomin   = _tb_btn('Zoom In +')
        btn_zoomout  = _tb_btn('Zoom Out −')
        btn_reset    = _tb_btn('Reset View')
        btn_clear    = _tb_btn('Clear All')
        btn_csv      = _tb_btn('Export CSV', '#0d6efd')
        btn_png      = _tb_btn('Export PNG', '#198754')

        btn_autofit.clicked.connect(self._auto_fit)
        btn_zoomin.clicked.connect(self._zoom_in)
        btn_zoomout.clicked.connect(self._zoom_out)
        btn_reset.clicked.connect(self._reset_view)
        btn_clear.clicked.connect(self._clear_all)
        btn_csv.clicked.connect(self._export_csv)
        btn_png.clicked.connect(self._export_png)

        for b in (btn_autofit, btn_zoomin, btn_zoomout, btn_reset):
            tb.addWidget(b)
        tb.addWidget(_sep())
        for b in (btn_clear, btn_csv, btn_png):
            tb.addWidget(b)
        tb.addStretch()
        rv.addWidget(toolbar_w)

        # Main plot
        self._vb = CustomViewBox()
        self._vb.context_menu_requested.connect(self._show_context_menu)
        self._plot = pg.PlotWidget(viewBox=self._vb)
        self._plot.setMenuEnabled(False)
        self._plot.showGrid(x=True, y=True, alpha=0.25)
        self._plot.getAxis('bottom').setLabel('Time (s)')
        self._plot.scene().sigMouseMoved.connect(self._on_mouse_move)

        self._crosshair_v = pg.InfiniteLine(
            angle=90, movable=False,
            pen=pg.mkPen('#ffffff', width=1, style=Qt.PenStyle.DashLine)
        )
        self._plot.addItem(self._crosshair_v)

        self._tooltip = QLabel('', self._plot)
        self._tooltip.setStyleSheet(
            'QLabel { background-color: rgba(15,15,20,210); color: #e8e8e8; '
            'border: 1px solid #4a4a4a; border-radius: 4px; '
            'padding: 5px 8px; font-family: "Segoe UI", monospace; font-size: 11px; }'
        )
        self._tooltip.setWordWrap(False)
        self._tooltip.hide()

        rv.addWidget(self._plot, 5)

        # Range selector
        self._range_plot = pg.PlotWidget()
        self._range_plot.setFixedHeight(60)
        self._range_plot.setMenuEnabled(False)
        self._range_plot.getAxis('left').hide()
        self._range_plot.getAxis('bottom').setLabel('Time (s)')
        self._range_region = pg.LinearRegionItem(
            brush=pg.mkBrush(80, 130, 200, 50),
            pen=pg.mkPen('#4a90d9', width=2),
            swapMode='block',
        )
        self._range_region.setZValue(10)
        for _line in self._range_region.lines:
            _line.setPen(pg.mkPen('#4a90d9', width=2))
            _line.setHoverPen(pg.mkPen('#ffffff', width=3))
        self._range_plot.addItem(self._range_region)
        self._range_region.sigRegionChanged.connect(self._on_region_changed)
        rv.addWidget(self._range_plot)

        # Time limit controls
        self._time_ctrl = TimeLimitControls()
        self._time_ctrl.range_changed.connect(self._on_time_range_changed)
        rv.addWidget(self._time_ctrl)

        # Stats legend
        self._stats = StatsLegend()
        rv.addWidget(self._stats)

        # Event overlay panel
        self._ev_panel = EventOverlayPanel()
        self._ev_panel.event_clicked.connect(self._on_event_panel_clicked)
        self._ev_panel.severity_visibility_changed.connect(self._on_category_visibility)
        self._ev_panel.event_visibility_changed.connect(self._on_event_visibility)
        rv.addWidget(self._ev_panel)

        # Connect plot range change AFTER all widgets created
        self._plot.sigRangeChanged.connect(self._on_x_range_changed)
        self._plot.sigRangeChanged.connect(lambda: self._update_event_label_positions())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._tree)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        outer.addWidget(splitter)

    # ── Data loading ──────────────────────────────────────────────────────────

    def update_data(self, data: dict):
        self._data = data
        self._color_idx = 0
        self._active_sigs.clear()
        self._t_offset = 0.0

        times_all = []
        for df in data.values():
            if 'TimeS' in df.columns:
                times_all.extend(df['TimeS'].dropna().values)
        if times_all:
            self._t_offset = float(np.min(times_all))
            t_end_rel = float(np.max(times_all)) - self._t_offset
        else:
            t_end_rel = 1.0

        self._t_full = (0.0, t_end_rel)
        self._time_ctrl.set_log_range(0.0, t_end_rel)

        self._plot.clear()
        self._range_plot.clear()
        self._range_plot.addItem(self._range_region)
        self._plot.addItem(self._crosshair_v)
        self._stats.clear()
        self._clear_event_lines()

        self._extract_events(data)
        self._build_tree()
        self._apply_defaults()

        self._range_region.setRegion(self._t_full)

    def _extract_events(self, data: dict):
        """Parse MSG/EV/ERR/ARM/MODE from data into event overlay panel."""
        events = []

        mode_df = data.get('MODE')
        if mode_df is not None and 'TimeS' in mode_df.columns:
            mode_col = next((c for c in ('Mode', 'ModeNum', 'mode') if c in mode_df.columns), None)
            for _, row in mode_df.iterrows():
                ts = float(row['TimeS']) - self._t_offset
                mode_str = str(int(row[mode_col])) if mode_col else '?'
                events.append((ts, 'INFO', 'MODE', f'MODE {mode_str}'))

        arm_df = data.get('ARM')
        if arm_df is not None and 'TimeS' in arm_df.columns:
            for _, row in arm_df.iterrows():
                ts = float(row['TimeS']) - self._t_offset
                events.append((ts, 'INFO', 'ARM', 'ARM/DISARM'))

        msg_df = data.get('MSG')
        if msg_df is not None and 'TimeS' in msg_df.columns:
            msg_col = next((c for c in ('Message', 'Msg') if c in msg_df.columns), None)
            if msg_col:
                for _, row in msg_df.iterrows():
                    ts = float(row['TimeS']) - self._t_offset
                    events.append((ts, 'INFO', 'MSG', str(row[msg_col])))

        ev_df = data.get('EV')
        if ev_df is not None and 'TimeS' in ev_df.columns:
            id_col = next((c for c in ('Id', 'ID', 'id') if c in ev_df.columns), None)
            for _, row in ev_df.iterrows():
                ts = float(row['TimeS']) - self._t_offset
                label = f'id={int(row[id_col])}' if id_col else 'EV'
                events.append((ts, 'INFO', 'EV', label))

        err_df = data.get('ERR')
        if err_df is not None and 'TimeS' in err_df.columns:
            for _, row in err_df.iterrows():
                ts = float(row['TimeS']) - self._t_offset
                events.append((ts, 'ERROR', 'ERR', 'Error'))

        events.sort(key=lambda e: e[0])
        self._ev_panel.set_events(events)
        self._build_event_lines(events)

    def _build_event_lines(self, events: list):
        self._clear_event_lines()
        _lbl_font = QFont('Segoe UI', 8)
        _Y_SLOTS = [0.92, 0.80, 0.68, 0.56, 0.44, 0.32]

        # Build collision groups: events within 1.0s of each other share a group
        sorted_events = sorted(events, key=lambda e: e[0])
        groups: list[list] = []
        cur: list = []
        for evt in sorted_events:
            if not cur or (evt[0] - cur[-1][0]) <= 1.0:
                cur.append(evt)
            else:
                groups.append(cur)
                cur = [evt]
        if cur:
            groups.append(cur)

        for group in groups:
            for slot_idx, (ts, sev, etype, msg) in enumerate(group):
                y_frac = _Y_SLOTS[slot_idx % len(_Y_SLOTS)]
                cat = _event_category(etype, sev, msg)
                pen = EVENT_PEN.get(cat, EVENT_PEN['INFO'])
                color = EVENT_COLORS.get(cat, '#e0e0e0')
                short = _make_short_label(etype, msg)

                line = pg.InfiniteLine(pos=float(ts), angle=90, movable=False, pen=pen)
                line.setToolTip(f'[{ts:.3f}s] {sev} {etype}: {msg}')

                label = pg.TextItem(
                    text=short, color=color,
                    anchor=(0.0, 1.0),
                    fill=pg.mkBrush(15, 15, 20, 200),
                    border=pg.mkPen(color, width=1),
                )
                label.setFont(_lbl_font)
                label.setPos(float(ts), 0)

                self._plot.addItem(line)
                self._plot.addItem(label)

                cat_vis = self._cat_visible.get(cat, True)
                if cat == 'DISARM':
                    cat_vis = self._cat_visible.get('ARM', True)
                line.setVisible(cat_vis)
                label.setVisible(cat_vis)
                self._event_items.append({
                    'ts': ts, 'cat': cat, 'line': line, 'label': label,
                    'visible': True, 'y_frac': y_frac,
                })

        self._update_event_label_positions()

    def _update_event_label_positions(self):
        if not self._event_items:
            return
        try:
            xr = self._vb.viewRange()[0]
            yr = self._vb.viewRange()[1]
            xmin, xmax = xr
            ymin, ymax = yr
        except Exception:
            return
        x_margin = (xmax - xmin) * 0.01
        for item in self._event_items:
            y_frac = item.get('y_frac', 0.85)
            y_pos = ymin + (ymax - ymin) * y_frac
            x = item['ts']
            if x < xmin:
                x = xmin + x_margin
            item['label'].setPos(x, y_pos)

    def _clear_event_lines(self):
        for item in self._event_items:
            try:
                self._plot.removeItem(item['line'])
            except Exception:
                pass
            try:
                self._plot.removeItem(item['label'])
            except Exception:
                pass
        self._event_items.clear()

    # ── Tree ──────────────────────────────────────────────────────────────────

    def _build_tree(self):
        self._tree.blockSignals(True)
        self._tree.clear()

        # Decompose data keys into base_name -> {inst_or_None: df_key}
        base_map: dict[str, dict] = {}
        for df_key in self._data:
            m = _INST_RE.match(df_key)
            if m:
                base = m.group(1)
                inst = int(m.group(2))
                base_map.setdefault(base, {})[inst] = df_key
            else:
                base_map.setdefault(df_key, {})[None] = df_key

        all_grouped = {name for msgs in MSG_GROUPS.values() for name in msgs}
        groups = dict(MSG_GROUPS)
        other = sorted(b for b in base_map if b not in all_grouped)
        if other:
            groups['OTHER'] = other

        for grp_name, msg_list in groups.items():
            grp = QTreeWidgetItem([grp_name])
            grp.setForeground(0, QBrush(QColor('#adb5bd')))
            self._tree.addTopLevelItem(grp)
            found = False

            for base_name in msg_list:
                if base_name not in base_map:
                    continue
                instances = base_map[base_name]
                for inst, df_key in sorted(instances.items(),
                                           key=lambda x: (-1 if x[0] is None else x[0])):
                    df = self._data.get(df_key)
                    if df is None:
                        continue
                    num_cols = [c for c in df.columns
                                if c not in ('TimeUS', 'TimeS')
                                and df[c].dtype.kind in ('f', 'i', 'u')]
                    if not num_cols:
                        continue
                    node_label = base_name if inst is None else f'{base_name}[{inst}]'
                    msg_item = QTreeWidgetItem([node_label])
                    msg_item.setForeground(0, QBrush(QColor('#e0e0e0')))
                    grp.addChild(msg_item)
                    found = True
                    for col in num_cols:
                        fi = QTreeWidgetItem([col])
                        fi.setCheckState(0, Qt.CheckState.Unchecked)
                        fi.setData(0, Qt.ItemDataRole.UserRole, df_key)
                        fi.setData(0, _USER_ROLE_COL, col)
                        msg_item.addChild(fi)

            if found:
                grp.setExpanded(True)

        self._tree.blockSignals(False)
        self._tree.itemChanged.connect(self._on_item_changed)

    def _apply_defaults(self):
        default_set = set(DEFAULT_SIGNALS)
        root = self._tree.invisibleRootItem()
        for gi in range(root.childCount()):
            grp = root.child(gi)
            for mi in range(grp.childCount()):
                msg_item = grp.child(mi)
                for fi in range(msg_item.childCount()):
                    field = msg_item.child(fi)
                    df_key = field.data(0, Qt.ItemDataRole.UserRole)
                    col = field.data(0, _USER_ROLE_COL)
                    if (df_key, col) in default_set:
                        field.setCheckState(0, Qt.CheckState.Checked)

    def _on_item_changed(self, item: QTreeWidgetItem, _col):
        df_key = item.data(0, Qt.ItemDataRole.UserRole)
        if df_key is None:
            return
        col = item.data(0, _USER_ROLE_COL)
        if col is None:
            return
        sig_key = f'{df_key}.{col}'
        if item.checkState(0) == Qt.CheckState.Checked:
            self._add_signal(df_key, col, sig_key)
        else:
            self._remove_signal(sig_key)

    # ── Signal management ─────────────────────────────────────────────────────

    def _add_signal(self, df_key: str, col: str, key: str):
        if key in self._active_sigs:
            return
        df = self._data.get(df_key)
        if df is None or col not in df.columns:
            return
        if 'TimeS' in df.columns:
            times = (df['TimeS'].values - self._t_offset).astype(float)
        else:
            times = np.arange(len(df), dtype=float)
        values = df[col].values.astype(float)
        mask = np.isfinite(values) & np.isfinite(times)
        times, values = times[mask], values[mask]

        color = signal_color(self._color_idx)
        self._color_idx += 1
        curve = self._plot.plot(times, values, pen=pg.mkPen(color=color, width=1.5), name=key)
        rcurve = self._range_plot.plot(times, values, pen=pg.mkPen(color=color, width=1))

        unit = _guess_unit(col)
        self._active_sigs[key] = {
            'df_key': df_key, 'col': col, 'unit': unit,
            'times': times, 'values': values,
            'color': color, 'curve': curve, 'range_curve': rcurve,
        }
        self._stats.add_signal(key, color)
        self._update_range_bounds()
        self._update_all_stats()

    def _remove_signal(self, key: str):
        sig = self._active_sigs.pop(key, None)
        if sig:
            self._plot.removeItem(sig['curve'])
            self._range_plot.removeItem(sig['range_curve'])
            self._stats.remove_signal(key)

    def _clear_all(self):
        self._tree.blockSignals(True)
        root = self._tree.invisibleRootItem()
        for gi in range(root.childCount()):
            grp = root.child(gi)
            for mi in range(grp.childCount()):
                msg_item = grp.child(mi)
                for fi in range(msg_item.childCount()):
                    msg_item.child(fi).setCheckState(0, Qt.CheckState.Unchecked)
        self._tree.blockSignals(False)
        for key, sig in list(self._active_sigs.items()):
            self._plot.removeItem(sig['curve'])
            self._range_plot.removeItem(sig['range_curve'])
        self._active_sigs.clear()
        self._stats.clear()
        self._color_idx = 0

    def _update_range_bounds(self):
        all_t = [v for sig in self._active_sigs.values()
                 for v in (sig['times'][0], sig['times'][-1]) if len(sig['times'])]
        if all_t:
            self._range_region.blockSignals(True)
            self._range_region.setRegion([min(all_t), max(all_t)])
            self._range_region.blockSignals(False)

    # ── Sync: plot ↔ region ↔ time controls ──────────────────────────────────

    def _on_x_range_changed(self, _vb, ranges):
        if self._syncing:
            return
        self._syncing = True
        x0, x1 = ranges[0]
        self._range_region.setRegion([x0, x1])
        self._time_ctrl.set_range(x0, x1)
        self._update_all_stats()
        self._syncing = False

    def _on_region_changed(self):
        if self._syncing:
            return
        self._syncing = True
        x0, x1 = self._range_region.getRegion()
        self._plot.setXRange(x0, x1, padding=0)
        self._time_ctrl.set_range(x0, x1)
        self._update_all_stats()
        self._syncing = False

    def _on_time_range_changed(self, x0: float, x1: float):
        if self._syncing:
            return
        self._syncing = True
        self._plot.setXRange(x0, x1, padding=0)
        self._range_region.setRegion([x0, x1])
        self._update_all_stats()
        self._syncing = False

    # ── Stats ─────────────────────────────────────────────────────────────────

    def _update_all_stats(self):
        x0, x1 = self._plot.getViewBox().viewRange()[0]
        for key, sig in self._active_sigs.items():
            times, values = sig['times'], sig['values']
            mask = (times >= x0) & (times <= x1)
            self._stats.update_signal_stats(key, values[mask])

    # ── Event line visibility ─────────────────────────────────────────────────

    def _on_category_visibility(self, cat: str, visible: bool):
        self._cat_visible[cat] = visible
        if cat == 'ARM':
            self._cat_visible['DISARM'] = visible
        for item in self._event_items:
            c = item['cat']
            if c == cat or (cat == 'ARM' and c == 'DISARM'):
                show = visible and item['visible']
                item['line'].setVisible(show)
                item['label'].setVisible(show)

    def _on_event_visibility(self, idx: int, visible: bool):
        if idx >= len(self._event_items):
            return
        item = self._event_items[idx]
        item['visible'] = visible
        cat_vis = self._cat_visible.get(item['cat'], True)
        if item['cat'] == 'DISARM':
            cat_vis = self._cat_visible.get('ARM', True)
        show = visible and cat_vis
        item['line'].setVisible(show)
        item['label'].setVisible(show)

    def _on_event_panel_clicked(self, ts: float):
        self._crosshair_v.setPos(ts)
        self.crosshair_moved.emit(ts + self._t_offset)
        try:
            self._mw.event_selected.emit(ts + self._t_offset)
        except Exception:
            pass

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def _on_mouse_move(self, pos):
        vb = self._vb
        if not self._plot.sceneBoundingRect().contains(pos):
            self._tooltip.hide()
            return
        mp = vb.mapSceneToView(pos)
        t = mp.x()
        self._crosshair_v.setPos(t)
        self.crosshair_moved.emit(t + self._t_offset)

        parts = []
        for key, sig in self._active_sigs.items():
            times, values = sig['times'], sig['values']
            if len(times) == 0:
                continue
            idx = np.searchsorted(times, t)
            if idx == 0:
                v = values[0]
            elif idx >= len(times):
                v = values[-1]
            else:
                t0, t1 = times[idx - 1], times[idx]
                v0, v1 = values[idx - 1], values[idx]
                dt = t1 - t0
                v = v0 if dt == 0 else v0 + (v1 - v0) * (t - t0) / dt
            unit = sig['unit']
            u_str = f' {unit}' if unit else ''
            parts.append(f'<span style="color:{sig["color"]}">{key}: {v:.4f}{u_str}</span>')

        self._tooltip_text = '  |  '.join(p.replace('<span', '').replace('</span>', '')
                                          .split('>')[1] for p in parts)
        if parts:
            self._tooltip.setText('<br>'.join(parts))
            self._tooltip.adjustSize()
            sp = self._plot.mapFromScene(pos)
            tip_w = self._tooltip.sizeHint().width() + 20
            tip_h = self._tooltip.sizeHint().height() + 10
            x = sp.x() + 15
            y = sp.y() - tip_h // 2
            if x + tip_w > self._plot.width():
                x = sp.x() - tip_w - 15
            y = max(5, min(self._plot.height() - tip_h - 5, y))
            self._tooltip.move(int(x), int(y))
            self._tooltip.resize(tip_w, tip_h)
            self._tooltip.show()
        else:
            self._tooltip.hide()

    # ── Context menu ──────────────────────────────────────────────────────────

    def _show_context_menu(self, qpoint):
        menu = QMenu(self)
        menu.setStyleSheet(
            'QMenu { background: #2a2a3e; color: #e0e0e0; border: 1px solid #495057; }'
            'QMenu::item:selected { background: #3a3a5e; }'
        )
        menu.addAction('Auto Fit', self._auto_fit)
        menu.addAction('Reset View', self._reset_view)
        menu.addSeparator()
        menu.addAction('Copy visible values', self._copy_visible_values)
        menu.addAction('Export visible → CSV', self._export_csv)
        menu.addAction('Export plot → PNG', self._export_png)
        menu.exec(qpoint)

    def _copy_visible_values(self):
        QApplication.clipboard().setText(self._tooltip_text)

    # ── Toolbar actions ───────────────────────────────────────────────────────

    def _auto_fit(self):
        self._plot.autoRange()

    def _zoom_in(self):
        xr = self._vb.viewRange()[0]
        mid = (xr[0] + xr[1]) / 2
        half = (xr[1] - xr[0]) * 0.4
        self._plot.setXRange(mid - half, mid + half, padding=0)

    def _zoom_out(self):
        xr = self._vb.viewRange()[0]
        mid = (xr[0] + xr[1]) / 2
        half = (xr[1] - xr[0]) * 0.6
        self._plot.setXRange(mid - half, mid + half, padding=0)

    def _reset_view(self):
        t0, t1 = self._t_full
        self._plot.setXRange(t0, t1, padding=0.02)
        self._vb.enableAutoRange(axis=pg.ViewBox.YAxis)

    # ── Export ────────────────────────────────────────────────────────────────

    def _export_csv(self):
        if not self._active_sigs:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Export CSV', 'signals.csv', 'CSV (*.csv)')
        if not path:
            return
        import pandas as pd
        x0, x1 = self._vb.viewRange()[0]
        frames = {}
        for key, sig in self._active_sigs.items():
            mask = (sig['times'] >= x0) & (sig['times'] <= x1)
            frames[key + '_t'] = sig['times'][mask]
            frames[key] = sig['values'][mask]
        max_len = max((len(v) for v in frames.values()), default=0)
        out = {}
        for k, v in frames.items():
            padded = np.full(max_len, np.nan)
            padded[:len(v)] = v
            out[k] = padded
        pd.DataFrame(out).to_csv(path, index=False)

    def _export_png(self):
        from PyQt6.QtWidgets import QMessageBox
        path, _ = QFileDialog.getSaveFileName(
            self, 'Export Plot as PNG', 'ardupilot_plot.png', 'PNG (*.png)'
        )
        if not path:
            return
        if not path.lower().endswith('.png'):
            path += '.png'
        try:
            pixmap = self._plot.grab()
            if pixmap.isNull():
                raise RuntimeError('grab() returned null pixmap — widget may not be visible')
            if not pixmap.save(path, 'PNG'):
                raise RuntimeError(f'QPixmap.save() failed for path: {path}')
            QMessageBox.information(self, 'Export Successful', f'Plot saved to:\n{path}')
        except Exception as e:
            QMessageBox.critical(
                self, 'Export Failed',
                f'Could not save PNG:\n{str(e)}\n\nTry a different save location (e.g. Desktop).'
            )

    # ── Public API (called from other tabs) ───────────────────────────────────

    def set_crosshair(self, t_abs: float):
        self._crosshair_v.setPos(t_abs - self._t_offset)

    def set_events(self, events: list):
        """Legacy entry point — events come from update_data now, but keep for compat."""
        pass


# ── Helper ────────────────────────────────────────────────────────────────────

def _sep():
    from PyQt6.QtWidgets import QFrame
    f = QFrame()
    f.setFrameShape(QFrame.Shape.VLine)
    f.setStyleSheet('color: #495057;')
    f.setFixedWidth(1)
    return f
