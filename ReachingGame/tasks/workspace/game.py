import math
import time
import threading
import winsound
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QTimer, QRect, QPoint
from PyQt5.QtGui import QPainter, QColor, QBrush, QFont, QPen, QPolygon

N_BINS        = 120   # 3° per bin
SMOOTH_WIN    = 2     # bins on each side for smoothing
SWITCH_DUR    = 2.0   # seconds for "Switch hand." display


def _shoelace(pts):
    n = len(pts)
    if n < 3:
        return 0.0
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += pts[i][0] * pts[j][1] - pts[j][0] * pts[i][1]
    return abs(area) / 2.0


def _beep(freq, ms):
    threading.Thread(target=winsound.Beep, args=(freq, ms), daemon=True).start()

def _beep_seq(*pairs):
    def _run():
        for freq, ms in pairs:
            winsound.Beep(freq, ms)
    threading.Thread(target=_run, daemon=True).start()


class GameScreen(QWidget):
    MARGIN = 0

    def __init__(self, state, liberty, main_window):
        super().__init__()
        self.state   = state
        self.liberty = liberty
        self.mw      = main_window
        self.setStyleSheet("background-color: #000000;")
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.BlankCursor)

        self._ws       = QRect()
        self._cursor_y = 0.0
        self._cursor_z = 0.0

        self._phase        = 'idle'
        self._trials       = []
        self._trial_idx    = -1
        self._start_pts    = {'R': None, 'L': None}
        self._traj         = []
        self._show_pts     = []
        self._show_timer   = 0.0
        self._switch_timer = 0.0
        self._envelopes      = {'R': [], 'L': []}   # list of (bins, sy, sz)
        self._pending_env    = None                 # (bins, arm, sy, sz) — added on advance
        self._target_bnd     = None                 # (avg_bins, target_arm, testing_arm)
        self._lateral_line_z = None                 # Z of horizontal reference line
        self._last_area      = 0.0                  # area of most recent trial (cm²)
        self._areas          = {'R': [], 'L': []}   # per-arm area history

        self._guide_angle = None   # degrees; None = inactive

        self._dt        = 0.008
        self._last_tick = time.perf_counter()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(8)

    # ──────────────────────────────────────────────────── events

    def showEvent(self, e):
        self._phase        = 'idle'
        self._trials       = []
        self._trial_idx    = -1
        self._start_pts    = {'R': None, 'L': None}
        self._traj         = []
        self._show_pts     = []
        self._show_timer   = 0.0
        self._switch_timer = 0.0
        self._envelopes      = {'R': [], 'L': []}
        self._pending_env    = None
        self._target_bnd     = None
        self._lateral_line_z = None
        self._last_area      = 0.0
        self._areas          = {'R': [], 'L': []}
        self._guide_angle    = None
        self._build_trials()
        if self._trials:
            self._trial_idx = 0
            self._enter_trial()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.mw.show_screen('menu')
        elif e.key() == Qt.Key_Space:
            self._on_space()

    def mouseMoveEvent(self, e):
        if self.liberty.use_mouse and self._ws.width() > 0:
            self._cursor_y, self._cursor_z = self._to_cm(e.x(), e.y())

    # ──────────────────────────────────────────────────── tick

    def _tick(self):
        now = time.perf_counter()
        self._dt = now - self._last_tick
        self._last_tick = now

        if not self.liberty.use_mouse:
            self._read_sensor()

        if self._phase == 'recording':
            self._traj.append((self._cursor_y, self._cursor_z))
            self._update_guide_angle()

        elif self._phase == 'show_traj':
            self._show_timer += self._dt
            if self._show_timer >= self._trials[self._trial_idx]['display_s']:
                self._advance()

        elif self._phase == 'switch_hand':
            self._switch_timer += self._dt
            if self._switch_timer >= SWITCH_DUR:
                self._enter_trial()

        self.update()

    def _read_sensor(self):
        if not self._trials or not (0 <= self._trial_idx < len(self._trials)):
            return
        arm    = self._trials[self._trial_idx]['arm']
        result = self._read_hand(arm)
        if result:
            self._cursor_y, self._cursor_z = result

    def _read_hand(self, arm):
        from digitizer import track_mcp
        st  = self.state
        sid = st.dig_sensor_right if arm == 'R' else st.dig_sensor_left
        s   = self.liberty.get_sensor(sid)
        if s is None:
            return None
        offset = (st.mcp_offset_right if arm == 'R' else st.mcp_offset_left) \
                 if st.dig_mode >= 1 else None
        if offset is not None:
            pos = track_mcp(s, offset)
            return pos[1] - st.sensor_y_offset, pos[2] - st.sensor_z_offset
        return s.y * 2.54 - st.sensor_y_offset, s.z * 2.54 - st.sensor_z_offset

    # ──────────────────────────────────────────────────── session build

    def _build_trials(self):
        from tasks.workspace_task import SESSIONS_SCREEN
        scr = self.mw.screens.get(SESSIONS_SCREEN)
        if not scr:
            return
        self._trials = []
        for r in range(scr.table.rowCount()):
            self._trials.append({
                'arm':       scr.table.item(r, 1).text().strip().upper(),
                'display_s': float(scr.table.item(r, 2).text()),
                'draw':      int(scr.table.item(r, 3).text()),
            })

    # ──────────────────────────────────────────────────── state machine

    def _enter_trial(self):
        arm = self._trials[self._trial_idx]['arm']
        self._traj           = []
        self._lateral_line_z = None
        self._phase = 'set_start' if self._start_pts[arm] is None else 'set_lateral'

    def _on_space(self):
        if self._phase == 'set_start':
            arm = self._trials[self._trial_idx]['arm']
            self._start_pts[arm] = (self._cursor_y, self._cursor_z)
            self._phase = 'set_lateral'
            _beep(660, 100)

        elif self._phase == 'set_lateral':
            arm = self._trials[self._trial_idx]['arm']
            self._lateral_line_z = self._cursor_z
            self._guide_angle    = 180.0 if arm == 'R' else 0.0
            self._phase = 'recording'
            self._traj  = [(self._cursor_y, self._cursor_z)]
            _beep(880, 80)

        elif self._phase == 'recording':
            self._end_recording()

    def _update_guide_angle(self):
        if self._guide_angle is None:
            return
        arm   = self._trials[self._trial_idx]['arm']
        speed = self.state.ws_guide_speed_R if arm == 'R' else self.state.ws_guide_speed_L
        delta = speed * self._dt
        if arm == 'R':
            self._guide_angle = max(0.0, self._guide_angle - delta)
        else:
            self._guide_angle = min(180.0, self._guide_angle + delta)

    def _end_recording(self):
        self._guide_angle = None
        self._show_pts   = list(self._traj)
        self._show_timer = 0.0
        arm    = self._trials[self._trial_idx]['arm']
        sy, sz = self._start_pts[arm]
        bins   = self._compute_bins(self._traj, sy, sz)
        self._pending_env = (bins, arm, sy, sz)
        pts = self._bins_to_pts(bins, sy, sz)
        self._last_area = _shoelace(pts)
        self._areas[arm].append(self._last_area)
        self._phase = 'show_traj'
        _beep_seq((784, 80), (1047, 100))

    def _advance(self):
        if self._pending_env:
            bins, arm, sy, sz = self._pending_env
            self._envelopes[arm].append((bins, sy, sz))
            self._pending_env = None
        cur_arm = self._trials[self._trial_idx]['arm']
        self._trial_idx += 1
        if self._trial_idx >= len(self._trials):
            self._phase = 'done'
            return
        nxt_arm = self._trials[self._trial_idx]['arm']
        if nxt_arm != cur_arm:
            self._build_target_boundary(cur_arm, nxt_arm)
            self._switch_timer = 0.0
            self._phase = 'switch_hand'
        else:
            self._enter_trial()

    # ──────────────────────────────────────────────────── envelope

    def _compute_bins(self, traj, sy, sz):
        bins = [0.0] * N_BINS
        for y, z in traj:
            dy = y - sy
            dz = z - sz
            r  = math.sqrt(dy * dy + dz * dz)
            if r < 0.3:
                continue
            idx = int((math.atan2(dz, dy) + math.pi) / (2 * math.pi) * N_BINS) % N_BINS
            if r > bins[idx]:
                bins[idx] = r
        sm = [0.0] * N_BINS
        w  = SMOOTH_WIN
        for i in range(N_BINS):
            sm[i] = sum(bins[(i + j - w) % N_BINS] for j in range(2 * w + 1)) / (2 * w + 1)
        return sm

    def _build_target_boundary(self, target_arm, testing_arm):
        env_list = self._envelopes[target_arm]
        if not env_list:
            self._target_bnd = None
            return
        avg  = [sum(e[0][i] for e in env_list) / len(env_list) for i in range(N_BINS)]
        self._target_bnd = (avg, target_arm, testing_arm)

    def _bins_to_pts(self, bins, sy, sz, mirror_start=None):
        pts = []
        for i, r in enumerate(bins):
            if r < 0.3:
                continue
            angle = -math.pi + (i + 0.5) * 2 * math.pi / N_BINS
            dy = r * math.cos(angle)
            dz = r * math.sin(angle)
            if mirror_start is not None:
                my, mz = mirror_start
                pts.append((my - dy, mz + dz))
            else:
                pts.append((sy + dy, sz + dz))
        return pts

    # ──────────────────────────────────────────────────── coordinates

    def _recompute_ws(self):
        m = self.MARGIN
        self._ws = QRect(m, m, self.width() - 2 * m, self.height() - 2 * m)

    def _to_screen(self, y_cm, z_cm):
        s  = self.state
        dy = max(s.WORKSPACE_Y_MAX - s.WORKSPACE_Y_MIN, 0.01)
        dz = max(s.WORKSPACE_Z_MAX - s.WORKSPACE_Z_MIN, 0.01)
        px = self._ws.left()   + (y_cm - s.WORKSPACE_Y_MIN) / dy * self._ws.width()
        py = self._ws.bottom() - (z_cm - s.WORKSPACE_Z_MIN) / dz * self._ws.height()
        return int(px), int(py)

    def _to_cm(self, px, py):
        s  = self.state
        dy = max(s.WORKSPACE_Y_MAX - s.WORKSPACE_Y_MIN, 0.01)
        dz = max(s.WORKSPACE_Z_MAX - s.WORKSPACE_Z_MIN, 0.01)
        y  = s.WORKSPACE_Y_MIN + (px - self._ws.left())   / max(self._ws.width(),  1) * dy
        z  = s.WORKSPACE_Z_MIN + (self._ws.bottom() - py) / max(self._ws.height(), 1) * dz
        return y, z

    # ──────────────────────────────────────────────────── drawing

    def paintEvent(self, e):
        self._recompute_ws()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(0, 0, 0))

        if self._phase == 'idle':
            if not self._trials:
                self._draw_text(p, "No sessions configured.\nPress ESC to return.")
            return

        if self._phase == 'done':
            self._draw_text(p, "Session complete!\nPress ESC to return to menu.")
            return

        if self._phase == 'switch_hand':
            self._draw_switch(p)
            return

        trial = self._trials[self._trial_idx]
        arm   = trial['arm']

        self._draw_ghosts(p, arm)
        self._draw_target_boundary(p, arm)
        self._draw_lateral_line(p)
        self._draw_center_line(p, arm)

        if self._phase == 'set_start':
            self._draw_instruction(p, "Position your center, then press SPACE.")
        elif self._phase == 'set_lateral':
            self._draw_instruction(p, "Extend arm to max lateral, then press SPACE.")
        elif self._phase == 'recording':
            if trial['draw']:
                self._draw_live_traj(p)
            self._draw_guide_line(p)
            self._draw_instruction(p, "Follow the guideline. Reach as far as possible.")
        elif self._phase == 'show_traj':
            self._draw_show_traj(p)
            self._draw_area_info(p, arm)

        self._draw_cursor(p)
        self._draw_counter(p, arm)

    def _draw_cursor(self, p):
        sx, sy = self._to_screen(self._cursor_y, self._cursor_z)
        p.setBrush(QBrush(QColor(220, 30, 30)))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPoint(sx, sy), 7, 7)

    def _draw_center_line(self, p, arm):
        sp = self._start_pts[arm]
        if sp is None:
            return
        cy, cz = sp
        x1, y1 = self._to_screen(cy, cz - 2.5)
        x2, y2 = self._to_screen(cy, cz + 2.5)
        p.setPen(QPen(QColor(255, 255, 255), 2))
        p.drawLine(x1, y1, x2, y2)

    def _draw_lateral_line(self, p):
        if self._lateral_line_z is None:
            return
        _, line_y = self._to_screen(0, self._lateral_line_z)
        p.setPen(QPen(QColor(160, 160, 160), 1))
        p.drawLine(0, line_y, self.width(), line_y)

    def _draw_ghosts(self, p, arm):
        env_list = self._envelopes[arm]
        if not env_list:
            return
        color = QColor(255, 255, 255, 128)

        if self.state.ws_ghost_mode == 'average':
            # Single ghost: running average of all stored envelopes
            n   = len(env_list)
            avg = [sum(e[0][i] for e in env_list) / n for i in range(N_BINS)]
            sy, sz = env_list[-1][1], env_list[-1][2]
            pts = self._bins_to_pts(avg, sy, sz)
            if len(pts) < 3:
                return
            poly = QPolygon([QPoint(*self._to_screen(y, z)) for y, z in pts])
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(color, 1))
            p.drawPolygon(poly)
        else:
            # Individual: up to 5 most recent
            n       = len(env_list)
            start_i = max(0, n - 5)
            for bins, sy, sz in env_list[start_i:]:
                pts = self._bins_to_pts(bins, sy, sz)
                if len(pts) < 3:
                    continue
                poly = QPolygon([QPoint(*self._to_screen(y, z)) for y, z in pts])
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(color, 1))
                p.drawPolygon(poly)

    def _draw_target_boundary(self, p, arm):
        if not self._target_bnd:
            return
        avg_bins, _ta, testing_arm = self._target_bnd
        if arm != testing_arm:
            return
        sp = self._start_pts[testing_arm]
        if sp is None:
            return
        pts = self._bins_to_pts(avg_bins, 0, 0, mirror_start=sp)
        if len(pts) < 3:
            return
        poly = QPolygon([QPoint(*self._to_screen(y, z)) for y, z in pts])
        pen  = QPen(QColor(255, 255, 255), 3, Qt.CustomDashLine)
        pen.setDashPattern([8, 6])
        p.setBrush(Qt.NoBrush)
        p.setPen(pen)
        p.drawPolygon(poly)

    def _draw_live_traj(self, p):
        if len(self._traj) < 2:
            return
        p.setPen(QPen(QColor(180, 180, 180), 2))
        for i in range(1, len(self._traj)):
            x1, y1 = self._to_screen(*self._traj[i - 1])
            x2, y2 = self._to_screen(*self._traj[i])
            p.drawLine(x1, y1, x2, y2)

    def _draw_show_traj(self, p):
        if len(self._show_pts) < 2:
            return
        p.setPen(QPen(QColor(255, 255, 255), 2))
        for i in range(1, len(self._show_pts)):
            x1, y1 = self._to_screen(*self._show_pts[i - 1])
            x2, y2 = self._to_screen(*self._show_pts[i])
            p.drawLine(x1, y1, x2, y2)

    def _draw_instruction(self, p, text):
        p.setPen(QColor(200, 200, 200))
        p.setFont(QFont('Arial', 24, QFont.Bold))
        p.drawText(self.rect().adjusted(0, 40, 0, 0), Qt.AlignTop | Qt.AlignHCenter, text)

    def _draw_counter(self, p, arm):
        arm_text = "Right" if arm == 'R' else "Left"
        p.setPen(QColor(160, 160, 160))
        p.setFont(QFont('Arial', 14))
        p.drawText(20, 30, f"Trial  {self._trial_idx + 1} / {len(self._trials)}   Arm: {arm_text}")

    def _draw_area_info(self, p, arm):
        # Top-center: current trial area
        p.setPen(QColor(220, 220, 220))
        p.setFont(QFont('Arial', 20, QFont.Bold))
        p.drawText(self.rect().adjusted(0, 10, 0, 0),
                   Qt.AlignTop | Qt.AlignHCenter,
                   f"Area: {self._last_area:.1f} cm²")

        # Top-right: per-arm running averages
        def _avg_str(a):
            vals = self._areas[a]
            if not vals:
                return "—"
            return f"{sum(vals) / len(vals):.1f} cm²"

        lines = f"R avg:  {_avg_str('R')}\nL avg:  {_avg_str('L')}"
        p.setPen(QColor(160, 160, 160))
        p.setFont(QFont('Arial', 14))
        p.drawText(self.rect().adjusted(0, 10, -20, 0),
                   Qt.AlignTop | Qt.AlignRight,
                   lines)

    def _draw_switch(self, p):
        if 0 <= self._trial_idx < len(self._trials):
            arm_text = "Right" if self._trials[self._trial_idx]['arm'] == 'R' else "Left"
            msg = f"Switch hand.\n{arm_text} arm next."
        else:
            msg = "Switch hand."
        self._draw_text(p, msg)

    def _draw_guide_line(self, p):
        if not self.state.ws_guide_line_on or self._guide_angle is None:
            return
        arm = self._trials[self._trial_idx]['arm']
        sp  = self._start_pts[arm]
        if sp is None:
            return
        sx, sy_s = self._to_screen(*sp)
        angle_rad = math.radians(self._guide_angle)
        far_y = sp[0] + math.cos(angle_rad) * 300
        far_z = sp[1] + math.sin(angle_rad) * 300
        ex, ey = self._to_screen(far_y, far_z)
        p.setPen(QPen(QColor(200, 200, 200, 160), 1))
        p.drawLine(sx, sy_s, ex, ey)

    def _draw_text(self, p, text):
        p.setPen(QColor(220, 220, 220))
        p.setFont(QFont('Arial', 36, QFont.Bold))
        p.drawText(self.rect(), Qt.AlignCenter, text)
