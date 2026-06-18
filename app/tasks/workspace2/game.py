import math
import os
import time
from datetime import datetime
from PyQt5.QtWidgets import QWidget, QPushButton, QVBoxLayout, QLabel, QApplication
from PyQt5.QtCore import Qt, QTimer, QRect, QPoint
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPolygon

START_CIRCLE_R = 2.5    # cm
START_OFFSET_Z = 20.0   # cm forward from trunk center


def _dist_angle(hand, trunk):
    """Unsigned distance and angle of hand from trunk (angle always >= 0)."""
    dy = hand[0] - trunk[0]
    dz = hand[1] - trunk[1]
    return math.sqrt(dy * dy + dz * dz), math.degrees(math.atan2(abs(dy), dz))


def _signed_angle(hand, trunk):
    """Signed angle: 0° = straight ahead, + = right, - = left."""
    dy = hand[0] - trunk[0]
    dz = hand[1] - trunk[1]
    return math.degrees(math.atan2(dy, dz))


# ── Pause overlay ─────────────────────────────────────────────────────────────

class _PauseOverlay(QWidget):
    def __init__(self, game):
        super().__init__(game)
        self._game = game
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.hide()
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(20)

        title = QLabel("Paused")
        title.setFont(QFont('Arial', 28, QFont.Bold))
        title.setStyleSheet("color: white;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        layout.addSpacing(12)

        hint = QLabel("ESC — resume    |    Enter — exit to menu")
        hint.setFont(QFont('Arial', 13))
        hint.setStyleSheet("color: #aaaaaa;")
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)

        layout.addSpacing(8)

        for text, slot in [("Resume", self._game._resume),
                            ("Screenshot", self._game._take_screenshot),
                            ("Main Menu", self._game._exit_to_menu)]:
            btn = QPushButton(text)
            btn.setFont(QFont('Arial', 18))
            btn.setFixedSize(220, 58)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #2a2a2a;
                    color: white;
                    border: 2px solid #555555;
                    border-radius: 8px;
                }
                QPushButton:hover {
                    background-color: #444444;
                    border-color: #aaaaaa;
                }
                QPushButton:pressed {
                    background-color: #111111;
                }
            """)
            btn.clicked.connect(slot)
            layout.addWidget(btn, alignment=Qt.AlignCenter)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 170))


# ── Game screen ───────────────────────────────────────────────────────────────

class GameScreen(QWidget):
    def __init__(self, state, liberty, main_window):
        super().__init__()
        self.state   = state
        self.liberty = liberty
        self.mw      = main_window
        self.setStyleSheet("background-color: #000000;")
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self._mouse_px     = None
        self._mouse_hand   = 'right'
        self._cursor_hidden = False

        self._ws = QRect()
        self._pos_right  = None
        self._pos_left   = None
        self._pos_trunk  = None

        self._paused = False
        self._overlay = _PauseOverlay(self)

        # Persists across trials within one game session; cleared on showEvent
        self._results      = {}   # side ('right'/'left') -> stat dict
        self._show_overlay = False

        self._phase            = 'wait_start'
        self._active_side      = None
        self._max_dist         = None
        self._max_angle        = None
        self._max_signed_angle = None

        # Sweep state
        self._sweep_r         = None
        self._sweep_angle     = None
        self._sweep_waypoints = []
        self._sweep_wp_idx    = 0
        self._sweep_waiting   = False

        # Range tracking: angle bin (int degree) -> max distance reached
        self._range_bins   = {}
        self._trajectory   = []  # [(y_cm, z_cm), ...] actual hand path during sweep

        # End-of-trial stats (overall | contra | ipsi)
        self._stat_avg_dist      = None
        self._stat_covered_angle = None
        self._stat_area          = None
        self._stat_contra_avg    = None
        self._stat_contra_angle  = None
        self._stat_contra_area   = None
        self._stat_ipsi_avg      = None
        self._stat_ipsi_angle    = None
        self._stat_ipsi_area     = None

        self._last_tick = time.perf_counter()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def _hide_cursor(self):
        if not self._cursor_hidden:
            QApplication.setOverrideCursor(Qt.BlankCursor)
            self._cursor_hidden = True

    def _show_cursor(self):
        if self._cursor_hidden:
            QApplication.restoreOverrideCursor()
            self._cursor_hidden = False

    def showEvent(self, e):
        timer_ms = max(1, round(1000 / self.state.sample_rate_hz))
        self._timer.start(timer_ms)
        self._results = {}
        self._reset()
        self._hide_cursor()
        super().showEvent(e)

    def hideEvent(self, e):
        self._timer.stop()
        self._overlay.hide()
        self._paused = False
        self._show_cursor()
        super().hideEvent(e)

    def resizeEvent(self, e):
        self._overlay.setGeometry(self.rect())
        super().resizeEvent(e)

    def _reset(self):
        self._phase            = 'wait_start'
        self._active_side      = None
        self._max_dist         = None
        self._max_angle        = None
        self._max_signed_angle = None
        self._sweep_r          = None
        self._sweep_angle      = None
        self._sweep_waypoints  = []
        self._sweep_wp_idx     = 0
        self._sweep_waiting    = False
        self._range_bins       = {}
        self._trajectory       = []
        self._show_overlay     = False
        self._stat_avg_dist      = None
        self._stat_covered_angle = None
        self._stat_area          = None
        self._stat_contra_avg    = None
        self._stat_contra_angle  = None
        self._stat_contra_area   = None
        self._stat_ipsi_avg      = None
        self._stat_ipsi_angle    = None
        self._stat_ipsi_area     = None
        self._last_tick          = time.perf_counter()

    # ── key events ────────────────────────────────────────────

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            if not self._paused:
                self._pause()
            else:
                self._resume()
        elif e.key() == Qt.Key_Return or e.key() == Qt.Key_Enter:
            if self._paused:
                self._exit_to_menu()
            elif self._phase == 'done':
                opp = 'left' if self._active_side == 'right' else 'right'
                if opp in self._results:
                    self._show_overlay = not self._show_overlay
                    self.update()
        elif e.key() == Qt.Key_S and self.liberty.use_mouse and not self._paused:
            self._mouse_hand = 'left' if self._mouse_hand == 'right' else 'right'
        elif e.key() == Qt.Key_Space and not self._paused:
            if e.modifiers() & Qt.ShiftModifier and self._phase == 'wait_log_start':
                self._phase = 'wait_start'
                self.update()
            elif self._phase == 'done':
                self._reset()
            else:
                self._on_space()

    def mouseMoveEvent(self, e):
        self._mouse_px = (e.x(), e.y())

    def _pause(self):
        self._paused = True
        self._timer.stop()
        self._show_cursor()
        self._overlay.setGeometry(self.rect())
        self._overlay.show()
        self._overlay.raise_()

    def _resume(self):
        self._paused = False
        self._overlay.hide()
        self._hide_cursor()
        timer_ms = max(1, round(1000 / self.state.sample_rate_hz))
        self._timer.start(timer_ms)

    def _take_screenshot(self):
        self._overlay.hide()
        pixmap = self.grab()
        self._overlay.show()

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        pid = self.state.participant_id or 'unknown'
        base = self.state.data_dir if self.state.data_dir else os.path.expanduser('~')
        folder = os.path.join(base, pid)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f'screenshot_{timestamp}.png')
        pixmap.save(path)

    def _exit_to_menu(self):
        self._paused = False
        self._overlay.hide()
        self._timer.stop()
        self._show_cursor()
        self.mw.show_screen('menu')

    def _on_space(self):
        if self._phase == 'wait_start':
            side = self._hand_in_start_circle()
            if side is None:
                return
            self._active_side      = side
            self._max_dist         = None
            self._max_angle        = None
            self._max_signed_angle = None
            self._phase            = 'reaching'

        elif self._phase == 'reaching':
            pos = self._active_pos()
            if pos is None or self._pos_trunk is None:
                return
            dist, angle             = _dist_angle(pos, self._pos_trunk)
            self._max_dist          = dist
            self._max_angle         = angle
            self._max_signed_angle  = _signed_angle(pos, self._pos_trunk)
            self._phase             = 'wait_log_start'

        elif self._phase == 'wait_log_start':
            if not self._hand_in_new_start():
                return
            self._start_sweep()

        elif self._phase == 'sweeping':
            if not self._sweep_waiting:
                return
            prev_idx = self._sweep_wp_idx
            self._sweep_wp_idx += 1
            if self._sweep_wp_idx >= len(self._sweep_waypoints):
                self._compute_stats()
                self._phase = 'done'
            else:
                # Contralateral (wp 0) and ipsilateral (wp 2): next segment
                # starts from where the hand currently is.
                if prev_idx in (0, 2):
                    pos = self._active_pos()
                    if pos is not None and self._pos_trunk is not None:
                        self._sweep_angle = _signed_angle(pos, self._pos_trunk)
                self._sweep_waiting = False

    # ── helpers ───────────────────────────────────────────────

    def _active_pos(self):
        return self._pos_right if self._active_side == 'right' else self._pos_left

    def _hand_in_start_circle(self):
        if self._pos_trunk is None:
            return None
        cy = self._pos_trunk[0]
        cz = self._pos_trunk[1] + START_OFFSET_Z
        for side, pos in [('right', self._pos_right), ('left', self._pos_left)]:
            if pos is None:
                continue
            if math.hypot(pos[0] - cy, pos[1] - cz) <= START_CIRCLE_R:
                return side
        return None

    def _new_start_pos(self):
        if self._pos_trunk is None or self._max_dist is None:
            return None, None
        r = math.radians(self._max_signed_angle)
        return (self._pos_trunk[0] + self._max_dist * math.sin(r),
                self._pos_trunk[1] + self._max_dist * math.cos(r))

    def _hand_in_new_start(self):
        pos = self._active_pos()
        if pos is None:
            return False
        ny, nz = self._new_start_pos()
        if ny is None:
            return False
        return math.hypot(pos[0] - ny, pos[1] - nz) <= START_CIRCLE_R

    def _start_sweep(self):
        self._sweep_r     = self._max_dist + self.state.ws2_dot_offset
        self._sweep_angle = self._max_signed_angle
        if self._active_side == 'right':
            self._sweep_waypoints = [-90.0, 0.0, 90.0, 0.0]
        else:
            self._sweep_waypoints = [90.0, 0.0, -90.0, 0.0]
        self._sweep_wp_idx  = 0
        self._sweep_waiting = False
        self._range_bins    = {}
        self._trajectory    = []
        self._phase         = 'sweeping'

    def _compute_stats(self):
        if not self._range_bins:
            return
        bins   = self._range_bins
        dtheta = math.pi / 180.0

        def _bin_stats(b):
            if not b:
                return None, None, None
            d = list(b.values())
            return (sum(d) / len(d),
                    max(b) - min(b),
                    0.5 * sum(r * r * dtheta for r in d))

        dists = list(bins.values())
        self._stat_avg_dist      = sum(dists) / len(dists)
        self._stat_covered_angle = max(bins) - min(bins)
        self._stat_area          = 0.5 * sum(r * r * dtheta for r in dists)

        if self._active_side == 'right':
            contra_bins = {k: v for k, v in bins.items() if k < 0}
            ipsi_bins   = {k: v for k, v in bins.items() if k > 0}
        else:
            contra_bins = {k: v for k, v in bins.items() if k > 0}
            ipsi_bins   = {k: v for k, v in bins.items() if k < 0}

        self._stat_contra_avg, self._stat_contra_angle, self._stat_contra_area = _bin_stats(contra_bins)
        self._stat_ipsi_avg,   self._stat_ipsi_angle,   self._stat_ipsi_area   = _bin_stats(ipsi_bins)

        self._results[self._active_side] = {
            'avg_dist':      self._stat_avg_dist,
            'covered_angle': self._stat_covered_angle,
            'area':          self._stat_area,
            'contra_avg':    self._stat_contra_avg,
            'contra_angle':  self._stat_contra_angle,
            'contra_area':   self._stat_contra_area,
            'ipsi_avg':      self._stat_ipsi_avg,
            'ipsi_angle':    self._stat_ipsi_angle,
            'ipsi_area':     self._stat_ipsi_area,
            'sweep_speed':   self.state.ws2_sweep_speed,
            'range_bins':    dict(self._range_bins),
            'trajectory':    list(self._trajectory),
        }
        self._log_result_to_csv()

    def _log_result_to_csv(self):
        if self.liberty.use_mouse:
            return
        import csv
        from datetime import datetime

        r   = self._results.get(self._active_side, {})
        now = datetime.now()

        def _f(val, dec=1):
            return f'{val:.{dec}f}' if val is not None else ''

        row = {
            'date':          now.strftime('%m/%d/%Y'),
            'time':          now.strftime('%H:%M:%S'),
            'hand':          self._active_side or '',
            'sweep_speed':   _f(r.get('sweep_speed')),
            'max_dist':      _f(r.get('avg_dist')),
            'dist_contra':   _f(r.get('contra_avg')),
            'dist_ipsi':     _f(r.get('ipsi_avg')),
            'angle_range':   _f(r.get('covered_angle'), 0),
            'angle_contra':  _f(r.get('contra_angle'), 0),
            'angle_ipsi':    _f(r.get('ipsi_angle'), 0),
            'area_total':    _f(r.get('area')),
            'area_contra':   _f(r.get('contra_area')),
            'area_ipsi':     _f(r.get('ipsi_area')),
        }
        fieldnames = list(row.keys())

        pid    = self.state.participant_id or 'unknown'
        base   = self.state.data_dir if self.state.data_dir else os.path.expanduser('~')
        folder = os.path.join(base, pid)
        os.makedirs(folder, exist_ok=True)
        path   = os.path.join(folder, 'ws2_results.csv')

        write_header = not os.path.exists(path)
        with open(path, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if write_header:
                writer.writeheader()
            writer.writerow(row)

    # ── tick ─────────────────────────────────────────────────

    def _tick(self):
        now = time.perf_counter()
        dt  = now - self._last_tick
        self._last_tick = now

        self._pos_right = self._read_hand('right')
        self._pos_left  = self._read_hand('left')
        self._pos_trunk = self._read_trunk() if self.state.dig_trunk_enabled else None

        if self._phase == 'sweeping':
            if not self._sweep_waiting:
                self._update_sweep(dt)
            self._update_range()

        self.update()

    def _update_sweep(self, dt):
        target    = self._sweep_waypoints[self._sweep_wp_idx]
        remaining = target - self._sweep_angle
        step      = math.copysign(
            min(self.state.ws2_sweep_speed * dt, abs(remaining)), remaining)
        self._sweep_angle += step
        if abs(self._sweep_angle - target) < 0.01:
            self._sweep_angle   = target
            self._sweep_waiting = True

    def _update_range(self):
        pos = self._active_pos()
        if pos is None or self._pos_trunk is None:
            return
        dist, _ = _dist_angle(pos, self._pos_trunk)
        key     = round(_signed_angle(pos, self._pos_trunk))
        if key not in self._range_bins or dist > self._range_bins[key]:
            self._range_bins[key] = dist
        self._trajectory.append((pos[0], pos[1]))

    # ── sensor reading ────────────────────────────────────────

    def _read_hand(self, side):
        if self.liberty.use_mouse:
            return self._mouse_to_cm() if side == self._mouse_hand else None
        from digitizer import track_mcp
        st  = self.state
        sid = st.dig_sensor_right if side == 'right' else st.dig_sensor_left
        s   = self.liberty.get_sensor(sid)
        if s is None:
            return None
        if st.dig_mode >= 1:
            offset = st.mcp_offset_right if side == 'right' else st.mcp_offset_left
            if offset is not None:
                pos = track_mcp(s, offset)
                return (pos[1] - st.sensor_y_offset, pos[2] - st.sensor_z_offset)
        return (s.y * 2.54 - st.sensor_y_offset, s.z * 2.54 - st.sensor_z_offset)

    def _read_trunk(self):
        if self.liberty.use_mouse:
            st = self.state
            return ((st.WORKSPACE_Y_MIN + st.WORKSPACE_Y_MAX) / 2.0,
                    st.WORKSPACE_Z_MIN)
        st = self.state
        s  = self.liberty.get_sensor(st.dig_sensor_trunk)
        if s is None:
            return None
        return (s.y * 2.54 - st.sensor_y_offset, s.z * 2.54 - st.sensor_z_offset)

    def _mouse_to_cm(self):
        if self._mouse_px is None or self._ws.width() == 0:
            return None
        st = self.state
        px, py = self._mouse_px
        dy = max(st.WORKSPACE_Y_MAX - st.WORKSPACE_Y_MIN, 0.01)
        dz = max(st.WORKSPACE_Z_MAX - st.WORKSPACE_Z_MIN, 0.01)
        y_cm = st.WORKSPACE_Y_MIN + (px - self._ws.left()) / self._ws.width()  * dy
        z_cm = st.WORKSPACE_Z_MIN + (self._ws.bottom() - py) / self._ws.height() * dz
        return (y_cm, z_cm)

    # ── coordinate mapping ────────────────────────────────────

    def _recompute_ws(self):
        self._ws = QRect(0, 0, self.width(), self.height())

    def _to_screen(self, y_cm, z_cm):
        st = self.state
        dy = max(st.WORKSPACE_Y_MAX - st.WORKSPACE_Y_MIN, 0.01)
        dz = max(st.WORKSPACE_Z_MAX - st.WORKSPACE_Z_MIN, 0.01)
        px = self._ws.left()   + (y_cm - st.WORKSPACE_Y_MIN) / dy * self._ws.width()
        py = self._ws.bottom() - (z_cm - st.WORKSPACE_Z_MIN) / dz * self._ws.height()
        return int(px), int(py)

    def _r_px(self, r_cm):
        st = self.state
        ry = self._ws.width()  / max(st.WORKSPACE_Y_MAX - st.WORKSPACE_Y_MIN, 0.01)
        rz = self._ws.height() / max(st.WORKSPACE_Z_MAX - st.WORKSPACE_Z_MIN, 0.01)
        return max(1, int(r_cm * ry)), max(1, int(r_cm * rz))

    # ── drawing ───────────────────────────────────────────────

    def paintEvent(self, e):
        self._recompute_ws()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(0, 0, 0))

        if self._pos_trunk is not None:
            self._draw_trunk(p)

        if self._phase == 'wait_start':
            self._draw_start_circle(p)
        elif self._phase == 'wait_log_start':
            self._draw_new_start_circle(p)

        # Hand cursors
        if self._phase == 'wait_start':
            cursor_positions = [self._pos_right, self._pos_left]
        elif self._phase in ('reaching', 'wait_log_start', 'sweeping'):
            cursor_positions = [self._active_pos()]
        else:
            cursor_positions = []

        for pos in cursor_positions:
            if pos is not None:
                sx, sy = self._to_screen(pos[0], pos[1])
                p.setBrush(QBrush(QColor(255, 255, 255)))
                p.setPen(Qt.NoPen)
                p.drawEllipse(QPoint(sx, sy), 8, 8)

        if self._phase == 'done' and self._range_bins:
            self._draw_range(p)
            self._draw_trajectory(p)
            if self._show_overlay:
                opp = 'left' if self._active_side == 'right' else 'right'
                self._draw_flipped_overlay(p, self._results.get(opp, {}))

        if self._phase in ('sweeping', 'done') and self._sweep_angle is not None:
            self._draw_sweep_dot(p)

        self._draw_hand_info(p)
        self._draw_instruction(p)

        p.setPen(QColor(60, 60, 60))
        p.setFont(QFont('Arial', 12))
        if self._phase == 'wait_log_start':
            bottom_hint = "Shift+Space — reset start    |    ESC — pause"
        else:
            bottom_hint = "ESC — pause"
        p.drawText(self.rect().adjusted(0, 0, -10, -10),
                   Qt.AlignBottom | Qt.AlignRight, bottom_hint)

    def _draw_trunk(self, p):
        ty, tz = self._pos_trunk
        x1, sy = self._to_screen(ty - 15, tz)
        x2, _  = self._to_screen(ty + 15, tz)
        p.setPen(QPen(QColor(255, 255, 255), 5))
        p.drawLine(x1, sy, x2, sy)

        tx, ty_s  = self._to_screen(ty, tz)
        _, ty_end = self._to_screen(ty, tz + 50)
        dot_pen = QPen(QColor(255, 255, 255), 1, Qt.CustomDashLine)
        dot_pen.setDashPattern([2, 10])
        p.setPen(dot_pen)
        p.drawLine(tx, ty_s, tx, ty_end)

    def _draw_start_circle(self, p):
        if self._pos_trunk is None:
            return
        ty, tz = self._pos_trunk
        cx, cy = self._to_screen(ty, tz + START_OFFSET_Z)
        rx, rz = self._r_px(START_CIRCLE_R)
        inside = self._hand_in_start_circle() is not None
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255), 4 if inside else 2))
        p.drawEllipse(QPoint(cx, cy), rx, rz)

    def _draw_new_start_circle(self, p):
        ny, nz = self._new_start_pos()
        if ny is None:
            return
        cx, cy = self._to_screen(ny, nz)
        rx, rz = self._r_px(START_CIRCLE_R)
        inside = self._hand_in_new_start()
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255), 4 if inside else 2))
        p.drawEllipse(QPoint(cx, cy), rx, rz)

    def _draw_range(self, p):
        if not self._range_bins or self._pos_trunk is None:
            return
        tx, ts      = self._to_screen(self._pos_trunk[0], self._pos_trunk[1])
        sorted_bins = sorted(self._range_bins.items())

        pts = [QPoint(tx, ts)]
        for angle_deg, dist in sorted_bins:
            a  = math.radians(angle_deg)
            py = self._pos_trunk[0] + dist * math.sin(a)
            pz = self._pos_trunk[1] + dist * math.cos(a)
            sx, sy = self._to_screen(py, pz)
            pts.append(QPoint(sx, sy))

        p.setBrush(QBrush(QColor(100, 180, 255, 70)))
        p.setPen(QPen(QColor(100, 180, 255), 1))
        p.drawPolygon(QPolygon(pts))

    def _draw_flipped_overlay(self, p, opp_result):
        if not opp_result or self._pos_trunk is None:
            return
        tx, ts = self._to_screen(self._pos_trunk[0], self._pos_trunk[1])
        trunk_y = self._pos_trunk[0]

        # Filled area: mirror angle signs
        opp_bins = opp_result.get('range_bins', {})
        if opp_bins:
            mirrored = sorted((-a, d) for a, d in opp_bins.items())
            pts = [QPoint(tx, ts)]
            for angle_deg, dist in mirrored:
                a  = math.radians(angle_deg)
                py = self._pos_trunk[0] + dist * math.sin(a)
                pz = self._pos_trunk[1] + dist * math.cos(a)
                sx, sy = self._to_screen(py, pz)
                pts.append(QPoint(sx, sy))
            p.setBrush(QBrush(QColor(255, 160, 60, 70)))
            p.setPen(QPen(QColor(255, 160, 60), 1))
            p.drawPolygon(QPolygon(pts))

        # Trajectory: mirror Y around trunk_y
        traj = opp_result.get('trajectory', [])
        if len(traj) >= 2:
            p.setPen(QPen(QColor(255, 200, 120), 2))
            for i in range(1, len(traj)):
                ay, az = traj[i - 1]
                by, bz = traj[i]
                ax, asc = self._to_screen(2 * trunk_y - ay, az)
                bx, bsc = self._to_screen(2 * trunk_y - by, bz)
                p.drawLine(ax, asc, bx, bsc)

    def _draw_trajectory(self, p):
        if len(self._trajectory) < 2:
            return
        p.setPen(QPen(QColor(180, 220, 255), 2))
        for i in range(1, len(self._trajectory)):
            ax, ay = self._to_screen(*self._trajectory[i - 1])
            bx, by = self._to_screen(*self._trajectory[i])
            p.drawLine(ax, ay, bx, by)

    def _draw_sweep_dot(self, p):
        if self._pos_trunk is None:
            return
        r     = math.radians(self._sweep_angle)
        dot_y = self._pos_trunk[0] + self._sweep_r * math.sin(r)
        dot_z = self._pos_trunk[1] + self._sweep_r * math.cos(r)
        tx, ts = self._to_screen(self._pos_trunk[0], self._pos_trunk[1])
        dx, ds = self._to_screen(dot_y, dot_z)
        ex, es = self._ray_to_edge(tx, ts, dx, ds)
        p.setPen(QPen(QColor(220, 60, 60), 1))
        p.drawLine(tx, ts, ex, es)
        p.setBrush(QBrush(QColor(220, 60, 60)))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPoint(dx, ds), 8, 8)

    def _ray_to_edge(self, x0, y0, x1, y1):
        """Return the point where the ray from (x0,y0) through (x1,y1) exits the screen."""
        ddx = x1 - x0
        ddy = y1 - y0
        if ddx == 0 and ddy == 0:
            return x1, y1
        t_max = float('inf')
        if ddx > 0:
            t_max = min(t_max, (self.width()  - x0) / ddx)
        elif ddx < 0:
            t_max = min(t_max, -x0 / ddx)
        if ddy > 0:
            t_max = min(t_max, (self.height() - y0) / ddy)
        elif ddy < 0:
            t_max = min(t_max, -y0 / ddy)
        return int(x0 + t_max * ddx), int(y0 + t_max * ddy)

    def _draw_instruction(self, p):
        p.setFont(QFont('Arial', 22, QFont.Bold))
        p.setPen(QColor(200, 200, 200))
        rect = self.rect().adjusted(0, 0, 0, -60)
        if self._phase == 'wait_start' and self._hand_in_start_circle() is None:
            p.drawText(rect, Qt.AlignBottom | Qt.AlignHCenter,
                       "Please move your hand to the start position.")
        elif self._phase == 'reaching':
            p.drawText(rect, Qt.AlignBottom | Qt.AlignHCenter,
                       "Reach as far as possible following the center line.")
        elif self._phase == 'wait_log_start' and not self._hand_in_new_start():
            p.drawText(rect, Qt.AlignBottom | Qt.AlignHCenter,
                       "Return to your max reach position and press space.")
        elif self._phase == 'wait_log_start' and self._hand_in_new_start():
            p.drawText(rect, Qt.AlignBottom | Qt.AlignHCenter,
                       "Press space to start sweep.")
        elif self._phase == 'sweeping' and not self._sweep_waiting:
            p.drawText(rect, Qt.AlignBottom | Qt.AlignHCenter,
                       "Reach toward the red dot as far as possible.")
        elif self._phase == 'sweeping' and self._sweep_waiting:
            p.drawText(rect, Qt.AlignBottom | Qt.AlignHCenter,
                       "Press space to continue.")
        elif self._phase == 'done':
            p.drawText(self.rect().adjusted(0, 0, 0, -self.height() // 2),
                       Qt.AlignCenter, "Trial complete!")
            p.setFont(QFont('Arial', 14))
            p.setPen(QColor(120, 120, 120))
            p.drawText(self.rect().adjusted(0, 0, 0, -20),
                       Qt.AlignBottom | Qt.AlignHCenter,
                       "Space — play again    |    Enter — compare hands    |    ESC — pause / exit")
            if self._show_overlay:
                self._draw_overlay_legend(p)

    def _draw_overlay_legend(self, p):
        opp  = 'left' if self._active_side == 'right' else 'right'
        cur_label = ('Right hand' if self._active_side == 'right' else 'Left hand')
        opp_label = ('Right hand' if opp == 'right' else 'Left hand')
        font = QFont('Arial', 15, QFont.Bold)
        p.setFont(font)
        cx = self.width() // 2
        y  = 16
        sw = 18  # swatch size

        # Blue swatch — current hand
        p.fillRect(cx - 160, y, sw, sw, QColor(100, 180, 255, 200))
        p.setPen(QColor(100, 180, 255))
        p.drawText(cx - 160 + sw + 6, y, 160, sw + 4, Qt.AlignVCenter, cur_label)

        # Orange swatch — opposite hand
        p.fillRect(cx + 20, y, sw, sw, QColor(255, 160, 60, 200))
        p.setPen(QColor(255, 160, 60))
        p.drawText(cx + 20 + sw + 6, y, 160, sw + 4, Qt.AlignVCenter, opp_label)

    def _draw_hand_info(self, p):
        if self._pos_trunk is None:
            return
        PAD = 16

        if self._phase == 'wait_start':
            sides = [
                ('Left hand',  self._pos_left,  Qt.AlignLeft,  'left'),
                ('Right hand', self._pos_right, Qt.AlignRight, 'right'),
            ]
        elif self._phase in ('reaching', 'wait_log_start', 'sweeping'):
            label = 'Right hand' if self._active_side == 'right' else 'Left hand'
            align = Qt.AlignRight if self._active_side == 'right' else Qt.AlignLeft
            sides = [(label, self._active_pos(), align, self._active_side)]
        elif self._phase == 'done':
            label = 'Right hand' if self._active_side == 'right' else 'Left hand'
            align = Qt.AlignRight if self._active_side == 'right' else Qt.AlignLeft
            sides = [(label, self._active_pos(), align, self._active_side)]
            opp   = 'left' if self._active_side == 'right' else 'right'
            if opp in self._results:
                opp_label = 'Left hand' if opp == 'left' else 'Right hand'
                opp_align = Qt.AlignLeft if opp == 'left' else Qt.AlignRight
                opp_pos   = self._pos_left if opp == 'left' else self._pos_right
                sides.append((opp_label, opp_pos, opp_align, opp))
        else:
            sides = []

        def _fmt(val, decimals=1):
            return f'{val:.{decimals}f}' if val is not None else '--'

        def _draw_result_block(p, res, align, base_y):
            if res is None:
                return
            split = self.state.ws2_show_split_stats
            stat_lines = [
                (f'max dist = {_fmt(res["avg_dist"])} cm'
                 + (f'  |  contra = {_fmt(res["contra_avg"])} cm'
                    f'  |  ipsi = {_fmt(res["ipsi_avg"])} cm' if split else '')),
                (f'angle range = {_fmt(res["covered_angle"], 0)}°'
                 + (f'  |  contra = {_fmt(res["contra_angle"], 0)}°'
                    f'  |  ipsi = {_fmt(res["ipsi_angle"], 0)}°' if split else '')),
                (f'area = {_fmt(res["area"])} cm²'
                 + (f'  |  contra = {_fmt(res["contra_area"])} cm²'
                    f'  |  ipsi = {_fmt(res["ipsi_area"])} cm²' if split else '')),
                f'sweep speed = {_fmt(res.get("sweep_speed"))} °/s',
            ]
            p.setFont(QFont('Arial', 14))
            p.setPen(QColor(150, 200, 255))
            for j, line in enumerate(stat_lines):
                p.drawText(self.rect().adjusted(PAD, base_y + j * 22, -PAD, 0),
                           align | Qt.AlignTop, line)

        for label, pos, align, side in sides:
            live = ('— cm  —°' if pos is None
                    else f'{_dist_angle(pos, self._pos_trunk)[0]:.1f} cm  '
                         f'{_dist_angle(pos, self._pos_trunk)[1]:.1f}°')

            p.setFont(QFont('Arial', 16, QFont.Bold))
            p.setPen(QColor(200, 200, 200))
            header_lines = [label, live]
            for i, line in enumerate(header_lines):
                p.drawText(self.rect().adjusted(PAD, PAD + i * 24, -PAD, 0),
                           align | Qt.AlignTop, line)

            base = PAD + len(header_lines) * 24 + 8
            _draw_result_block(p, self._results.get(side), align, base)
