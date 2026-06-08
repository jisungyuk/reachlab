import math
import threading
import winsound
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QDoubleSpinBox, QComboBox, QPushButton,
                             QSizePolicy, QFrame, QMessageBox)
from PyQt5.QtCore import Qt, QPointF, QPoint, QTimer, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QBrush, QPen, QFont, QPolygon

ASPECT_RATIOS = [
    ('16:9',  16, 9),
    ('16:10', 16, 10),
    ('3:2',   3,  2),
    ('4:3',   4,  3),
    ('21:9',  21, 9),
]

HANDLE_PX = 12

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


class WorkspaceCanvas(QWidget):
    changed = pyqtSignal(float, float, float, float)  # y_min, y_max, z_min, z_max

    def __init__(self):
        super().__init__()
        self.setMinimumSize(500, 350)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self._desk_w = 86.36
        self._desk_h = 55.88
        self._aspect = 16 / 9

        # Monitor rect in desk-cm coords
        self._rx = 13.0
        self._ry = 11.0
        self._rw = 59.8
        self._rh = 33.6

        self._dragging    = False
        self._resizing    = False
        self._drag_off    = QPointF()
        self._res_start   = QPointF()
        self._res_ow      = 0.0
        self._real_mon_w  = 0.0   # physical monitor width in cm (from set_monitor)

        self._cursor_y      = 0.0
        self._cursor_z      = 0.0
        self._cursor_active = False
        self._source_y      = None
        self._source_z      = None

    # ── public ───────────────────────────────────────────

    def set_desk(self, w, h):
        self._desk_w = max(w, 1)
        self._desk_h = max(h, 1)
        self._clamp()
        self.update()
        self._emit()

    def center(self):
        self._rx = (self._desk_w - self._rw) / 2
        self._ry = (self._desk_h - self._rh) / 2
        self.update()
        self._emit()

    def set_monitor(self, w_cm, h_cm):
        self._real_mon_w = w_cm
        self._aspect = w_cm / max(h_cm, 0.001)
        self._rw = min(w_cm, self._desk_w)
        self._rh = self._rw / self._aspect
        self._rx = (self._desk_w - self._rw) / 2
        self._ry = (self._desk_h - self._rh) / 2
        self._clamp()
        self.update()
        self._emit()

    def restore_rect(self, rx, ry, rw, rh):
        self._rw     = rw
        self._rh     = rh
        self._aspect = rw / max(rh, 0.001)
        self._rx     = rx
        self._ry     = ry
        self.update()
        self._emit()

    def fit_max(self):
        if self._aspect > 0:
            self._rw = min(self._desk_w, self._desk_h * self._aspect)
            self._rh = self._rw / self._aspect
        self._rx = (self._desk_w - self._rw) / 2
        self._ry = (self._desk_h - self._rh) / 2
        self.update()
        self._emit()

    def set_scale(self, scale):
        if self._real_mon_w <= 0:
            return
        cx = self._rx + self._rw / 2
        cy = self._ry + self._rh / 2
        self._rw = self._real_mon_w * scale
        self._rh = self._rw / max(self._aspect, 0.001)
        self._rx = cx - self._rw / 2
        self._ry = cy - self._rh / 2
        self.update()
        self._emit()

    # ── internal ─────────────────────────────────────────

    def _sao(self):
        pad = 30
        aw = self.width()  - 2 * pad
        ah = self.height() - 2 * pad
        scale = min(aw / self._desk_w, ah / self._desk_h)
        ox = pad + (aw - self._desk_w * scale) / 2
        oy = pad + (ah - self._desk_h * scale) / 2
        return scale, ox, oy

    def _to_px(self, cx, cy):
        s, ox, oy = self._sao()
        return ox + cx * s, oy + (self._desk_h - cy) * s

    def _to_cm(self, px, py):
        s, ox, oy = self._sao()
        return (px - ox) / s, self._desk_h - (py - oy) / s

    def _handle_px(self):
        s, ox, oy = self._sao()
        hx = ox + (self._rx + self._rw) * s
        hy = oy + (self._desk_h - self._ry) * s
        h  = HANDLE_PX
        return hx - h, hy - h, hx + h, hy + h

    def _in_handle(self, px, py):
        x1, y1, x2, y2 = self._handle_px()
        return x1 <= px <= x2 and y1 <= py <= y2

    def _in_rect(self, px, py):
        s, ox, oy = self._sao()
        mx     = ox + self._rx * s
        my_top = oy + (self._desk_h - self._ry - self._rh) * s
        my_bot = oy + (self._desk_h - self._ry) * s
        return mx <= px <= mx + self._rw * s and my_top <= py <= my_bot

    def _clamp(self):
        # Fit within desk while preserving aspect ratio
        if self._aspect > 0:
            max_by_w = self._desk_w
            max_by_h = self._desk_h * self._aspect
            self._rw = max(5.0, min(self._rw, min(max_by_w, max_by_h)))
            self._rh = self._rw / self._aspect
        else:
            self._rw = max(5.0, min(self._rw, self._desk_w))
            self._rh = max(5.0, min(self._rh, self._desk_h))
        self._rx = max(0.0, min(self._rx, self._desk_w - self._rw))
        self._ry = max(0.0, min(self._ry, self._desk_h - self._rh))

    def _clamp_pos_only(self):
        # Clamp position only — never restricts size (used when dragging/moving an oversized rect)
        if self._rw <= self._desk_w:
            self._rx = max(0.0, min(self._rx, self._desk_w - self._rw))
        if self._rh <= self._desk_h:
            self._ry = max(0.0, min(self._ry, self._desk_h - self._rh))

    def update_cursor(self, y, z, active):
        self._cursor_y, self._cursor_z, self._cursor_active = y, z, active
        self.update()

    def set_source(self, y, z):
        self._source_y = y
        self._source_z = z
        self.update()

    def _emit(self):
        self.changed.emit(self._rx, self._rx + self._rw,
                          self._ry, self._ry + self._rh)

    # ── drawing ──────────────────────────────────────────

    def paintEvent(self, e):
        s, ox, oy = self._sao()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(220, 220, 220))

        # Desk
        dw, dh = int(self._desk_w * s), int(self._desk_h * s)
        p.setBrush(QBrush(QColor(205, 175, 135)))
        p.setPen(QPen(QColor(100, 75, 50), 2))
        p.drawRect(int(ox), int(oy), dw, dh)
        p.setPen(QColor(100, 75, 50))
        p.setFont(QFont('Arial', 11))
        p.drawText(int(ox + 6), int(oy + 15),
                   f"Desk  {self._desk_w:.0f} × {self._desk_h:.0f} cm")

        # Monitor rect
        mx = ox + self._rx * s
        my = oy + (self._desk_h - self._ry - self._rh) * s
        mw = int(self._rw * s)
        mh = int(self._rh * s)
        p.setBrush(QBrush(QColor(70, 130, 220, 90)))
        p.setPen(QPen(QColor(30, 90, 200), 2))
        p.drawRect(int(mx), int(my), mw, mh)
        p.setPen(QColor(30, 90, 200))
        p.setFont(QFont('Arial', 11, QFont.Bold))
        scale_str = ""
        if self._real_mon_w > 0:
            scale_str = f"  ×{self._rw / self._real_mon_w:.2f}"
        p.drawText(int(mx + 5), int(my + 15),
                   f"{self._rw:.1f} × {self._rh:.1f} cm{scale_str}")

        # Center lines — desk
        dash = QPen(QColor(100, 75, 50, 120), 1, Qt.DashLine)
        p.setPen(dash)
        p.drawLine(int(ox + dw / 2), int(oy), int(ox + dw / 2), int(oy + dh))
        p.drawLine(int(ox), int(oy + dh / 2), int(ox + dw), int(oy + dh / 2))

        # Center lines — monitor rect
        dash2 = QPen(QColor(30, 90, 200, 160), 1, Qt.DashLine)
        p.setPen(dash2)
        p.drawLine(int(mx + mw / 2), int(my), int(mx + mw / 2), int(my + mh))
        p.drawLine(int(mx), int(my + mh / 2), int(mx + mw), int(my + mh / 2))

        # Player marker — bottom-center of desk
        px_p, py_p = self._to_px(self._desk_w / 2, 0)
        tri_size = 8
        tri = QPolygon([
            QPoint(int(px_p),            int(py_p) + 2),
            QPoint(int(px_p) - tri_size, int(py_p) + 2 + tri_size * 2),
            QPoint(int(px_p) + tri_size, int(py_p) + 2 + tri_size * 2),
        ])
        p.setBrush(QBrush(QColor(220, 60, 60)))
        p.setPen(QPen(QColor(160, 30, 30), 1))
        p.drawPolygon(tri)
        p.setPen(QColor(160, 30, 30))
        p.setFont(QFont('Arial', 11, QFont.Bold))
        p.drawText(int(px_p) - 22, int(py_p) + 2 + tri_size * 2 + 14, "Player")

        # Resize handle (bottom-right)
        x1, y1, x2, y2 = self._handle_px()
        p.setBrush(QBrush(QColor(30, 90, 200)))
        p.setPen(Qt.NoPen)
        p.drawRect(int(x1), int(y1), int(x2 - x1), int(y2 - y1))

        self._draw_source(p)
        self._draw_cursor(p)

    def _draw_source(self, p):
        if self._source_y is None:
            return
        sx, sy = self._to_px(self._source_y, self._source_z)
        half = 10
        p.setPen(QPen(QColor(255, 200, 0), 2))
        p.setBrush(Qt.NoBrush)
        p.drawRect(int(sx) - half, int(sy) - half, half * 2, half * 2)
        p.drawLine(int(sx) - half - 6, int(sy), int(sx) + half + 6, int(sy))
        p.drawLine(int(sx), int(sy) - half - 6, int(sx), int(sy) + half + 6)
        p.setPen(QColor(255, 200, 0))
        p.setFont(QFont('Arial', 10, QFont.Bold))
        p.drawText(int(sx) + half + 4, int(sy) + 4, "Source")

    def _draw_cursor(self, p):
        if not self._cursor_active:
            return
        sx, sy = self._to_px(self._cursor_y, self._cursor_z)
        p.setPen(QPen(QColor(220, 30, 30), 1))
        p.drawLine(int(sx) - 21, int(sy), int(sx) + 21, int(sy))
        p.drawLine(int(sx), int(sy) - 21, int(sx), int(sy) + 21)
        p.setBrush(QBrush(QColor(220, 30, 30, 160)))
        p.setPen(QPen(QColor(255, 255, 255), 1))
        p.drawEllipse(QPoint(int(sx), int(sy)), 9, 9)

    # ── mouse ────────────────────────────────────────────

    def mousePressEvent(self, e):
        self.setFocus()
        px, py = e.x(), e.y()
        if self._in_handle(px, py):
            self._resizing  = True
            self._res_start = QPointF(px, py)
            self._res_ow    = self._rw
        elif self._in_rect(px, py):
            self._dragging = True
            cx, cy = self._to_cm(px, py)
            self._drag_off = QPointF(cx - self._rx, cy - self._ry)

    def keyPressEvent(self, e):
        step = 5.0 if e.modifiers() & Qt.ShiftModifier else 1.0
        key  = e.key()
        if   key == Qt.Key_Left:  self._rx -= step
        elif key == Qt.Key_Right: self._rx += step
        elif key == Qt.Key_Up:    self._ry += step
        elif key == Qt.Key_Down:  self._ry -= step
        else:
            super().keyPressEvent(e)
            return
        self._clamp_pos_only()
        self.update()
        self._emit()

    def mouseMoveEvent(self, e):
        px, py = e.x(), e.y()
        if self._resizing:
            s, _, _ = self._sao()
            dx = (px - self._res_start.x()) / s
            nw = max(5.0, self._res_ow + dx)
            nh = nw / self._aspect
            nw = min(nw, self._desk_w - self._rx)
            nh = min(nh, self._desk_h - self._ry)
            if nw / max(nh, 0.001) > self._aspect:
                nw = nh * self._aspect
            else:
                nh = nw / self._aspect
            self._rw, self._rh = nw, nh
            self.update()
            self._emit()
        elif self._dragging:
            cx, cy = self._to_cm(px, py)
            self._rx = cx - self._drag_off.x()
            self._ry = cy - self._drag_off.y()
            self._clamp_pos_only()
            self.update()
            self._emit()

        if self._in_handle(px, py):
            self.setCursor(Qt.SizeFDiagCursor)
        elif self._in_rect(px, py):
            self.setCursor(Qt.SizeAllCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def mouseReleaseEvent(self, e):
        self._dragging = False
        self._resizing = False


class EnvironmentScreen(QWidget):
    def __init__(self, state, liberty, main_window):
        super().__init__()
        self.setObjectName('EnvironmentScreen')
        self.setStyleSheet('#EnvironmentScreen { background-color: #f0f0f0; }')
        self.state   = state
        self.liberty = liberty
        self.mw      = main_window
        self._ws        = (0.0, 59.8, 0.0, 33.6)
        self._mon_unit  = state.env_mon_unit
        self._desk_unit = state.env_desk_unit
        self._origin_countdown = 0
        self._origin_timer = QTimer(self)
        self._origin_timer.timeout.connect(self._origin_tick)
        self._cursor_timer = QTimer(self)
        self._cursor_timer.timeout.connect(self._tick)
        self._cursor_timer.start(50)
        self._build()

    def showEvent(self, e):
        super().showEvent(e)
        self._load_task_env()

    def _load_task_env(self):
        task_key = self.state.task_type
        for attr in ('env_rect_x', 'env_rect_y', 'env_rect_w', 'env_rect_h'):
            setattr(self.state, attr, None)
        self.state.load_task_rect(task_key, fallback=False)
        task_name = task_key.replace('_', ' ').title()
        self.title_lbl.setText(f"Environment — {task_name}")
        if self.state.env_rect_x is not None:
            self.canvas.restore_rect(
                self.state.env_rect_x, self.state.env_rect_y,
                self.state.env_rect_w, self.state.env_rect_h,
            )

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
        self.title_lbl = QLabel("Environment")
        self.title_lbl.setFont(QFont('Arial', 22, QFont.Bold))
        self.title_lbl.setStyleSheet("color: #000000;")
        top.addWidget(self.title_lbl)
        top.addStretch()
        root.addLayout(top)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #cccccc;")
        root.addWidget(sep)

        # Settings row
        srow = QHBoxLayout()
        srow.setSpacing(10)

        srow.addWidget(self._bold("Monitor"))
        srow.addWidget(QLabel("Size:"))
        self.mon_size = QDoubleSpinBox()
        if self._mon_unit == 'cm':
            self.mon_size.setRange(12, 305)
        else:
            self.mon_size.setRange(5, 120)
        self.mon_size.setValue(self.state.env_mon_size)
        self.mon_size.setSuffix(f" {self._mon_unit}")
        self.mon_size.setFixedWidth(80)
        self.mon_size.setStyleSheet(SPIN)
        srow.addWidget(self.mon_size)

        srow.addWidget(QLabel("Ratio:"))
        self.ratio_cb = QComboBox()
        for label, rw, rh in ASPECT_RATIOS:
            self.ratio_cb.addItem(label, (rw, rh))
        self.ratio_cb.setCurrentIndex(self.state.env_mon_ratio_idx)
        self.ratio_cb.setStyleSheet(
            "QComboBox { background:#fff; color:#000; border:1px solid #aaa;"
            " border-radius:4px; padding:2px 8px; font-size:14px; }"
            "QComboBox QAbstractItemView { background:#fff; color:#000;"
            " selection-background-color:#b0c8e0; }"
        )
        srow.addWidget(self.ratio_cb)

        self.mon_unit_btn = QPushButton(self._mon_unit)
        self.mon_unit_btn.setStyleSheet(UNIT_BTN)
        self.mon_unit_btn.clicked.connect(self._toggle_mon_unit)
        srow.addWidget(self.mon_unit_btn)

        self.mon_info = QLabel("")
        self.mon_info.setStyleSheet("color:#555555; font-size:14px;")
        srow.addWidget(self.mon_info)

        srow.addSpacing(20)
        srow.addWidget(self._bold("Desk"))
        srow.addWidget(QLabel("W:"))
        self.desk_w = QDoubleSpinBox()
        if self._desk_unit == 'in':
            self.desk_w.setRange(4, 197)
        else:
            self.desk_w.setRange(10, 500)
        self.desk_w.setValue(self.state.env_desk_w)
        self.desk_w.setSuffix(f" {self._desk_unit}")
        self.desk_w.setFixedWidth(90)
        self.desk_w.setStyleSheet(SPIN)
        srow.addWidget(self.desk_w)

        srow.addWidget(QLabel("H:"))
        self.desk_h = QDoubleSpinBox()
        if self._desk_unit == 'in':
            self.desk_h.setRange(4, 197)
        else:
            self.desk_h.setRange(10, 500)
        self.desk_h.setValue(self.state.env_desk_h)
        self.desk_h.setSuffix(f" {self._desk_unit}")
        self.desk_h.setFixedWidth(90)
        self.desk_h.setStyleSheet(SPIN)
        srow.addWidget(self.desk_h)

        self.desk_unit_btn = QPushButton(self._desk_unit)
        self.desk_unit_btn.setStyleSheet(UNIT_BTN)
        self.desk_unit_btn.clicked.connect(self._toggle_desk_unit)
        srow.addWidget(self.desk_unit_btn)

        self.desk_ratio_lbl = QLabel("")
        self.desk_ratio_lbl.setStyleSheet("color:#555555; font-size:14px;")
        srow.addWidget(self.desk_ratio_lbl)
        self.desk_w.valueChanged.connect(self._update_desk_ratio)
        self.desk_h.valueChanged.connect(self._update_desk_ratio)
        self._update_desk_ratio()

        srow.addSpacing(10)
        upd = QPushButton("Update")
        upd.setStyleSheet(BTN)
        upd.clicked.connect(self._on_update)
        srow.addWidget(upd)
        srow.addStretch()
        root.addLayout(srow)

        # Canvas
        self.canvas = WorkspaceCanvas()
        self.canvas.changed.connect(self._on_changed)
        root.addWidget(self.canvas)

        # Bottom bar
        bot = QHBoxLayout()
        self.ws_lbl = QLabel()
        self.ws_lbl.setFont(QFont('Arial', 14))
        self.ws_lbl.setStyleSheet("color:#000000;")
        bot.addWidget(self.ws_lbl)
        bot.addStretch()

        scale_lbl = QLabel("Scale:")
        scale_lbl.setStyleSheet("color:#000000; font-size:14px;")
        bot.addWidget(scale_lbl)
        bot.addSpacing(4)
        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setRange(0.1, 5.0)
        self.scale_spin.setSingleStep(0.05)
        self.scale_spin.setDecimals(2)
        self.scale_spin.setSuffix(" ×")
        self.scale_spin.setValue(1.0)
        self.scale_spin.setFixedWidth(80)
        self.scale_spin.setStyleSheet(SPIN)
        self.scale_spin.valueChanged.connect(self._on_scale_changed)
        bot.addWidget(self.scale_spin)
        bot.addSpacing(16)

        reset_btn = QPushButton("Reset")
        reset_btn.setStyleSheet(BTN)
        reset_btn.clicked.connect(self._reset)
        bot.addWidget(reset_btn)
        bot.addSpacing(8)
        center_btn = QPushButton("Center")
        center_btn.setStyleSheet(BTN)
        center_btn.clicked.connect(self.canvas.center)
        bot.addWidget(center_btn)
        bot.addSpacing(8)
        fit_btn = QPushButton("Max Fit")
        fit_btn.setStyleSheet(BTN)
        fit_btn.clicked.connect(self.canvas.fit_max)
        bot.addWidget(fit_btn)
        bot.addSpacing(8)
        apply_btn = QPushButton("Apply")
        apply_btn.setStyleSheet(BTN)
        apply_btn.clicked.connect(self._apply)
        bot.addWidget(apply_btn)
        bot.addSpacing(24)

        self.origin_btn = QPushButton("Set Origin")
        self.origin_btn.setStyleSheet(BTN)
        self.origin_btn.clicked.connect(self._start_origin)
        bot.addWidget(self.origin_btn)
        bot.addSpacing(8)
        self.origin_lbl = QLabel(self._origin_text())
        self.origin_lbl.setFont(QFont('Arial', 14))
        self.origin_lbl.setStyleSheet("color: #555555;")
        bot.addWidget(self.origin_lbl)

        root.addLayout(bot)

        self._on_update()

    def _bold(self, text):
        lbl = QLabel(text)
        lbl.setFont(QFont('Arial', 15, QFont.Bold))
        lbl.setStyleSheet("color:#000000;")
        return lbl

    def _toggle_mon_unit(self):
        val = self.mon_size.value()
        if self._mon_unit == 'in':
            self._mon_unit = 'cm'
            self.mon_size.setRange(12, 305)
            self.mon_size.setValue(round(val * 2.54, 1))
            self.mon_size.setSuffix(" cm")
        else:
            self._mon_unit = 'in'
            self.mon_size.setRange(5, 120)
            self.mon_size.setValue(round(val / 2.54, 1))
            self.mon_size.setSuffix(" in")
        self.mon_unit_btn.setText(self._mon_unit)
        self._on_update()

    def _toggle_desk_unit(self):
        w = self.desk_w.value()
        h = self.desk_h.value()
        if self._desk_unit == 'cm':
            self._desk_unit = 'in'
            self.desk_w.setRange(4, 197)
            self.desk_h.setRange(4, 197)
            self.desk_w.setValue(round(w / 2.54, 2))
            self.desk_h.setValue(round(h / 2.54, 2))
            self.desk_w.setSuffix(" in")
            self.desk_h.setSuffix(" in")
        else:
            self._desk_unit = 'cm'
            self.desk_w.setRange(10, 500)
            self.desk_h.setRange(10, 500)
            self.desk_w.setValue(round(w * 2.54, 2))
            self.desk_h.setValue(round(h * 2.54, 2))
            self.desk_w.setSuffix(" cm")
            self.desk_h.setSuffix(" cm")
        self.desk_unit_btn.setText(self._desk_unit)
        self._on_update()

    def _mon_dims(self):
        diag = self.mon_size.value()
        if self._mon_unit == 'cm':
            diag = diag / 2.54
        rw, rh = self.ratio_cb.currentData()
        d = math.sqrt(rw**2 + rh**2)
        return diag * rw / d * 2.54, diag * rh / d * 2.54

    def _on_update(self):
        wc, hc = self._mon_dims()
        self.mon_info.setText(f"= {wc:.1f} × {hc:.1f} cm")
        dw = self.desk_w.value()
        dh = self.desk_h.value()
        if self._desk_unit == 'in':
            dw *= 2.54
            dh *= 2.54
        self.canvas.set_desk(dw, dh)
        self.canvas.set_monitor(wc, hc)

    def _reset(self):
        self.state.load_config()

        # Monitor unit
        self._mon_unit = self.state.env_mon_unit
        if self._mon_unit == 'cm':
            self.mon_size.setRange(12, 305)
        else:
            self.mon_size.setRange(5, 120)
        self.mon_size.setSuffix(f" {self._mon_unit}")
        self.mon_unit_btn.setText(self._mon_unit)
        self.mon_size.setValue(self.state.env_mon_size)
        self.ratio_cb.setCurrentIndex(self.state.env_mon_ratio_idx)

        # Desk unit
        self._desk_unit = self.state.env_desk_unit
        if self._desk_unit == 'in':
            self.desk_w.setRange(4, 197)
            self.desk_h.setRange(4, 197)
        else:
            self.desk_w.setRange(10, 500)
            self.desk_h.setRange(10, 500)
        self.desk_w.setSuffix(f" {self._desk_unit}")
        self.desk_h.setSuffix(f" {self._desk_unit}")
        self.desk_unit_btn.setText(self._desk_unit)
        self.desk_w.setValue(self.state.env_desk_w)
        self.desk_h.setValue(self.state.env_desk_h)

        self._on_update()
        self._load_task_env()

    def _update_desk_ratio(self):
        h = self.desk_h.value()
        if h > 0:
            self.desk_ratio_lbl.setText(f"= {self.desk_w.value() / h:.2f} : 1")

    def _on_scale_changed(self, val):
        self.canvas.set_scale(val)

    def _on_changed(self, y_min, y_max, z_min, z_max):
        self._ws = (y_min, y_max, z_min, z_max)
        self.ws_lbl.setText(
            f"Workspace:   Y  {y_min:.1f} – {y_max:.1f} cm     "
            f"Z  {z_min:.1f} – {z_max:.1f} cm"
        )
        if self.canvas._real_mon_w > 0:
            scale = self.canvas._rw / self.canvas._real_mon_w
            self.scale_spin.blockSignals(True)
            self.scale_spin.setValue(scale)
            self.scale_spin.blockSignals(False)

    def _apply(self):
        y_min, y_max, z_min, z_max = self._ws
        self.state.WORKSPACE_Y_MIN = y_min
        self.state.WORKSPACE_Y_MAX = y_max
        self.state.WORKSPACE_Z_MIN = z_min
        self.state.WORKSPACE_Z_MAX = z_max
        self.state.env_mon_size      = self.mon_size.value()
        self.state.env_mon_unit      = self._mon_unit
        self.state.env_mon_ratio_idx = self.ratio_cb.currentIndex()
        self.state.env_desk_w        = self.desk_w.value()
        self.state.env_desk_h        = self.desk_h.value()
        self.state.env_desk_unit     = self._desk_unit
        self.state.env_rect_x        = self.canvas._rx
        self.state.env_rect_y        = self.canvas._ry
        self.state.env_rect_w        = self.canvas._rw
        self.state.env_rect_h        = self.canvas._rh
        self.state.save_task_rect(self.state.task_type)
        task_name = self.state.task_type.replace('_', ' ').title() + ' Task'
        QMessageBox.information(self, "Saved", f"{task_name} environment settings saved.")

    def _tick(self):
        if (self.state.sensor_x_offset == 0.0 and
                self.state.sensor_y_offset == 0.0 and
                self.state.sensor_z_offset == 0.0):
            self.canvas.update_cursor(0, 0, False)
            self.canvas.set_source(None, None)
            return
        src_y = -self.state.sensor_y_offset
        src_z = -self.state.sensor_z_offset
        self.canvas.set_source(src_y, src_z)
        s1 = self.liberty.get_sensor(1)
        if s1 is None:
            self.canvas.update_cursor(0, 0, False)
            return
        y = s1.y * 2.54 - self.state.sensor_y_offset
        z = s1.z * 2.54 - self.state.sensor_z_offset
        active = (0 <= y <= self.canvas._desk_w and 0 <= z <= self.canvas._desk_h)
        self.canvas.update_cursor(y, z, active)

    def _origin_text(self):
        x = self.state.sensor_x_offset
        y = self.state.sensor_y_offset
        z = self.state.sensor_z_offset
        if x == 0.0 and y == 0.0 and z == 0.0:
            return "Origin: not set"
        return f"Origin: X {x:.1f} cm, Y {y:.1f} cm, Z {z:.1f} cm"

    def _start_origin(self):
        if self._origin_timer.isActive():
            return
        self._origin_countdown = 3
        self.origin_btn.setEnabled(False)
        self.origin_lbl.setText("3...")
        self._origin_timer.start(1000)

    def _origin_tick(self):
        self._origin_countdown -= 1
        if self._origin_countdown > 0:
            self.origin_lbl.setText(f"{self._origin_countdown}...")
            return
        self._origin_timer.stop()
        self.origin_btn.setEnabled(True)
        s = self.liberty.get_sensor(1)
        if s is None:
            self.origin_lbl.setText("No sensor data")
            return
        self.state.sensor_x_offset = s.x * 2.54
        self.state.sensor_y_offset = s.y * 2.54
        self.state.sensor_z_offset = s.z * 2.54
        self.state.save_config()
        def _arpeggio():
            for freq, dur in [(523, 80), (659, 80), (784, 80), (1047, 280)]:
                winsound.Beep(freq, dur)
        threading.Thread(target=_arpeggio, daemon=True).start()
        self.origin_lbl.setText(self._origin_text())
