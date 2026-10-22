import math
import time
import threading
from datetime import datetime
from screens._beep import beep
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QTimer, QRect, QPoint
from PyQt5.QtGui import QPainter, QColor, QBrush, QFont, QPen
from tasks.reaching import recorder


def _beep(freq, ms):
    threading.Thread(target=beep, args=(freq, ms), daemon=True).start()

def _beep_seq(*pairs):
    def _run():
        for freq, ms in pairs:
            beep(freq, ms)
    threading.Thread(target=_run, daemon=True).start()


HOME_RADIUS_CM = 3.0   # 3 cm home zone
FEEDBACK_S     = 1.0   # GOOD/BAD display time


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

        self._ws      = QRect()
        self._cursor_y  = 0.0   # cm
        self._cursor_z  = 0.0   # cm
        self._cursor_in_ws = True

        self._phase   = 'calibration'
        self._home_x  = None   # MCP height at calibration (Liberty x), recorded only
        self._home_y  = 0.0
        self._home_z  = 0.0
        self._trials  = []
        self._trial_idx = -1
        self._trial   = None

        # trial state machine
        self._t_state          = None
        self._hold_elapsed     = 0.0
        self._ready_elapsed    = 0.0
        self._exec_elapsed     = 0.0
        self._feedback_elapsed = 0.0
        self._outcome_good     = False
        self._go_cue_elapsed   = 0.0
        self._last_cursor_y    = 0.0
        self._last_cursor_z    = 0.0
        self._ready_ms         = None   # last ShowDirection entry, ms from trial start
        self._go_ms            = None   # last Executing entry, ms from trial start

        self._paused    = False
        self._dt        = 0.004
        self._last_tick = time.perf_counter()

        # data recording
        self._session_dir     = None
        self._session_index   = None
        self._samples         = []
        self._trial_start_t   = 0.0
        self._last_landmarks  = {}

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(4)

    # ------------------------------------------------------------------ events

    def showEvent(self, e):
        self._timer.start(max(1, round(1000 / self.state.sample_rate_hz)))
        self._phase    = 'calibration'
        self._paused   = False
        self._cursor_y = self.state.WORKSPACE_Y_MAX / 2
        self._cursor_z = self.state.WORKSPACE_Z_MAX / 2
        self._calib_hand    = self._peek_first_hand()
        self._session_dir   = None
        self._session_index = None

    def hideEvent(self, e):
        self._timer.stop()
        self._paused = False

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            if self._paused:
                self._paused = False
                self.mw.show_screen('menu')
            elif self._phase == 'running':
                self._paused = True
            else:
                self.mw.show_screen('menu')
            return
        if self._paused:
            if e.key() == Qt.Key_Space:
                self._paused = False
            return
        if e.key() == Qt.Key_Space and self._phase == 'calibration':
            self._confirm_calibration()

    def mouseMoveEvent(self, e):
        if self.liberty.use_mouse and self._ws.width() > 0:
            self._cursor_y, self._cursor_z = self._to_cm(e.x(), e.y())
            self._cursor_in_ws = True

    # ------------------------------------------------------------------ tick

    def _tick(self):
        now = time.perf_counter()
        self._dt = now - self._last_tick
        self._last_tick = now
        if self._paused:
            self.update()
            return
        if not self.liberty.use_mouse:
            self._read_sensor()
        if self._phase == 'running' and self._t_state:
            if not self.liberty.use_mouse:
                self._record_sample()
            self._update_trial()
        self.update()

    def _current_hand(self):
        if self._trial is not None:
            return self._trial['hand']
        return getattr(self, '_calib_hand', 'right')

    def _peek_first_hand(self):
        from tasks.reaching_task import SESSIONS_SCREEN
        s_scr = self.mw.screens.get(SESSIONS_SCREEN)
        if s_scr and s_scr.table.rowCount() > 0:
            row  = max(0, min(self.state.start_trial - 1, s_scr.table.rowCount() - 1))
            item = s_scr.table.item(row, 1)
            if item and item.text().strip() == '2':
                return 'left'
        return 'right'

    def _read_sensor(self):
        st   = self.state
        hand = self._current_hand()
        landmarks = recorder.live_landmarks(st, self.liberty, hand)
        mcp = landmarks.get('mcp')
        if mcp is None:
            sensor_n = st.dig_sensor_right if hand == 'right' else st.dig_sensor_left
            s = self.liberty.get_sensor(sensor_n)
            if s is None:
                return
            mcp = [s.x * 2.54, s.y * 2.54, s.z * 2.54]
        y = mcp[1] - st.sensor_y_offset
        z = mcp[2] - st.sensor_z_offset
        self._cursor_in_ws = (st.WORKSPACE_Y_MIN <= y <= st.WORKSPACE_Y_MAX and
                              st.WORKSPACE_Z_MIN <= z <= st.WORKSPACE_Z_MAX)
        self._cursor_y = max(st.WORKSPACE_Y_MIN, min(st.WORKSPACE_Y_MAX, y))
        self._cursor_z = max(st.WORKSPACE_Z_MIN, min(st.WORKSPACE_Z_MAX, z))
        self._last_landmarks = {
            lm: [pos[0] - st.sensor_x_offset, pos[1] - st.sensor_y_offset, pos[2] - st.sensor_z_offset]
            for lm, pos in landmarks.items()
        }

    def _trial_ms(self):
        return (time.perf_counter() - self._trial_start_t) * 1000.0

    def _record_sample(self):
        t_ms = self._trial_ms()
        self._samples.append((
            t_ms, self._t_state, self._cursor_y, self._cursor_z,
            dict(self._last_landmarks),
        ))

    def _write_trial_file(self):
        if self._session_dir is None:
            self._session_index, self._session_dir = recorder.ensure_session_dir(self.state)
        t    = self._trial
        now  = datetime.now()
        # Shared output format: positions in cm, Liberty frame converted by the
        # recorder (to_output_axes); trial numbers are the session table row,
        # 1-based, shared by both hands.
        start_pos  = recorder.to_output_axes([self._home_x, self._home_y, self._home_z])
        target_pos = recorder.to_output_axes([self._home_x, t['target_y'], t['target_z']])
        meta = {
            'format_version':   recorder.FORMAT_VERSION,
            'system':           'reachlab',
            'date':             now.strftime('%Y-%m-%d'),
            'time':             now.strftime('%H:%M:%S'),
            'participant_id':   self.state.participant_id or '',
            'session_index':    self._session_index,
            'trial_index':      t['row'],
            'used_hand':        t['hand'],
            'instruction':      t['instruction'],
            'target_id':        t['target_id'],
            'start_pos_cm':     start_pos,
            'start_radius_cm':  HOME_RADIUS_CM,
            'target_pos_cm':    target_pos,
            'target_radius_cm': t['target_r'],
            'hold_s':           t['hold_s'],
            'wait_s':           t['wait_s'],
            'move_s':           t['move_s'],
            'feedback_s':       FEEDBACK_S,
            'ready_ms':         self._ready_ms,
            'go_ms':            self._go_ms,
            'outcome':          'GOOD' if self._outcome_good else 'BAD',
            'axes':             recorder.AXES,
            'origin':           recorder.ORIGIN,
            'dig_mode':         self.state.dig_mode,
            'target_angle_deg': t['target_angle_deg'],
            'target_dist_cm':   t['target_dist_cm'],
        }
        recorder.write_trial(self._session_dir, t['row'], t['hand'], meta, self._samples)

    # ------------------------------------------------------------------ calibration

    def _confirm_calibration(self):
        mcp = self._last_landmarks.get('mcp')
        self._home_x = mcp[0] if mcp else None
        self._home_y = self._cursor_y
        self._home_z = self._cursor_z
        self._build_trials()
        if not self._trials:
            return
        self._phase = 'running'
        # "Start from trial N" (menu): skip to the first trial at or after
        # session table row N. _start_next_trial() advances by one first.
        first = next((i for i, tr in enumerate(self._trials)
                      if tr['row'] >= self.state.start_trial), len(self._trials))
        self._trial_idx = first - 1
        self._start_next_trial()

    # ------------------------------------------------------------------ build trials

    def _build_trials(self):
        from tasks.reaching_task import TARGETS_SCREEN, SESSIONS_SCREEN
        t_scr = self.mw.screens.get(TARGETS_SCREEN)
        s_scr = self.mw.screens.get(SESSIONS_SCREEN)
        if not t_scr or not s_scr:
            return

        targets = {}
        for r in range(t_scr.table.rowCount()):
            tid   = t_scr.table.item(r, 0).text().strip()
            angle = float(t_scr.table.item(r, 1).text())
            dist  = float(t_scr.table.item(r, 2).text())
            diam  = float(t_scr.table.item(r, 3).text())
            targets[tid] = (angle, dist, diam)

        self._trials = []
        for r in range(s_scr.table.rowCount()):
            hand   = 'left' if s_scr.table.item(r, 1).text().strip() == '2' else 'right'
            tid    = s_scr.table.item(r, 2).text().strip()
            hold_s = float(s_scr.table.item(r, 3).text())
            wait_s = float(s_scr.table.item(r, 4).text())
            move_s = float(s_scr.table.item(r, 5).text())
            inst   = int(s_scr.table.item(r, 6).text())
            if tid not in targets:
                continue
            angle_deg, dist_cm, diam_cm = targets[tid]

            # 0° = right (+Y), 90° = forward (+Z)
            rad = math.radians(angle_deg)
            ty  = self._home_y + dist_cm * math.cos(rad)
            tz  = self._home_z + dist_cm * math.sin(rad)

            self._trials.append({
                'row':              r + 1,   # 1-based session table row = trial number
                'hand':             hand,
                'target_id':        tid,
                'target_angle_deg': angle_deg,
                'target_dist_cm':   dist_cm,
                'target_diam_cm':   diam_cm,
                'target_y':    ty,
                'target_z':    tz,
                'target_r':    diam_cm / 2,
                'hold_s':      hold_s,
                'wait_s':      wait_s,
                'move_s':      move_s,
                'instruction': inst,
            })

    # ------------------------------------------------------------------ state machine

    def _start_next_trial(self):
        self._trial_idx += 1
        if self._trial_idx >= len(self._trials):
            self._phase = 'done'
            return
        self._trial            = self._trials[self._trial_idx]
        self._t_state          = 'MoveToStart'
        self._hold_elapsed     = 0.0
        self._ready_elapsed    = 0.0
        self._exec_elapsed     = 0.0
        self._feedback_elapsed = 0.0
        self._outcome_good     = False
        self._go_cue_elapsed   = 0.0
        self._last_cursor_y    = self._cursor_y
        self._last_cursor_z    = self._cursor_z
        self._ready_ms         = None
        self._go_ms            = None
        self._samples          = []
        self._trial_start_t    = time.perf_counter()

    def _in_zone(self, cy, cz, zy, zz, r):
        return (cy - zy) ** 2 + (cz - zz) ** 2 <= r ** 2

    def _update_trial(self):
        t  = self._trial
        cy = self._cursor_y
        cz = self._cursor_z

        if self._t_state == 'MoveToStart':
            if self._in_zone(cy, cz, self._home_y, self._home_z, HOME_RADIUS_CM):
                self._t_state      = 'HoldInStart'
                self._hold_elapsed = 0.0
                _beep(440, 80)

        elif self._t_state == 'HoldInStart':
            if not self._in_zone(cy, cz, self._home_y, self._home_z, HOME_RADIUS_CM):
                self._t_state = 'MoveToStart'
            else:
                self._hold_elapsed += self._dt
                if self._hold_elapsed >= t['hold_s']:
                    self._t_state       = 'ShowDirection'
                    self._ready_elapsed = 0.0
                    self._ready_ms      = self._trial_ms()

        elif self._t_state == 'ShowDirection':
            if not self._in_zone(cy, cz, self._home_y, self._home_z, HOME_RADIUS_CM):
                self._t_state = 'MoveToStart'
            else:
                self._ready_elapsed += self._dt
                if self._ready_elapsed >= t['wait_s']:
                    self._t_state        = 'Executing'
                    self._exec_elapsed   = 0.0
                    self._go_ms          = self._trial_ms()
                    self._go_cue_elapsed = 0.0
                    _beep(880, 100)

        elif self._t_state == 'Executing':
            self._go_cue_elapsed += self._dt
            self._exec_elapsed   += self._dt
            self._last_cursor_y   = cy
            self._last_cursor_z   = cz
            if self._exec_elapsed >= t['move_s']:
                self._outcome_good     = self._in_zone(cy, cz, t['target_y'], t['target_z'], t['target_r'])
                self._t_state          = 'Feedback'
                self._feedback_elapsed = 0.0
                if self._outcome_good:
                    _beep_seq((784, 80), (1047, 100))
                else:
                    _beep_seq((330, 80), (220, 150))

        elif self._t_state == 'Feedback':
            self._feedback_elapsed += self._dt
            if self._feedback_elapsed >= FEEDBACK_S:
                if not self.liberty.use_mouse:
                    self._write_trial_file()
                self._start_next_trial()

    # ------------------------------------------------------------------ coordinates

    def _recompute_ws(self):
        aw = self.width()  - 2 * self.MARGIN
        ah = self.height() - 2 * self.MARGIN
        self._ws = QRect(self.MARGIN, self.MARGIN, aw, ah)

    def _to_screen(self, y_cm, z_cm):
        s  = self.state
        px = self._ws.left()   + (y_cm - s.WORKSPACE_Y_MIN) / (s.WORKSPACE_Y_MAX - s.WORKSPACE_Y_MIN) * self._ws.width()
        py = self._ws.bottom() - (z_cm - s.WORKSPACE_Z_MIN) / (s.WORKSPACE_Z_MAX - s.WORKSPACE_Z_MIN) * self._ws.height()
        return int(px), int(py)

    def _to_cm(self, px, py):
        s = self.state
        y = s.WORKSPACE_Y_MIN + (px - self._ws.left())   / self._ws.width()  * (s.WORKSPACE_Y_MAX - s.WORKSPACE_Y_MIN)
        z = s.WORKSPACE_Z_MIN + (self._ws.bottom() - py) / self._ws.height() * (s.WORKSPACE_Z_MAX - s.WORKSPACE_Z_MIN)
        return (max(s.WORKSPACE_Y_MIN, min(s.WORKSPACE_Y_MAX, y)),
                max(s.WORKSPACE_Z_MIN, min(s.WORKSPACE_Z_MAX, z)))

    def _r_px(self, r_cm):
        s  = self.state
        sy = self._ws.width()  / (s.WORKSPACE_Y_MAX - s.WORKSPACE_Y_MIN)
        sz = self._ws.height() / (s.WORKSPACE_Z_MAX - s.WORKSPACE_Z_MIN)
        return max(1, int(r_cm * sy)), max(1, int(r_cm * sz))

    # ------------------------------------------------------------------ drawing

    def paintEvent(self, e):
        self._recompute_ws()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(0, 0, 0))

        if self._phase == 'calibration':
            self._draw_calibration(p)
        elif self._phase == 'running':
            self._draw_running(p)
        elif self._phase == 'done':
            self._draw_done(p)

        if self._paused:
            self._draw_pause_overlay(p)

    def _draw_cursor(self, p):
        if not self._cursor_in_ws:
            return
        sx, sy = self._to_screen(self._cursor_y, self._cursor_z)
        p.setBrush(QBrush(QColor(220, 30, 30)))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPoint(sx, sy), 8, 8)

    def _draw_calibration(self, p):
        self._draw_cursor(p)
        p.setPen(QColor(220, 220, 220))
        p.setFont(QFont('Arial', 26, QFont.Bold))
        p.drawText(self.rect(), Qt.AlignCenter,
                   "Set your home position.\nPress SPACE to confirm.")

    def _draw_running(self, p):
        t = self._trial
        in_home = self._in_zone(self._cursor_y, self._cursor_z,
                                self._home_y, self._home_z, HOME_RADIUS_CM)

        # Home circle
        hsx, hsy = self._to_screen(self._home_y, self._home_z)
        hrx, hrz = self._r_px(HOME_RADIUS_CM)
        if self._t_state in ('ShowDirection', 'Executing'):
            p.setBrush(QBrush(QColor(255, 255, 255)))
            p.setPen(QPen(QColor(255, 255, 255), 4))
        elif in_home:
            p.setBrush(QBrush(QColor(160, 160, 160)))
            p.setPen(QPen(QColor(255, 255, 255), 4))
        else:
            p.setBrush(QBrush(QColor(160, 160, 160)))
            p.setPen(Qt.NoPen)
        p.drawEllipse(QPoint(hsx, hsy), hrx, hrz)

        # Instruction text — ShowDirection only, bottom center
        if self._t_state == 'ShowDirection':
            inst_text = "REACH" if t['instruction'] == 1 else "REST"
            p.setPen(QColor(255, 255, 255))
            p.setFont(QFont('Arial', 36, QFont.Bold))
            p.drawText(self.rect().adjusted(0, 0, 0, -20), Qt.AlignBottom | Qt.AlignHCenter, inst_text)

        # Go cue — first 0.6 s of Executing, bottom center (same position as instruction)
        if self._t_state == 'Executing' and self._go_cue_elapsed < 0.6:
            p.setPen(QColor(255, 255, 255))
            p.setFont(QFont('Arial', 36, QFont.Bold))
            p.drawText(self.rect().adjusted(0, 0, 0, -20), Qt.AlignBottom | Qt.AlignHCenter, "GO!")

        # Target circle — open ring, hidden during Feedback
        if self._t_state in ('MoveToStart', 'HoldInStart', 'ShowDirection', 'Executing'):
            tsx, tsy = self._to_screen(t['target_y'], t['target_z'])
            trx, trz = self._r_px(t['target_r'])
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(120, 120, 120), 4))
            p.drawEllipse(QPoint(tsx, tsy), trx, trz)

        # Feedback — frozen cursor + GOOD/BAD
        if self._t_state == 'Feedback':
            fx, fy = self._to_screen(self._last_cursor_y, self._last_cursor_z)
            p.setBrush(QBrush(QColor(220, 30, 30)))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPoint(fx, fy), 8, 8)
            color = QColor(0, 200, 80) if self._outcome_good else QColor(220, 40, 40)
            p.setPen(color)
            p.setFont(QFont('Arial', 36, QFont.Bold))
            outcome_text = "GOOD" if self._outcome_good else "BAD"
            p.drawText(self.rect().adjusted(0, 20, 0, 0), Qt.AlignTop | Qt.AlignHCenter, outcome_text)

        # Trial counter
        scale = self.state.env_scale()
        scale_str = f"{scale:.2f}".rstrip('0').rstrip('.')
        p.setPen(QColor(160, 160, 160))
        p.setFont(QFont('Arial', 14))
        p.drawText(20, 30, f"{scale_str}×   Trial  {self._trial_idx + 1} / {len(self._trials)}")

        # Live cursor (not during Feedback)
        if self._t_state != 'Feedback':
            self._draw_cursor(p)

    def _draw_done(self, p):
        p.setPen(QColor(220, 220, 220))
        p.setFont(QFont('Arial', 30, QFont.Bold))
        p.drawText(self.rect(), Qt.AlignCenter,
                   "Session complete!\nPress ESC to return to menu.")

    def _draw_pause_overlay(self, p):
        from PyQt5.QtCore import QRect as _QRect
        p.fillRect(self.rect(), QColor(0, 0, 0, 160))
        box_w, box_h = 260, 100
        cx = (self.width()  - box_w) // 2
        cy = (self.height() - box_h) // 2
        p.setBrush(QBrush(QColor(30, 30, 30)))
        p.setPen(QPen(QColor(180, 180, 180), 2))
        p.drawRect(cx, cy, box_w, box_h)
        if int(time.perf_counter() * 2) % 2 == 0:
            p.setPen(QColor(220, 220, 220))
            p.setFont(QFont('Arial', 32, QFont.Bold))
            p.drawText(_QRect(cx, cy, box_w, box_h), Qt.AlignCenter, "PAUSE")
        p.setPen(QColor(180, 180, 180))
        p.setFont(QFont('Arial', 13, QFont.Bold))
        p.drawText(_QRect(0, cy + box_h + 14, self.width(), 24), Qt.AlignCenter, "SPACE to resume")
        p.drawText(_QRect(0, cy + box_h + 40, self.width(), 24), Qt.AlignCenter, "ESC to end the session")
