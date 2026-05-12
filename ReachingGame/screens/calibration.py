import os
import json
import math
from datetime import datetime

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QDoubleSpinBox,
    QPushButton, QSizePolicy, QFrame, QComboBox,
)
from PyQt5.QtCore import Qt, QPoint, QTimer
from PyQt5.QtGui import QPainter, QColor, QBrush, QPen, QFont, QPolygon

SAVE_DIR   = r'C:\Users\Jisung Yuk\Desktop\Liberty\calibrated matrix'
LATEST_CAL = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          '..', 'last_calibration.json')

BTN = """
QPushButton {
    background-color: #888888; color: white; border: none;
    border-radius: 5px; font-size: 15px; padding: 6px 14px;
}
QPushButton:hover   { background-color: #999999; }
QPushButton:pressed { background-color: #777777; }
"""
SPIN = (
    "QDoubleSpinBox { background:#ffffff; color:#000000; border:1px solid #aaaaaa;"
    " border-radius:4px; padding:2px 6px; font-size:14px; }"
    "QDoubleSpinBox::up-button { width:0; } QDoubleSpinBox::down-button { width:0; }"
)
UNIT_BTN = (
    "QPushButton { background:#666666; color:white; border:none;"
    " border-radius:4px; font-size:13px; padding:2px 8px; min-width:34px; }"
    "QPushButton:hover { background:#777777; }"
)
COMBO = (
    "QComboBox { background:#ffffff; color:#000000; border:1px solid #aaaaaa;"
    " border-radius:4px; padding:2px 8px; font-size:14px; }"
    "QComboBox::drop-down { border:none; }"
    "QComboBox QAbstractItemView { background:#ffffff; color:#000000;"
    " selection-background-color:#b0c8e0; }"
)

# Density presets: spacing in cm
_DENSITY = {
    'Sparse (8 in)': 8 * 2.54,
    'Dense  (4 in)': 4 * 2.54,
}


def _error_color(err_cm):
    """Absolute threshold coloring by error magnitude in cm."""
    if err_cm < 0.3:
        return QColor(50, 200, 50)
    elif err_cm < 0.6:
        return QColor(220, 200, 0)
    elif err_cm < 0.9:
        return QColor(230, 110, 0)
    else:
        return QColor(220, 40, 40)


class CalibrationCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(500, 350)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._desk_w  = 86.36
        self._desk_h  = 55.88
        self._mat_w   = 86.36
        self._mat_h   = 55.88
        self._margin  = 2.54          # cm edge offset (default 1 in)

        self._mat_origin_y = None
        self._mat_origin_z = None

        self._grid_points = []
        self._current_idx = 0

        self._s1_y      = 0.0
        self._s1_z      = 0.0
        self._s1_active = False

    # ── public ───────────────────────────────────────────

    def set_desk(self, w_cm, h_cm):
        self._desk_w = max(w_cm, 1)
        self._desk_h = max(h_cm, 1)
        self.update()

    def set_mat(self, w_cm, h_cm):
        self._mat_w = w_cm
        self._mat_h = h_cm
        self.update()

    def set_margin(self, margin_cm):
        self._margin = margin_cm

    def set_origin(self, y_cm, z_cm):
        self._mat_origin_y = y_cm
        self._mat_origin_z = z_cm
        self._build_grid()
        self.update()

    def set_grid(self, cols, rows):
        self._cols = cols
        self._rows = rows

    def reset(self):
        self._mat_origin_y = None
        self._mat_origin_z = None
        self._grid_points  = []
        self._current_idx  = 0
        self.update()

    def record_current(self, y_cm, z_cm):
        if 0 <= self._current_idx < len(self._grid_points):
            pt = self._grid_points[self._current_idx]
            pt['meas_y']   = y_cm
            pt['meas_z']   = z_cm
            pt['measured'] = True
            self._current_idx += 1
            self.update()
            return self._current_idx >= len(self._grid_points)
        return False

    def undo_last(self):
        if self._current_idx > 0:
            self._current_idx -= 1
            pt = self._grid_points[self._current_idx]
            pt['meas_y']   = None
            pt['meas_z']   = None
            pt['measured'] = False
            self.update()
            return True
        return False

    def skip_current(self):
        """Skip current point (mark as skipped, advance index)."""
        if 0 <= self._current_idx < len(self._grid_points):
            self._grid_points[self._current_idx]['skipped'] = True
            self._current_idx += 1
            self.update()
            return self._current_idx >= len(self._grid_points)
        return False

    def update_s1(self, y, z, active):
        self._s1_y, self._s1_z, self._s1_active = y, z, active
        self.update()

    def get_stats(self):
        pts = [p for p in self._grid_points if p['measured']]
        if not pts:
            return None
        errors = [math.sqrt((p['meas_y'] - p['y_desk'])**2 +
                            (p['meas_z'] - p['z_desk'])**2) for p in pts]
        rms = math.sqrt(sum(e**2 for e in errors) / len(errors))
        return {'n': len(pts), 'rms': rms, 'max': max(errors)}

    # ── internal ─────────────────────────────────────────

    def _build_grid(self):
        cols   = getattr(self, '_cols', 5)
        rows   = getattr(self, '_rows', 4)
        m      = self._margin
        use_w  = max(self._mat_w - 2 * m, 0)
        use_h  = max(self._mat_h - 2 * m, 0)
        self._grid_points = []
        for r in range(rows):
            for c in range(cols):
                yl = m + c / max(cols - 1, 1) * use_w
                zl = m + r / max(rows - 1, 1) * use_h
                self._grid_points.append({
                    'y_local': yl, 'z_local': zl,
                    'y_desk': self._mat_origin_y + yl,
                    'z_desk': self._mat_origin_z + zl,
                    'meas_y': None, 'meas_z': None,
                    'measured': False,
                })
        self._current_idx = 0

    def _sao(self):
        pad = 30
        aw  = self.width()  - 2 * pad
        ah  = self.height() - 2 * pad
        sc  = min(aw / max(self._desk_w, 1), ah / max(self._desk_h, 1))
        ox  = pad + (aw - self._desk_w * sc) / 2
        oy  = pad + (ah - self._desk_h * sc) / 2
        return sc, ox, oy

    def _px(self, y_cm, z_cm):
        sc, ox, oy = self._sao()
        return int(ox + y_cm * sc), int(oy + (self._desk_h - z_cm) * sc)

    def _draw_arrow(self, p, x1, y1, x2, y2, color, head=8):
        dx, dy = x2 - x1, y2 - y1
        length = math.sqrt(dx * dx + dy * dy)
        p.setPen(QPen(color, 2))
        p.drawLine(x1, y1, x2, y2)
        if length < 3:
            return
        ux, uy = dx / length, dy / length
        ax = int(x2 - head * (ux - 0.4 * uy))
        ay = int(y2 - head * (uy + 0.4 * ux))
        bx = int(x2 - head * (ux + 0.4 * uy))
        by = int(y2 - head * (uy - 0.4 * ux))
        p.setBrush(QBrush(color))
        p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygon([QPoint(x2, y2), QPoint(ax, ay), QPoint(bx, by)]))

    # ── drawing ──────────────────────────────────────────

    def paintEvent(self, _):
        sc, ox, oy = self._sao()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(220, 220, 220))

        # Desk
        dw, dh = int(self._desk_w * sc), int(self._desk_h * sc)
        p.setBrush(QBrush(QColor(205, 175, 135)))
        p.setPen(QPen(QColor(100, 75, 50), 2))
        p.drawRect(int(ox), int(oy), dw, dh)
        p.setPen(QColor(100, 75, 50))
        p.setFont(QFont('Arial', 11))
        p.drawText(int(ox + 6), int(oy + 15),
                   f"Desk  {self._desk_w:.0f} × {self._desk_h:.0f} cm")

        dash = QPen(QColor(100, 75, 50, 100), 1, Qt.DashLine)
        p.setPen(dash)
        p.drawLine(int(ox + dw/2), int(oy), int(ox + dw/2), int(oy + dh))
        p.drawLine(int(ox), int(oy + dh/2), int(ox + dw), int(oy + dh/2))

        if self._mat_origin_y is None:
            # S1 cursor only
            self._paint_cursor(p)
            return

        # Mat rect
        mx, my = self._px(self._mat_origin_y, self._mat_origin_z + self._mat_h)
        mw, mh = int(self._mat_w * sc), int(self._mat_h * sc)
        p.setBrush(QBrush(QColor(100, 180, 100, 50)))
        p.setPen(QPen(QColor(50, 140, 50), 2))
        p.drawRect(mx, my, mw, mh)
        p.setPen(QColor(50, 140, 50))
        p.setFont(QFont('Arial', 10))
        p.drawText(mx + 4, my + 14,
                   f"Mat  {self._mat_w:.0f} × {self._mat_h:.0f} cm")

        # ── quiver field: colored arrows from known → measured ──
        for pt in self._grid_points:
            if not pt['measured']:
                continue
            kx, ky = self._px(pt['y_desk'], pt['z_desk'])
            ex, ey = self._px(pt['meas_y'],  pt['meas_z'])
            err    = math.sqrt((pt['meas_y'] - pt['y_desk'])**2 +
                               (pt['meas_z'] - pt['z_desk'])**2)
            color = _error_color(err)
            self._draw_arrow(p, kx, ky, ex, ey, color)
            # error label next to arrow tip
            p.setPen(color)
            p.setFont(QFont('Arial', 16))
            p.drawText(ex + 5, ey - 3, f"{err:.2f}")

        # ── pending / current grid dots ──
        for i, pt in enumerate(self._grid_points):
            if pt['measured']:
                continue
            kx, ky = self._px(pt['y_desk'], pt['z_desk'])
            if i == self._current_idx:
                p.setBrush(QBrush(QColor(60, 130, 220)))
                p.setPen(QPen(QColor(20, 70, 170), 2))
                p.drawEllipse(QPoint(kx, ky), 9, 9)
                p.setPen(QColor(10, 40, 120))
                p.setFont(QFont('Arial', 10, QFont.Bold))
                p.drawText(kx + 12, ky + 4, f"{i+1}")
            else:
                p.setBrush(QBrush(QColor(100, 160, 230)))
                p.setPen(Qt.NoPen)
                p.drawEllipse(QPoint(kx, ky), 5, 5)

        self._paint_cursor(p)

    def _paint_cursor(self, p):
        if not self._s1_active:
            return
        sx, sy = self._px(self._s1_y, self._s1_z)
        p.setPen(QPen(QColor(220, 30, 30), 1))
        p.drawLine(sx - 21, sy, sx + 21, sy)
        p.drawLine(sx, sy - 21, sx, sy + 21)
        p.setBrush(QBrush(QColor(220, 30, 30, 160)))
        p.setPen(QPen(QColor(255, 255, 255), 1))
        p.drawEllipse(QPoint(sx, sy), 9, 9)


class CalibrationScreen(QWidget):
    def __init__(self, state, liberty, main_window):
        super().__init__()
        self.setObjectName('CalibrationScreen')
        self.setStyleSheet('#CalibrationScreen { background-color: #f0f0f0; }')
        self.setFocusPolicy(Qt.StrongFocus)
        self.state   = state
        self.liberty = liberty
        self.mw      = main_window
        self._phase    = 'set_origin'
        self._mat_unit = 'in'
        self._build()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(50)

    # ── build ─────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        # Top bar
        top = QHBoxLayout()
        back = QPushButton("← Back")
        back.setStyleSheet(BTN)
        back.clicked.connect(lambda: self.mw.show_screen('menu'))
        top.addWidget(back)
        top.addStretch()
        title = QLabel("Calibration")
        title.setFont(QFont('Arial', 22, QFont.Bold))
        title.setStyleSheet("color: #000000;")
        top.addWidget(title)
        top.addStretch()
        root.addLayout(top)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #cccccc;")
        root.addWidget(sep)

        # Settings row
        srow = QHBoxLayout()
        srow.setSpacing(10)

        srow.addWidget(self._bold("Mat"))
        srow.addWidget(QLabel("W:"))
        self.mat_w = QDoubleSpinBox()
        self.mat_w.setRange(1, 300)
        self.mat_w.setValue(34.0)
        self.mat_w.setSuffix(" in")
        self.mat_w.setFixedWidth(80)
        self.mat_w.setStyleSheet(SPIN)
        srow.addWidget(self.mat_w)

        srow.addWidget(QLabel("H:"))
        self.mat_h = QDoubleSpinBox()
        self.mat_h.setRange(1, 300)
        self.mat_h.setValue(22.0)
        self.mat_h.setSuffix(" in")
        self.mat_h.setFixedWidth(80)
        self.mat_h.setStyleSheet(SPIN)
        srow.addWidget(self.mat_h)

        self.mat_unit_btn = QPushButton("in")
        self.mat_unit_btn.setStyleSheet(UNIT_BTN)
        self.mat_unit_btn.clicked.connect(self._toggle_mat_unit)
        srow.addWidget(self.mat_unit_btn)

        srow.addSpacing(20)
        srow.addWidget(self._bold("Density"))

        self.density_combo = QComboBox()
        for label, spacing_cm in _DENSITY.items():
            self.density_combo.addItem(label, spacing_cm)
        self.density_combo.setFixedWidth(140)
        self.density_combo.setStyleSheet(COMBO)
        self.density_combo.currentIndexChanged.connect(self._update_grid_lbl)
        srow.addWidget(self.density_combo)

        self.grid_lbl = QLabel()
        self.grid_lbl.setStyleSheet("color: #555555; font-size: 14px;")
        srow.addWidget(self.grid_lbl)

        self.mat_w.valueChanged.connect(self._update_grid_lbl)
        self.mat_h.valueChanged.connect(self._update_grid_lbl)

        srow.addStretch()
        root.addLayout(srow)

        # Canvas
        self.canvas = CalibrationCanvas()
        root.addWidget(self.canvas)

        # Instruction
        self.instr_lbl = QLabel()
        self.instr_lbl.setAlignment(Qt.AlignCenter)
        self.instr_lbl.setFont(QFont('Arial', 15))
        self.instr_lbl.setStyleSheet("color: #333333;")
        root.addWidget(self.instr_lbl)

        # Bottom bar
        bot = QHBoxLayout()
        self.stat_lbl = QLabel("")
        self.stat_lbl.setFont(QFont('Arial', 13))
        self.stat_lbl.setStyleSheet("color: #333333;")
        bot.addWidget(self.stat_lbl)
        bot.addStretch()

        self.start_btn = QPushButton("Reset")
        self.start_btn.setStyleSheet(BTN)
        self.start_btn.clicked.connect(self._on_start)
        bot.addWidget(self.start_btn)
        bot.addSpacing(8)

        self.save_btn = QPushButton("Save")
        self.save_btn.setStyleSheet(BTN)
        self.save_btn.clicked.connect(self._on_save)
        self.save_btn.setEnabled(False)
        bot.addWidget(self.save_btn)
        root.addLayout(bot)

        self._update_grid_lbl()
        self._refresh_desk()
        self._set_phase('set_origin')

    def _bold(self, text):
        lbl = QLabel(text)
        lbl.setFont(QFont('Arial', 15, QFont.Bold))
        lbl.setStyleSheet("color:#000000;")
        return lbl

    # ── mat unit toggle ────────────────────────────────────

    def _toggle_mat_unit(self):
        w, h = self.mat_w.value(), self.mat_h.value()
        if self._mat_unit == 'in':
            self._mat_unit = 'cm'
            self.mat_w.setRange(1, 762); self.mat_h.setRange(1, 762)
            self.mat_w.setValue(round(w * 2.54, 1))
            self.mat_h.setValue(round(h * 2.54, 1))
            self.mat_w.setSuffix(" cm"); self.mat_h.setSuffix(" cm")
        else:
            self._mat_unit = 'in'
            self.mat_w.setRange(1, 300); self.mat_h.setRange(1, 300)
            self.mat_w.setValue(round(w / 2.54, 1))
            self.mat_h.setValue(round(h / 2.54, 1))
            self.mat_w.setSuffix(" in"); self.mat_h.setSuffix(" in")
        self.mat_unit_btn.setText(self._mat_unit)

    def _mat_dims_cm(self):
        w, h = self.mat_w.value(), self.mat_h.value()
        if self._mat_unit == 'in':
            return w * 2.54, h * 2.54
        return w, h

    def _margin_cm(self):
        return 2.54 if self._mat_unit == 'in' else 5.0

    # ── grid calculation ───────────────────────────────────

    def _spacing_cm(self):
        return self.density_combo.currentData()

    def _calc_grid(self):
        w_cm, h_cm = self._mat_dims_cm()
        m  = self._margin_cm()
        sp = max(self._spacing_cm(), 0.01)
        usable_w = max(w_cm - 2 * m, 1)
        usable_h = max(h_cm - 2 * m, 1)
        cols = max(2, int(usable_w / sp) + 1)
        rows = max(2, int(usable_h / sp) + 1)
        return cols, rows

    def _update_grid_lbl(self):
        cols, rows = self._calc_grid()
        self.grid_lbl.setText(f"→  {cols} × {rows}  ({cols * rows} pts)")

    def _refresh_desk(self):
        dw = self.state.env_desk_w
        dh = self.state.env_desk_h
        if self.state.env_desk_unit == 'in':
            dw *= 2.54; dh *= 2.54
        self.canvas.set_desk(dw, dh)

    # ── phase control ─────────────────────────────────────

    def _set_phase(self, phase):
        self._phase = phase
        self.start_btn.setEnabled(True)
        if phase == 'set_origin':
            self.instr_lbl.setText(
                "Place S1 at the mat's bottom-left corner (origin), then press  T.")
            self.save_btn.setEnabled(False)
            self.stat_lbl.setText("")
        elif phase == 'measuring':
            self._update_instr()
            self.save_btn.setEnabled(False)
        elif phase == 'done':
            self.instr_lbl.setText("Calibration complete. Press Save to export.")
            self.save_btn.setEnabled(True)
            st = self.canvas.get_stats()
            if st:
                rms_in = st['rms'] / 2.54
                max_in = st['max'] / 2.54
                self.stat_lbl.setText(
                    f"Points: {st['n']}   "
                    f"RMS: {st['rms']:.2f} cm  ({rms_in:.3f} in)   "
                    f"Max: {st['max']:.2f} cm  ({max_in:.3f} in)")

    def _update_instr(self):
        idx   = self.canvas._current_idx
        total = len(self.canvas._grid_points)
        if idx < total:
            pt    = self.canvas._grid_points[idx]
            y_in  = pt['y_local'] / 2.54
            z_in  = pt['z_local'] / 2.54
            self.instr_lbl.setText(
                f"Point {idx+1} / {total}  —  "
                f"Y = {pt['y_local']:.1f} cm ({y_in:.1f} in)   "
                f"Z = {pt['z_local']:.1f} cm ({z_in:.1f} in)  "
                f"|  T = record   R = undo   Y = skip")

    # ── actions ───────────────────────────────────────────

    def _load_latest(self):
        if not os.path.exists(LATEST_CAL):
            return False
        try:
            with open(LATEST_CAL) as f:
                data = json.load(f)
            w_cm = data['mat_w_cm']
            h_cm = data['mat_h_cm']
            # Update mat spinboxes without triggering grid recalc
            for spin in (self.mat_w, self.mat_h):
                spin.blockSignals(True)
            if self._mat_unit == 'in':
                self.mat_w.setValue(round(w_cm / 2.54, 1))
                self.mat_h.setValue(round(h_cm / 2.54, 1))
            else:
                self.mat_w.setValue(round(w_cm, 1))
                self.mat_h.setValue(round(h_cm, 1))
            for spin in (self.mat_w, self.mat_h):
                spin.blockSignals(False)
            self._update_grid_lbl()

            self._refresh_desk()
            c = self.canvas
            c._mat_w         = w_cm
            c._mat_h         = h_cm
            c._margin        = data.get('margin_cm', 2.54)
            c._cols          = data['grid_cols']
            c._rows          = data['grid_rows']
            c._mat_origin_y  = data['mat_origin_y']
            c._mat_origin_z  = data['mat_origin_z']
            c._build_grid()
            for i, sp in enumerate(data.get('points', [])):
                if i < len(c._grid_points) and sp.get('measured'):
                    c._grid_points[i].update(
                        meas_y=sp['meas_y'], meas_z=sp['meas_z'], measured=True)
            c._current_idx = len(c._grid_points)
            c.update()
            self._set_phase('done')
            return True
        except Exception:
            return False

    def _on_start(self):
        if not self._load_latest():
            self._refresh_desk()
            w_cm, h_cm = self._mat_dims_cm()
            self.canvas.set_mat(w_cm, h_cm)
            self.canvas.set_margin(self._margin_cm())
            self.canvas.set_grid(*self._calc_grid())
            self.canvas.reset()
            self._set_phase('set_origin')

    def _on_save(self):
        os.makedirs(SAVE_DIR, exist_ok=True)
        ts   = datetime.now().strftime('%Y%m%d_%H%M%S')
        path = os.path.join(SAVE_DIR, f'calibration_{ts}.json')
        w_cm, h_cm = self._mat_dims_cm()
        st = self.canvas.get_stats() or {}
        cols, rows = self._calc_grid()
        data = {
            'timestamp':    ts,
            'mat_w_cm':     w_cm,
            'mat_h_cm':     h_cm,
            'margin_cm':    self._margin_cm(),
            'mat_origin_y': self.canvas._mat_origin_y,
            'mat_origin_z': self.canvas._mat_origin_z,
            'grid_cols':    cols,
            'grid_rows':    rows,
            'rms_error_cm': st.get('rms'),
            'max_error_cm': st.get('max'),
            'points':       self.canvas._grid_points,
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        with open(LATEST_CAL, 'w') as f:
            json.dump(data, f, indent=2)
        self.instr_lbl.setText(f"Saved → {path}")

    # ── timer / key ───────────────────────────────────────

    def _tick(self):
        s1 = self.liberty.get_sensor(1)
        if s1 is None:
            self.canvas.update_s1(0, 0, False)
            return
        y, z = s1.y * 2.54, s1.z * 2.54
        active = (0 <= y <= self.canvas._desk_w and
                  0 <= z <= self.canvas._desk_h)
        self.canvas.update_s1(y, z, active)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.mw.show_screen('menu')
            return

        if e.key() == Qt.Key_T:
            s1 = self.liberty.get_sensor(1)
            if s1 is None:
                return
            y, z = s1.y * 2.54, s1.z * 2.54
            if self._phase == 'set_origin':
                self.canvas.set_origin(y, z)
                self._set_phase('measuring')
            elif self._phase == 'measuring':
                done = self.canvas.record_current(y, z)
                if done:
                    self._set_phase('done')
                else:
                    self._update_instr()

        elif e.key() == Qt.Key_R and self._phase == 'measuring':
            if self.canvas.undo_last():
                self._update_instr()

        elif e.key() == Qt.Key_Y and self._phase == 'measuring':
            if self.canvas.skip_current():
                self._set_phase('done')
            else:
                self._update_instr()

        super().keyPressEvent(e)

    def showEvent(self, e):
        self.setFocus()
        self._on_start()
