import threading
import winsound
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QComboBox, QPushButton, QFrame, QScrollArea)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

BTN = """
QPushButton {
    background-color: #888888; color: white; border: none;
    border-radius: 5px; font-size: 15px; padding: 6px 14px;
}
QPushButton:hover   { background-color: #999999; }
QPushButton:pressed { background-color: #777777; }
"""
BTN_SM = BTN.replace("font-size: 15px; padding: 6px 14px;",
                      "font-size: 13px; padding: 4px 10px;")
COMBO = (
    "QComboBox { background:#ffffff; color:#000000; border:1px solid #aaaaaa;"
    " border-radius:4px; padding:2px 8px; font-size:14px; }"
    "QComboBox::drop-down { border:none; }"
    "QComboBox QAbstractItemView { background:#ffffff; color:#000000;"
    " selection-background-color:#b0c8e0; }"
)

MODES = [
    ('Cursor   (Mode 0)',  0),
    ('MCP      (Mode 1)',  1),
    ('Wrist    (Mode 2)',  2),
    ('Full Arm (Mode 3)',  3),
]
SENSORS = [('S1', 1), ('S2', 2), ('S3', 3), ('S4', 4)]

# Wrist landmarks: (key, label, side)
WRIST_LANDMARKS = ['MCP', 'RSP', 'USP', 'LE', 'ME']
WRIST_LM_FULL = {
    'MCP': 'MCP (metacarpal)',
    'RSP': 'RSP (radial styloid)',
    'USP': 'USP (ulnar styloid)',
    'LE':  'LE  (lateral epicondyle)',
    'ME':  'ME  (medial epicondyle)',
}


class DigitizationScreen(QWidget):
    def __init__(self, state, liberty, main_window):
        super().__init__()
        self.setObjectName('DigitizationScreen')
        self.setStyleSheet('#DigitizationScreen { background-color: #f0f0f0; }')
        self.state   = state
        self.liberty = liberty
        self.mw      = main_window

        # Single countdown timer shared across all record buttons
        self._cd_value = 0
        self._cd_fn    = None   # callable: what to do when countdown ends
        self._cd_lbl   = None   # QLabel to update with "3..."
        self._cd_btn   = None   # QPushButton to disable during countdown
        self._cd_timer = QTimer(self)
        self._cd_timer.timeout.connect(self._tick_cd)

        # Wrist mode: R-side temp offsets in S2 frame before finalization
        self._wrist_R_tmp = {}  # {landmark: [x,y,z]}

        # Live update references (rebuilt per mode)
        self._live_rows  = {}   # sensor_n -> QLabel
        self._mcp_pos_lbls = {}  # 'right'/'left' -> QLabel

        self._live_timer = QTimer(self)
        self._live_timer.timeout.connect(self._update_live)

        self._build()

    def showEvent(self, e):
        self._live_timer.start(125)
        super().showEvent(e)

    def hideEvent(self, e):
        self._live_timer.stop()
        self._cd_timer.stop()
        super().hideEvent(e)

    # ── top-level layout ──────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 16)
        root.setSpacing(10)

        # Back + title
        top = QHBoxLayout()
        back = QPushButton("← Back")
        back.setStyleSheet(BTN)
        back.clicked.connect(lambda: self.mw.show_screen('menu'))
        top.addWidget(back)
        top.addStretch()
        title = QLabel("Digitization")
        title.setFont(QFont('Arial', 22, QFont.Bold))
        title.setStyleSheet("color: #000000;")
        top.addWidget(title)
        top.addStretch()
        root.addLayout(top)
        root.addWidget(self._sep())

        # Mode selector
        mode_row = QHBoxLayout()
        mode_row.addWidget(self._bold("Mode:"))
        mode_row.addSpacing(8)
        self.mode_cb = QComboBox()
        self.mode_cb.setStyleSheet(COMBO)
        self.mode_cb.setFixedWidth(200)
        for label, val in MODES:
            self.mode_cb.addItem(label, val)
            if val == self.state.dig_mode:
                self.mode_cb.setCurrentIndex(self.mode_cb.count() - 1)
        self.mode_cb.currentIndexChanged.connect(self._on_mode_changed)
        mode_row.addWidget(self.mode_cb)
        mode_row.addStretch()
        root.addLayout(mode_row)
        root.addWidget(self._sep())

        # Scrollable content area (rebuilt on mode change)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setStyleSheet("background: transparent;")
        root.addWidget(self._scroll)

        self._rebuild_content()

    def _rebuild_content(self):
        self._live_rows.clear()
        self._mcp_pos_lbls.clear()

        page = QWidget()
        page.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        mode = self.state.dig_mode
        if mode == 0:
            self._build_cursor(lay)
        elif mode == 1:
            self._build_mcp(lay)
        elif mode == 2:
            self._build_wrist(lay)
        else:
            lay.addWidget(QLabel("Mode not yet implemented."))

        lay.addStretch()
        self._scroll.setWidget(page)

    def _on_mode_changed(self):
        self.state.dig_mode = self.mode_cb.currentData()
        self.state.save_config()
        self._rebuild_content()

    # ── MODE 0: Cursor ────────────────────────────────────────

    def _build_cursor(self, lay):
        lay.addWidget(self._bold("Sensor Assignment"))
        row = QHBoxLayout()
        for label, key in [("Right Hand:", 'right'), ("Left Hand:", 'left')]:
            l = QLabel(label)
            l.setFont(QFont('Arial', 14))
            l.setStyleSheet("color: #333333;")
            row.addWidget(l)
            default = (self.state.dig_sensor_right if key == 'right'
                       else self.state.dig_sensor_left)
            cb = self._sensor_cb(default)
            cb.currentIndexChanged.connect(
                lambda _, k=key, c=cb: self._save_cursor_assign(k, c))
            row.addWidget(cb)
            row.addSpacing(20)
        row.addStretch()
        lay.addLayout(row)

    def _save_cursor_assign(self, side, cb):
        if side == 'right':
            self.state.dig_sensor_right = cb.currentData()
        else:
            self.state.dig_sensor_left = cb.currentData()
        self.state.save_config()

    # ── MODE 1: MCP ───────────────────────────────────────────

    def _build_mcp(self, lay):
        # Sensor assignment
        lay.addWidget(self._bold("Sensor Assignment"))
        arow = QHBoxLayout()
        for label, key in [("Right Hand:", 'right'),
                            ("Left Hand:",  'left'),
                            ("Pointer:",    'ptr')]:
            l = QLabel(label)
            l.setFont(QFont('Arial', 14))
            l.setStyleSheet("color: #333333;")
            arow.addWidget(l)
            default = {'right': self.state.dig_sensor_right,
                       'left':  self.state.dig_sensor_left,
                       'ptr':   self.state.mcp_sensor_pointer}[key]
            cb = self._sensor_cb(default)
            cb.currentIndexChanged.connect(
                lambda _, k=key, c=cb: self._save_mcp_assign(k, c))
            arow.addWidget(cb)
            arow.addSpacing(16)
        arow.addStretch()
        lay.addLayout(arow)
        lay.addWidget(self._sep())

        # Live sensor data
        lay.addWidget(self._bold("Live Sensor Data"))
        for label, attr in [("Right Hand", 'dig_sensor_right'),
                             ("Left Hand",  'dig_sensor_left'),
                             ("Pointer",    'mcp_sensor_pointer')]:
            n = getattr(self.state, attr)
            lbl = self._live_row_widget(lay, label, n)
            self._live_rows[n] = lbl
        lay.addWidget(self._sep())

        # Record buttons
        lay.addWidget(self._bold("Record MCP Positions"))
        for side, attr in [('right', 'mcp_offset_right'),
                            ('left',  'mcp_offset_left')]:
            offset = getattr(self.state, attr)
            rrow = QHBoxLayout()
            btn = QPushButton(f"Record {'Right' if side=='right' else 'Left'} MCP")
            btn.setStyleSheet(BTN)
            btn.setFixedWidth(220)
            lbl = QLabel(self._offset_text(offset))
            lbl.setFont(QFont('Arial', 14))
            lbl.setStyleSheet("color: #555555;")
            btn.clicked.connect(lambda _, s=side, b=btn, l=lbl: self._start_cd(
                b, l, lambda s=s, l=l: self._record_mcp(s, l)))
            rrow.addWidget(btn)
            rrow.addSpacing(10)
            rrow.addWidget(lbl)
            rrow.addStretch()
            lay.addLayout(rrow)

        lay.addSpacing(6)

        # Live MCP positions
        lay.addWidget(self._bold("Live MCP Position"))
        for side in ('right', 'left'):
            mrow = QHBoxLayout()
            name_lbl = QLabel(f"{'Right' if side=='right' else 'Left'} MCP:")
            name_lbl.setFixedWidth(110)
            name_lbl.setFont(QFont('Arial', 14))
            name_lbl.setStyleSheet("color: #333333;")
            pos_lbl = QLabel("—")
            pos_lbl.setFont(QFont('Arial', 14))
            pos_lbl.setStyleSheet("color: #888888;")
            mrow.addWidget(name_lbl)
            mrow.addWidget(pos_lbl)
            mrow.addStretch()
            lay.addLayout(mrow)
            self._mcp_pos_lbls[side] = pos_lbl

        lay.addWidget(self._sep())

        # Clear buttons
        crow = QHBoxLayout()
        for label, fn in [("Clear Right", lambda: self._clear_mcp('right')),
                          ("Clear Left",  lambda: self._clear_mcp('left')),
                          ("Clear All",   self._clear_mcp_all)]:
            b = QPushButton(label)
            b.setStyleSheet(BTN)
            b.clicked.connect(fn)
            crow.addWidget(b)
            crow.addSpacing(8)
        crow.addStretch()
        lay.addLayout(crow)

    def _save_mcp_assign(self, key, cb):
        val = cb.currentData()
        if key == 'right': self.state.dig_sensor_right = val
        elif key == 'left': self.state.dig_sensor_left = val
        elif key == 'ptr':  self.state.mcp_sensor_pointer = val
        self.state.save_config()

    def _record_mcp(self, side, status_lbl):
        from digitizer import compute_offset
        hand_n = (self.state.dig_sensor_right if side == 'right'
                  else self.state.dig_sensor_left)
        ptr_n  = self.state.mcp_sensor_pointer
        hand_s = self.liberty.get_sensor(hand_n)
        ptr_s  = self.liberty.get_sensor(ptr_n)
        if hand_s is None or ptr_s is None:
            status_lbl.setText("No sensor data — try again")
            return
        offset = compute_offset(hand_s, ptr_s)
        if side == 'right':
            self.state.mcp_offset_right = offset
        else:
            self.state.mcp_offset_left = offset
        self.state.save_config()
        threading.Thread(target=winsound.Beep, args=(880, 120), daemon=True).start()
        status_lbl.setText(self._offset_text(offset))

    def _clear_mcp(self, side):
        if side == 'right': self.state.mcp_offset_right = None
        else:               self.state.mcp_offset_left  = None
        self.state.save_config()
        self._rebuild_content()

    def _clear_mcp_all(self):
        self.state.mcp_offset_right = None
        self.state.mcp_offset_left  = None
        self.state.save_config()
        self._rebuild_content()

    # ── MODE 2: Wrist ─────────────────────────────────────────

    def _build_wrist(self, lay):
        # Sensor assignment
        lay.addWidget(self._bold("Sensor Assignment"))
        arow = QHBoxLayout()
        arow.setSpacing(10)
        assigns = [
            ("L.Hand:",        'wrist_sensor_L_hand'),
            ("R.Hand:",        'wrist_sensor_R_hand'),
            ("L.Forearm:",     'wrist_sensor_L_forearm'),
            ("R.Ptr→Forearm:", 'wrist_sensor_R_ptr'),
        ]
        for label, attr in assigns:
            l = QLabel(label)
            l.setFont(QFont('Arial', 13))
            l.setStyleSheet("color: #333333;")
            arow.addWidget(l)
            cb = self._sensor_cb(getattr(self.state, attr))
            cb.currentIndexChanged.connect(
                lambda _, a=attr, c=cb: self._save_wrist_assign(a, c))
            arow.addWidget(cb)
            arow.addSpacing(8)
        arow.addStretch()
        lay.addLayout(arow)
        lay.addWidget(self._sep())

        # Live sensor data
        lay.addWidget(self._bold("Live Sensor Data"))
        live_cfg = [
            ("L.Hand",     'wrist_sensor_L_hand'),
            ("R.Hand",     'wrist_sensor_R_hand'),
            ("L.Forearm",  'wrist_sensor_L_forearm'),
            ("R.Ptr/FA",   'wrist_sensor_R_ptr'),
        ]
        for label, attr in live_cfg:
            n = getattr(self.state, attr)
            lbl = self._live_row_widget(lay, label, n)
            self._live_rows[n] = lbl
        lay.addWidget(self._sep())

        # Landmarks — left side
        lay.addWidget(self._bold("Left Side Landmarks"))
        lay.addWidget(self._note("Pointer → landmark, press Record. L.MCP stored in L.Hand frame; others in L.Forearm frame."))
        for lm in WRIST_LANDMARKS:
            stored = getattr(self.state, f'wrist_L_{lm}')
            rrow = QHBoxLayout()
            lbl_name = QLabel(f"{WRIST_LM_FULL[lm]}:")
            lbl_name.setFixedWidth(230)
            lbl_name.setFont(QFont('Arial', 13))
            lbl_name.setStyleSheet("color: #333333;")
            btn = QPushButton("Record")
            btn.setStyleSheet(BTN_SM)
            btn.setFixedWidth(90)
            status = QLabel(self._offset_text(stored))
            status.setFont(QFont('Arial', 13))
            status.setStyleSheet("color: #555555;")
            btn.clicked.connect(lambda _, l=lm, b=btn, s=status:
                                 self._start_cd(b, s, lambda l=l, s=s: self._record_wrist_L(l, s)))
            rrow.addWidget(lbl_name)
            rrow.addWidget(btn)
            rrow.addSpacing(8)
            rrow.addWidget(status)
            rrow.addStretch()
            lay.addLayout(rrow)

        lay.addWidget(self._sep())

        # Landmarks — right side
        lay.addWidget(self._bold("Right Side Landmarks"))
        lay.addWidget(self._note("Use R.Ptr (S4) as pointer. RSP/USP/LE/ME stored in R.Hand frame until 'Finalize'."))
        for lm in WRIST_LANDMARKS:
            stored = getattr(self.state, f'wrist_R_{lm}')
            tmp    = self._wrist_R_tmp.get(lm)
            rrow = QHBoxLayout()
            lbl_name = QLabel(f"{WRIST_LM_FULL[lm]}:")
            lbl_name.setFixedWidth(230)
            lbl_name.setFont(QFont('Arial', 13))
            lbl_name.setStyleSheet("color: #333333;")
            btn = QPushButton("Record")
            btn.setStyleSheet(BTN_SM)
            btn.setFixedWidth(90)
            if lm == 'MCP':
                disp = stored
            else:
                disp = stored if stored is not None else tmp
            status = QLabel(self._offset_text_wrist_R(lm, stored, tmp))
            status.setFont(QFont('Arial', 13))
            status.setStyleSheet("color: #555555;")
            btn.clicked.connect(lambda _, l=lm, b=btn, s=status:
                                 self._start_cd(b, s, lambda l=l, s=s: self._record_wrist_R(l, s)))
            rrow.addWidget(lbl_name)
            rrow.addWidget(btn)
            rrow.addSpacing(8)
            rrow.addWidget(status)
            rrow.addStretch()
            lay.addLayout(rrow)

        # Finalize button
        lay.addSpacing(6)
        fin_row = QHBoxLayout()
        self._finalize_btn = QPushButton("Finalize Right Forearm")
        self._finalize_btn.setStyleSheet(BTN)
        self._finalize_btn.clicked.connect(self._finalize_wrist_R)
        self._finalize_lbl = QLabel(self._finalize_status())
        self._finalize_lbl.setFont(QFont('Arial', 13))
        self._finalize_lbl.setStyleSheet("color: #555555;")
        fin_row.addWidget(self._finalize_btn)
        fin_row.addSpacing(10)
        fin_row.addWidget(self._finalize_lbl)
        fin_row.addStretch()
        lay.addLayout(fin_row)

        lay.addWidget(self._sep())

        # Clear
        crow = QHBoxLayout()
        for label, fn in [("Clear Left",  self._clear_wrist_L),
                          ("Clear Right", self._clear_wrist_R),
                          ("Clear All",   self._clear_wrist_all)]:
            b = QPushButton(label)
            b.setStyleSheet(BTN)
            b.clicked.connect(fn)
            crow.addWidget(b)
            crow.addSpacing(8)
        crow.addStretch()
        lay.addLayout(crow)

    def _save_wrist_assign(self, attr, cb):
        setattr(self.state, attr, cb.currentData())
        self.state.save_config()

    def _record_wrist_L(self, lm, status_lbl):
        from digitizer import compute_offset
        ptr_n  = self.state.wrist_sensor_R_ptr
        ptr_s  = self.liberty.get_sensor(ptr_n)
        if lm == 'MCP':
            hand_n = self.state.wrist_sensor_L_hand
            hand_s = self.liberty.get_sensor(hand_n)
            if hand_s is None or ptr_s is None:
                status_lbl.setText("No sensor data — try again")
                return
            offset = compute_offset(hand_s, ptr_s)
            self.state.wrist_L_MCP = offset
        else:
            fore_n = self.state.wrist_sensor_L_forearm
            fore_s = self.liberty.get_sensor(fore_n)
            if fore_s is None or ptr_s is None:
                status_lbl.setText("No sensor data — try again")
                return
            offset = compute_offset(fore_s, ptr_s)
            setattr(self.state, f'wrist_L_{lm}', offset)
        self.state.save_config()
        threading.Thread(target=winsound.Beep, args=(880, 120), daemon=True).start()
        status_lbl.setText(self._offset_text(offset))

    def _record_wrist_R(self, lm, status_lbl):
        from digitizer import compute_offset
        ptr_n  = self.state.wrist_sensor_R_ptr
        hand_n = self.state.wrist_sensor_R_hand
        ptr_s  = self.liberty.get_sensor(ptr_n)
        hand_s = self.liberty.get_sensor(hand_n)
        if hand_s is None or ptr_s is None:
            status_lbl.setText("No sensor data — try again")
            return
        offset = compute_offset(hand_s, ptr_s)
        if lm == 'MCP':
            self.state.wrist_R_MCP = offset
            self.state.save_config()
        else:
            self._wrist_R_tmp[lm] = offset  # temp: in S2 frame until finalization
        threading.Thread(target=winsound.Beep, args=(880, 120), daemon=True).start()
        status_lbl.setText(self._offset_text_wrist_R(
            lm, getattr(self.state, f'wrist_R_{lm}'), self._wrist_R_tmp.get(lm)))

    def _finalize_wrist_R(self):
        from digitizer import finalize_forearm
        needed = {lm: self._wrist_R_tmp.get(lm) for lm in ['RSP','USP','LE','ME']}
        if any(v is None for v in needed.values()):
            self._finalize_lbl.setText("Record RSP/USP/LE/ME first")
            return
        hand_n = self.state.wrist_sensor_R_hand
        fore_n = self.state.wrist_sensor_R_ptr
        hand_s = self.liberty.get_sensor(hand_n)
        fore_s = self.liberty.get_sensor(fore_n)
        if hand_s is None or fore_s is None:
            self._finalize_lbl.setText("No sensor data — try again")
            return
        converted = finalize_forearm(hand_s, fore_s, needed)
        for lm, off in converted.items():
            setattr(self.state, f'wrist_R_{lm}', off)
        self._wrist_R_tmp.clear()
        self.state.save_config()
        threading.Thread(target=winsound.Beep,
                         args=(880, 120), daemon=True).start()
        self._finalize_lbl.setText("✓  RSP/USP/LE/ME converted to R.Forearm frame")
        self._rebuild_content()

    def _finalize_status(self):
        done = all(getattr(self.state, f'wrist_R_{lm}') is not None
                   for lm in ['RSP','USP','LE','ME'])
        if done:
            return "✓  Finalized"
        tmp_done = all(self._wrist_R_tmp.get(lm) is not None
                       for lm in ['RSP','USP','LE','ME'])
        if tmp_done:
            return "Ready — place S4 on R.Forearm then press"
        return "Record RSP/USP/LE/ME first"

    def _offset_text_wrist_R(self, lm, stored, tmp):
        if lm == 'MCP':
            return self._offset_text(stored)
        if stored is not None:
            return f"✓  ({stored[0]:.2f}, {stored[1]:.2f}, {stored[2]:.2f}) cm  [R.Forearm frame]"
        if tmp is not None:
            return f"(tmp)  ({tmp[0]:.2f}, {tmp[1]:.2f}, {tmp[2]:.2f}) cm  [R.Hand frame — needs Finalize]"
        return "Not recorded"

    def _clear_wrist_L(self):
        for lm in WRIST_LANDMARKS:
            setattr(self.state, f'wrist_L_{lm}', None)
        self.state.save_config()
        self._rebuild_content()

    def _clear_wrist_R(self):
        for lm in WRIST_LANDMARKS:
            setattr(self.state, f'wrist_R_{lm}', None)
        self._wrist_R_tmp.clear()
        self.state.save_config()
        self._rebuild_content()

    def _clear_wrist_all(self):
        self._clear_wrist_L()
        self._clear_wrist_R()

    # ── countdown ─────────────────────────────────────────────

    def _start_cd(self, btn, lbl, fn):
        if self._cd_timer.isActive():
            return
        self._cd_value = 3
        self._cd_fn    = fn
        self._cd_lbl   = lbl
        self._cd_btn   = btn
        btn.setEnabled(False)
        lbl.setText("3...")
        self._cd_timer.start(1000)

    def _tick_cd(self):
        self._cd_value -= 1
        if self._cd_value > 0:
            self._cd_lbl.setText(f"{self._cd_value}...")
            return
        self._cd_timer.stop()
        if self._cd_btn:
            self._cd_btn.setEnabled(True)
        fn = self._cd_fn
        self._cd_fn = self._cd_lbl = self._cd_btn = None
        if fn:
            fn()

    # ── live update ───────────────────────────────────────────

    def _update_live(self):
        for sensor_n, lbl in list(self._live_rows.items()):
            self._refresh_sensor_lbl(lbl, sensor_n)

        # MCP mode: live MCP positions
        if self.state.dig_mode == 1:
            self._update_mcp_positions()

    def _refresh_sensor_lbl(self, lbl, sensor_n):
        s      = self.liberty.get_sensor(sensor_n)
        active = self.liberty.is_sensor_active(sensor_n)
        if s is None or not active:
            lbl.setText("● INACTIVE")
            lbl.setStyleSheet("color: #dc3232;")
        else:
            y = s.y * 2.54 - self.state.sensor_y_offset
            z = s.z * 2.54 - self.state.sensor_z_offset
            x = s.x * 2.54
            lbl.setText(f"● ACTIVE    Y: {y:.1f}   Z: {z:.1f}   X: {x:.1f} cm")
            lbl.setStyleSheet("color: #228822;")

    def _update_mcp_positions(self):
        from digitizer import track_mcp
        for side, attr, sensor_attr in [
            ('right', 'mcp_offset_right', 'dig_sensor_right'),
            ('left',  'mcp_offset_left',  'dig_sensor_left'),
        ]:
            lbl = self._mcp_pos_lbls.get(side)
            if lbl is None:
                continue
            offset = getattr(self.state, attr)
            if offset is None:
                lbl.setText("—")
                lbl.setStyleSheet("color: #888888;")
                continue
            n = getattr(self.state, sensor_attr)
            s = self.liberty.get_sensor(n)
            if s is None or not self.liberty.is_sensor_active(n):
                lbl.setText("Sensor inactive")
                lbl.setStyleSheet("color: #dc3232;")
                continue
            pos = track_mcp(s, offset)
            y = pos[1] - self.state.sensor_y_offset
            z = pos[2] - self.state.sensor_z_offset
            lbl.setText(f"Y: {y:.1f}   Z: {z:.1f}   X: {pos[0]:.1f} cm")
            lbl.setStyleSheet("color: #228822;")

    # ── helpers ───────────────────────────────────────────────

    def _sep(self):
        f = QFrame()
        f.setFrameShape(QFrame.HLine)
        f.setStyleSheet("color: #cccccc;")
        return f

    def _bold(self, text):
        l = QLabel(text)
        l.setFont(QFont('Arial', 16, QFont.Bold))
        l.setStyleSheet("color: #000000;")
        return l

    def _note(self, text):
        l = QLabel(text)
        l.setFont(QFont('Arial', 12))
        l.setStyleSheet("color: #777777;")
        l.setWordWrap(True)
        return l

    def _sensor_cb(self, default_n):
        cb = QComboBox()
        cb.setStyleSheet(COMBO)
        cb.setFixedWidth(70)
        for label, n in SENSORS:
            cb.addItem(label, n)
            if n == default_n:
                cb.setCurrentIndex(cb.count() - 1)
        return cb

    def _live_row_widget(self, lay, role, sensor_n):
        row = QHBoxLayout()
        rl = QLabel(f"{role} (S{sensor_n}):")
        rl.setFixedWidth(160)
        rl.setFont(QFont('Arial', 14))
        rl.setStyleSheet("color: #333333;")
        dl = QLabel("—")
        dl.setFont(QFont('Arial', 14))
        dl.setStyleSheet("color: #888888;")
        row.addWidget(rl)
        row.addWidget(dl)
        row.addStretch()
        lay.addLayout(row)
        return dl

    def _offset_text(self, offset):
        if offset is None:
            return "Not recorded"
        return f"✓   ({offset[0]:.2f},  {offset[1]:.2f},  {offset[2]:.2f}) cm"
