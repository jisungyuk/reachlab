import math
import time
import threading
import winsound
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QTimer, QRect, QPoint
from PyQt5.QtGui import QPainter, QColor, QBrush, QFont, QPen, QPolygon

N_BINS          = 60    # 3° per bin, forward 180° only (bin 0 = 0°, bin 59 = 178.5°)
SMOOTH_WIN      = 2     # bins on each side for smoothing
SWITCH_DUR      = 2.0   # seconds for "Switch hand." display
LATERAL_START_R = 2.5   # cm — radius of start circle (diameter 5 cm)


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
        self._cursor_x = 0.0
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
        self._envelopes         = {'R': [], 'L': []}   # list of (bins, sy, sz)
        self._pending_env       = None                 # (bins, arm, sy, sz) — added on advance
        self._target_bnd        = None                 # (avg_bins, target_arm, testing_arm)
        self._lateral_lines     = {'R': None, 'L': None}  # Z of horizontal line per arm
        self._lateral_start_pts = {'R': None, 'L': None}  # start circle position per arm
        self._prev_setup        = {'R': None, 'L': None}  # (start_pt, lateral_line, lateral_start_pt) before reset
        self._last_area         = 0.0                  # area of most recent trial (cm²)
        self._areas             = {'R': [], 'L': []}   # per-arm area history

        self._guide_angle  = None   # degrees; None = inactive
        self._x_below_dur  = 0.0    # seconds cursor has been below elev_min_cm
        self._paused       = False

        self._dt        = 0.004
        self._last_tick = time.perf_counter()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(4)

    # ──────────────────────────────────────────────────── events

    def showEvent(self, e):
        timer_ms = max(1, round(1000 / self.state.sample_rate_hz))
        self._timer.start(timer_ms)
        self._phase        = 'idle'
        self._trials       = []
        self._trial_idx    = -1
        self._start_pts    = {'R': None, 'L': None}
        self._traj         = []
        self._show_pts     = []
        self._show_timer   = 0.0
        self._switch_timer = 0.0
        self._envelopes         = {'R': [], 'L': []}
        self._pending_env       = None
        self._target_bnd        = None
        self._lateral_lines     = {'R': None, 'L': None}
        self._lateral_start_pts = {'R': None, 'L': None}
        self._prev_setup        = {'R': None, 'L': None}
        self._last_area         = 0.0
        self._areas             = {'R': [], 'L': []}
        self._guide_angle       = None
        self._x_below_dur       = 0.0
        self._paused            = False
        self._build_trials()
        if self._trials:
            self._trial_idx = max(0, min(self.state.start_trial - 1, len(self._trials) - 1))
            self._enter_trial()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            if self._paused:
                self._paused = False
                self.mw.show_screen('menu')
            else:
                self._paused = True
            return
        if self._paused:
            if e.key() == Qt.Key_Space:
                self._paused = False
            return
        if e.key() == Qt.Key_Backspace:
            if self._phase == 'recording':
                self._abort_to_wait_start()
        elif e.key() == Qt.Key_Space:
            shift = bool(e.modifiers() & Qt.ShiftModifier)
            if shift:
                self._on_shift_space()
            else:
                self._on_space()

    def mouseMoveEvent(self, e):
        if self.liberty.use_mouse and self._ws.width() > 0:
            self._cursor_y, self._cursor_z = self._to_cm(e.x(), e.y())

    def wheelEvent(self, e):
        if self.liberty.use_mouse:
            delta = e.angleDelta().y() / 120  # notches
            self._cursor_x = round(self._cursor_x + delta * 0.5, 1)

    # ──────────────────────────────────────────────────── tick

    def _tick(self):
        now = time.perf_counter()
        self._dt = now - self._last_tick
        self._last_tick = now

        if self._paused:
            self.update()
            return

        if not self.liberty.use_mouse:
            self._read_sensor()

        if self._phase == 'recording':
            trial = self._trials[self._trial_idx]
            self._traj.append((self._cursor_y, self._cursor_z))
            self._update_guide_angle()
            if trial['elev_min_cm'] > 0 and self._cursor_x < trial['elev_min_cm']:
                self._x_below_dur += self._dt
                if self._x_below_dur >= self.state.ws_elev_dur:
                    self._abort_to_wait_start()
            else:
                self._x_below_dur = 0.0

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
            self._cursor_x, self._cursor_y, self._cursor_z = result

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
            return pos[0] - st.sensor_x_offset, pos[1] - st.sensor_y_offset, pos[2] - st.sensor_z_offset
        return s.x * 2.54 - st.sensor_x_offset, s.y * 2.54 - st.sensor_y_offset, s.z * 2.54 - st.sensor_z_offset

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
                'elev_min_cm':  float(scr.table.item(r, 4).text()),
            })

    # ──────────────────────────────────────────────────── state machine

    def _enter_trial(self):
        arm = self._trials[self._trial_idx]['arm']
        self._traj = []
        if self._start_pts[arm] is None:
            self._phase = 'set_start'
        elif self._lateral_lines[arm] is None:
            self._phase = 'set_lateral'
        else:
            self._phase = 'wait_start'

    def _on_space(self):
        if self._phase == 'set_start':
            arm = self._trials[self._trial_idx]['arm']
            self._start_pts[arm] = (self._cursor_y, self._cursor_z)
            self._phase = 'set_lateral'
            _beep(660, 100)

        elif self._phase == 'set_lateral':
            arm = self._trials[self._trial_idx]['arm']
            self._lateral_lines[arm]     = self._cursor_z
            self._lateral_start_pts[arm] = (self._cursor_y, self._cursor_z)
            # rebase existing envelopes to new center (bins/shape unchanged, origin updated)
            new_sy = self._start_pts[arm][0]
            new_sz = self._cursor_z
            self._envelopes[arm] = [
                (bins, new_sy, new_sz) for bins, _, _ in self._envelopes[arm]
            ]
            self._phase = 'wait_start'
            _beep(660, 100)

        elif self._phase == 'wait_start':
            if not self._in_start_circle():
                return
            trial = self._trials[self._trial_idx]
            if trial['elev_min_cm'] > 0 and self._cursor_x < trial['elev_min_cm']:
                return
            arm = trial['arm']
            self._guide_angle = 0.0 if arm == 'R' else 180.0
            self._phase = 'recording'
            self._traj  = [(self._cursor_y, self._cursor_z)]
            _beep(880, 80)

        elif self._phase == 'recording':
            self._end_recording()

    def _abort_to_wait_start(self):
        self._guide_angle = None
        self._traj        = []
        self._x_below_dur = 0.0
        self._phase       = 'wait_start'
        _beep(300, 150)

    def _in_start_circle(self):
        arm = self._trials[self._trial_idx]['arm']
        sp  = self._lateral_start_pts[arm]
        if sp is None:
            return False
        cy, cz = sp
        return (self._cursor_y - cy)**2 + (self._cursor_z - cz)**2 <= LATERAL_START_R**2

    def _on_shift_space(self):
        if self._phase not in ('wait_start', 'set_start', 'set_lateral'):
            return
        arm = self._trials[self._trial_idx]['arm']
        # save previous setup for ghost display
        if self._start_pts[arm] is not None:
            self._prev_setup[arm] = (
                self._start_pts[arm],
                self._lateral_lines[arm],
                self._lateral_start_pts[arm],
            )
        self._start_pts[arm]         = None
        self._lateral_lines[arm]     = None
        self._lateral_start_pts[arm] = None
        self._phase = 'set_start'
        _beep(440, 120)

    def _update_guide_angle(self):
        if self._guide_angle is None:
            return
        arm   = self._trials[self._trial_idx]['arm']
        speed = self.state.ws_guide_speed_R if arm == 'R' else self.state.ws_guide_speed_L
        delta = speed * self._dt
        if arm == 'R':
            self._guide_angle = min(180.0, self._guide_angle + delta)  # 0→180 (right→left)
        else:
            self._guide_angle = max(0.0, self._guide_angle - delta)    # 180→0 (left→right)

    def _end_recording(self):
        self._guide_angle = None
        self._show_pts   = list(self._traj)
        self._show_timer = 0.0
        arm = self._trials[self._trial_idx]['arm']
        sy  = self._start_pts[arm][0]
        lz  = self._lateral_lines[arm]
        sz  = lz if lz is not None else self._start_pts[arm][1]  # center Z = lateral line
        traj_clipped = [(y, z) for y, z in self._traj if lz is None or z >= lz]
        bins   = self._compute_bins(traj_clipped, sy, sz)
        self._pending_env = (bins, arm, sy, sz)
        pts = self._bins_to_pts(bins, sy, sz, close_z=lz)
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
        BIN_RAD = math.pi / N_BINS  # 3° per bin

        def _update(y, z):
            dy, dz = y - sy, z - sz
            if dz < 0:
                return
            r = math.sqrt(dy * dy + dz * dz)
            if r < 0.3:
                return
            idx = min(int(math.atan2(dz, dy) / math.pi * N_BINS), N_BINS - 1)
            if r > bins[idx]:
                bins[idx] = r

        for k, (y, z) in enumerate(traj):
            _update(y, z)
            if k == 0:
                continue
            py, pz = traj[k - 1]
            # interpolate along the segment so no bin is skipped
            dy1, dz1 = py - sy, pz - sz
            dy2, dz2 = y  - sy, z  - sz
            r1 = math.sqrt(dy1 * dy1 + dz1 * dz1)
            r2 = math.sqrt(dy2 * dy2 + dz2 * dz2)
            if r1 >= 0.3 and r2 >= 0.3:
                a1    = math.atan2(max(dz1, 0.0), dy1)
                a2    = math.atan2(max(dz2, 0.0), dy2)
                steps = max(2, int(abs(a2 - a1) / BIN_RAD) + 2)
            else:
                steps = 4
            for t in range(1, steps):
                fy = py + (y - py) * t / steps
                fz = pz + (z - pz) * t / steps
                _update(fy, fz)

        sm = [0.0] * N_BINS
        w  = SMOOTH_WIN
        for i in range(N_BINS):
            vals = [bins[max(0, min(N_BINS - 1, i + j))] for j in range(-w, w + 1)]
            sm[i] = sum(vals) / len(vals)
        return sm

    def _build_target_boundary(self, target_arm, testing_arm):
        env_list = self._envelopes[target_arm]
        if not env_list:
            self._target_bnd = None
            return
        avg  = [sum(e[0][i] for e in env_list) / len(env_list) for i in range(N_BINS)]
        self._target_bnd = (avg, target_arm, testing_arm)

    def _bins_to_pts(self, bins, sy, sz, mirror_start=None, close_z=None):
        pts = []
        center_y = mirror_start[0] if mirror_start is not None else sy
        for i, r in enumerate(bins):
            if r < 0.3:
                continue
            angle = (i + 0.5) * math.pi / N_BINS  # 1.5° … 178.5°
            dy = r * math.cos(angle)
            dz = r * math.sin(angle)
            if mirror_start is not None:
                my, mz = mirror_start
                pts.append((my - dy, mz + dz))
            else:
                pts.append((sy + dy, sz + dz))
        # 177-180° end → drop to lateral line → center → 1-3° end x on lateral
        # auto-close: (first_arc_x, close_z) → pts[0], nearly vertical
        if close_z is not None and len(pts) >= 2:
            first_y = pts[0][0]
            pts.append((pts[-1][0], close_z))
            pts.append((center_y,   close_z))
            pts.append((first_y,    close_z))
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

    def _r_px(self, r_cm):
        s  = self.state
        ry = self._ws.width()  / max(s.WORKSPACE_Y_MAX - s.WORKSPACE_Y_MIN, 0.01)
        rz = self._ws.height() / max(s.WORKSPACE_Z_MAX - s.WORKSPACE_Z_MIN, 0.01)
        return max(1, int(r_cm * ry)), max(1, int(r_cm * rz))

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
            self._draw_done_screen(p)
            return

        if self._phase == 'switch_hand':
            self._draw_switch(p)
            return

        trial = self._trials[self._trial_idx]
        arm   = trial['arm']
        lz    = self._lateral_lines[arm]

        # ── clipped region: above lateral line ──
        if lz is not None:
            _, line_y = self._to_screen(0, lz)
            p.setClipRect(0, 0, self.width(), line_y)

        self._draw_ghosts(p, arm)
        self._draw_target_boundary(p, arm)
        if self._phase == 'recording' and trial['draw']:
            self._draw_live_traj(p)
        elif self._phase == 'show_traj':
            self._draw_show_traj(p)

        if lz is not None:
            p.setClipping(False)
        # ── end clipped region ──

        self._draw_lateral_line(p, arm)
        self._draw_center_line(p, arm)
        self._draw_lateral_start_circle(p, arm)

        if self._phase == 'set_start':
            self._draw_prev_setup_ghost(p, arm)
            self._draw_instruction(p, "Position your center, then press SPACE.")
        elif self._phase == 'set_lateral':
            self._draw_prev_setup_ghost(p, arm)
            self._draw_instruction(p, "Extend arm to max lateral, then press SPACE.")
        elif self._phase == 'wait_start':
            trial = self._trials[self._trial_idx]
            elev_fail = trial['elev_min_cm'] > 0 and self._cursor_x < trial['elev_min_cm']
            if self._in_start_circle():
                if elev_fail:
                    self._draw_instruction(p, "Raise your hand!")
                else:
                    self._draw_instruction(p, "Ready for the cue.")
            else:
                self._draw_instruction(p, "Return to start position.")
                if elev_fail:
                    self._draw_warning(p, "Raise your hand!")
        elif self._phase == 'recording':
            self._draw_guide_line(p)
            self._draw_cursor_circle(p, arm)
            trial = self._trials[self._trial_idx]
            self._draw_instruction(p, "Follow the guideline. Reach as far as possible.")
            if trial['elev_min_cm'] > 0 and self._cursor_x < trial['elev_min_cm']:
                self._draw_warning(p, "Raise your hand!")
        elif self._phase == 'show_traj':
            self._draw_trial_area(p)

        self._draw_cursor(p)
        self._draw_counter(p, arm)
        self._draw_avg_info(p)

        if self._paused:
            self._draw_pause_overlay(p)

    def _draw_cursor(self, p):
        sx, sy = self._to_screen(self._cursor_y, self._cursor_z)
        trial = self._trials[self._trial_idx] if 0 <= self._trial_idx < len(self._trials) else None
        below = (trial and trial['elev_min_cm'] > 0 and self._cursor_x < trial['elev_min_cm'])
        color = QColor(220, 30, 30) if below else QColor(30, 200, 80)
        p.setBrush(QBrush(color))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPoint(sx, sy), 7, 7)
        if self.liberty.use_mouse:
            p.setPen(QColor(200, 200, 200))
            p.setFont(QFont('Arial', 10))
            p.drawText(sx + 10, sy + 14, f"x={self._cursor_x:.1f} cm")

    def _draw_prev_setup_ghost(self, p, arm):
        prev = self._prev_setup[arm]
        if prev is None:
            return
        start_pt, lateral_z, lateral_start_pt = prev
        alpha = 77  # 0.3 * 255

        # ghost center line
        cy, cz = start_pt
        x1, y1 = self._to_screen(cy, cz + 2.0)
        x2, y2 = self._to_screen(cy, self.state.WORKSPACE_Z_MIN)
        p.setPen(QPen(QColor(255, 255, 255, alpha), 2))
        p.drawLine(x1, y1, x2, y2)

        # ghost lateral line
        if lateral_z is not None:
            _, line_y = self._to_screen(0, lateral_z)
            p.setPen(QPen(QColor(160, 160, 160, alpha), 1))
            p.drawLine(0, line_y, self.width(), line_y)

        # ghost start circle
        if lateral_start_pt is not None:
            sy_c, sz_c = lateral_start_pt
            sx, sy_s = self._to_screen(sy_c, sz_c)
            rx, rz   = self._r_px(LATERAL_START_R)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(255, 255, 255, alpha), 2))
            p.drawEllipse(QPoint(sx, sy_s), rx, rz)

    def _draw_center_line(self, p, arm):
        sp = self._start_pts[arm]
        if sp is None:
            return
        cy, cz = sp
        x1, y1 = self._to_screen(cy, cz + 2.0)                  # 2 cm above center
        x2, y2 = self._to_screen(cy, self.state.WORKSPACE_Z_MIN) # down to workspace bottom
        p.setPen(QPen(QColor(255, 255, 255), 2))
        p.drawLine(x1, y1, x2, y2)

    def _draw_lateral_line(self, p, arm):
        lz = self._lateral_lines[arm]
        if lz is None:
            return
        _, line_y = self._to_screen(0, lz)
        p.setPen(QPen(QColor(160, 160, 160), 1))
        p.drawLine(0, line_y, self.width(), line_y)

    def _draw_lateral_start_circle(self, p, arm):
        sp = self._lateral_start_pts[arm]
        if sp is None:
            return
        cy, cz = sp
        sx, sy_s = self._to_screen(cy, cz)
        rx, rz   = self._r_px(LATERAL_START_R)
        inside   = ((self._cursor_y - cy)**2 + (self._cursor_z - cz)**2
                    <= LATERAL_START_R**2)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255), 4 if inside else 2))
        p.drawEllipse(QPoint(sx, sy_s), rx, rz)

    def _draw_ghosts(self, p, arm):
        env_list = self._envelopes[arm]
        if not env_list:
            return
        color = QColor(255, 255, 255, 128)
        lz    = self._lateral_lines[arm]

        if self.state.ws_ghost_mode == 'average':
            n   = len(env_list)
            avg = [sum(e[0][i] for e in env_list) / n for i in range(N_BINS)]
            sy, sz = env_list[-1][1], env_list[-1][2]
            pts = self._bins_to_pts(avg, sy, sz, close_z=lz)
            if len(pts) < 3:
                return
            poly = QPolygon([QPoint(*self._to_screen(y, z)) for y, z in pts])
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(color, 1))
            p.drawPolygon(poly)
        elif self.state.ws_ghost_mode == 'max':
            mx  = [max(e[0][i] for e in env_list) for i in range(N_BINS)]
            sy, sz = env_list[-1][1], env_list[-1][2]
            pts = self._bins_to_pts(mx, sy, sz, close_z=lz)
            if len(pts) < 3:
                return
            poly = QPolygon([QPoint(*self._to_screen(y, z)) for y, z in pts])
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(color, 1))
            p.drawPolygon(poly)
        else:
            n       = len(env_list)
            start_i = max(0, n - 5)
            for bins, sy, sz in env_list[start_i:]:
                pts = self._bins_to_pts(bins, sy, sz, close_z=lz)
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
        if self._start_pts[testing_arm] is None:
            return
        lz  = self._lateral_lines[testing_arm]
        sp_y = self._start_pts[testing_arm][0]
        mirror_pt = (sp_y, lz) if lz is not None else self._start_pts[testing_arm]
        pts = self._bins_to_pts(avg_bins, 0, 0, mirror_start=mirror_pt, close_z=lz)
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

    def _draw_warning(self, p, text):
        p.setPen(QColor(255, 80, 80))
        p.setFont(QFont('Arial', 22, QFont.Bold))
        p.drawText(self.rect().adjusted(0, 80, 0, 0), Qt.AlignTop | Qt.AlignHCenter, text)

    def _draw_instruction(self, p, text):
        p.setPen(QColor(200, 200, 200))
        p.setFont(QFont('Arial', 24, QFont.Bold))
        p.drawText(self.rect().adjusted(0, 40, 0, 0), Qt.AlignTop | Qt.AlignHCenter, text)

    def _draw_counter(self, p, arm):
        arm_text = "Right" if arm == 'R' else "Left"
        scale = self.state.env_scale()
        scale_str = f"{scale:.2f}".rstrip('0').rstrip('.')
        p.setPen(QColor(160, 160, 160))
        p.setFont(QFont('Arial', 14))
        p.drawText(20, 30, f"{scale_str}×   Trial  {self._trial_idx + 1} / {len(self._trials)}   Arm: {arm_text}")

    def _avg_str(self, a):
        vals = self._areas[a]
        if not vals:
            return "—"
        return f"{sum(vals) / len(vals):.1f} cm²  (n={len(vals)})"

    def _draw_trial_area(self, p):
        p.setPen(QColor(220, 220, 220))
        p.setFont(QFont('Arial', 20, QFont.Bold))
        p.drawText(self.rect().adjusted(0, 10, 0, 0),
                   Qt.AlignTop | Qt.AlignHCenter,
                   f"Area: {self._last_area:.1f} cm²")

    def _draw_avg_info(self, p):
        lines = f"R avg:  {self._avg_str('R')}\nL avg:  {self._avg_str('L')}"
        p.setPen(QColor(160, 160, 160))
        p.setFont(QFont('Arial', 14))
        p.drawText(self.rect().adjusted(0, 10, -20, 0),
                   Qt.AlignTop | Qt.AlignRight,
                   lines)

    def _draw_done_screen(self, p):
        self._draw_text(p, "Session complete!")
        # prominent results below center
        def line(a, label):
            vals = self._areas[a]
            if not vals:
                return f"{label}:  —"
            return f"{label}:  {sum(vals)/len(vals):.1f} cm²  (n={len(vals)})"
        results = f"{line('R', 'R avg')}\n{line('L', 'L avg')}"
        p.setPen(QColor(200, 200, 200))
        p.setFont(QFont('Arial', 26, QFont.Bold))
        p.drawText(self.rect().adjusted(0, 80, 0, 0),
                   Qt.AlignTop | Qt.AlignHCenter, results)
        p.setPen(QColor(120, 120, 120))
        p.setFont(QFont('Arial', 16))
        p.drawText(self.rect().adjusted(0, 0, 0, -30),
                   Qt.AlignBottom | Qt.AlignHCenter, "Press ESC to return to menu.")

    def _draw_switch(self, p):
        if 0 <= self._trial_idx < len(self._trials):
            arm_text = "Right" if self._trials[self._trial_idx]['arm'] == 'R' else "Left"
            msg = f"Switch hand.\n{arm_text} arm next."
        else:
            msg = "Switch hand."
        self._draw_text(p, msg)

    def _draw_cursor_circle(self, p, arm):
        if not self.state.ws_shadow_circle_on:
            return
        oz = self._lateral_lines[arm]
        if oz is None:
            return
        cx, cy = self._to_screen(self._cursor_y, oz)
        rx, rz = self._r_px(LATERAL_START_R * 0.72)
        p.setBrush(QBrush(QColor(50, 200, 80)))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPoint(cx, cy), rx, rz)

    def _draw_guide_line(self, p):
        if self._guide_angle is None:
            return
        arm = self._trials[self._trial_idx]['arm']
        if self._start_pts[arm] is None or self._lateral_lines[arm] is None:
            return
        oy = self._start_pts[arm][0]
        oz = self._lateral_lines[arm]
        angle_rad = math.radians(self._guide_angle)

        if self.state.ws_guide_line_on:
            sx, sy_s = self._to_screen(oy, oz)
            far_y = oy + math.cos(angle_rad) * 300
            far_z = oz + math.sin(angle_rad) * 300
            ex, ey = self._to_screen(far_y, far_z)
            p.setPen(QPen(QColor(200, 200, 200, 160), 1))
            p.drawLine(sx, sy_s, ex, ey)

        lsp = self._lateral_start_pts[arm]
        if lsp is None:
            return
        dy = lsp[0] - oy
        dz = lsp[1] - oz
        dist = math.sqrt(dy * dy + dz * dz)
        if dist <= 0.1:
            return

        if self.state.ws_guide_line_on:
            dot_y = oy + math.cos(angle_rad) * dist
            dot_z = oz + math.sin(angle_rad) * dist
            dx, dy_s = self._to_screen(dot_y, dot_z)
            p.setBrush(QBrush(QColor(255, 255, 255)))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPoint(dx, dy_s), 6, 6)

        if self.state.ws_shadow_circle_on:
            shadow_y = oy + math.cos(angle_rad) * dist
            shx, shy = self._to_screen(shadow_y, oz)
            rx, rz = self._r_px(LATERAL_START_R * 0.8)
            p.setBrush(QBrush(QColor(255, 255, 255)))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPoint(shx, shy), rx, rz)

    def _draw_pause_overlay(self, p):
        from PyQt5.QtCore import QRect as _QRect
        p.fillRect(self.rect(), QColor(0, 0, 0, 160))
        box_w, box_h = 260, 100
        cx = (self.width()  - box_w) // 2
        cy = (self.height() - box_h) // 2
        p.setBrush(QBrush(QColor(30, 30, 30)))
        p.setPen(QPen(QColor(180, 180, 180), 2))
        p.drawRect(cx, cy, box_w, box_h)
        # blink "PAUSE" at ~2 Hz
        if int(time.perf_counter() * 2) % 2 == 0:
            p.setPen(QColor(220, 220, 220))
            p.setFont(QFont('Arial', 32, QFont.Bold))
            p.drawText(_QRect(cx, cy, box_w, box_h), Qt.AlignCenter, "PAUSE")
        p.setPen(QColor(180, 180, 180))
        p.setFont(QFont('Arial', 13, QFont.Bold))
        p.drawText(_QRect(0, cy + box_h + 14, self.width(), 24), Qt.AlignCenter, "SPACE to resume")
        p.drawText(_QRect(0, cy + box_h + 40, self.width(), 24), Qt.AlignCenter, "ESC to end the session")

    def _draw_text(self, p, text):
        p.setPen(QColor(220, 220, 220))
        p.setFont(QFont('Arial', 36, QFont.Bold))
        p.drawText(self.rect(), Qt.AlignCenter, text)
