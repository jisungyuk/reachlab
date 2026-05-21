import math
import time
import threading
import winsound
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QTimer, QRect, QPoint
from PyQt5.QtGui import QPainter, QColor, QBrush, QFont, QPen


def _beep(freq, ms):
    threading.Thread(target=winsound.Beep, args=(freq, ms), daemon=True).start()

def _beep_seq(*pairs):
    def _run():
        for freq, ms in pairs:
            winsound.Beep(freq, ms)
    threading.Thread(target=_run, daemon=True).start()


HOME_RADIUS_CM = 3.0   # 3 cm home zone


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

        self._dt        = 0.008
        self._last_tick = time.perf_counter()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(8)

    # ------------------------------------------------------------------ events

    def showEvent(self, e):
        self._phase    = 'calibration'
        self._cursor_y = self.state.WORKSPACE_Y_MAX / 2
        self._cursor_z = self.state.WORKSPACE_Z_MAX / 2

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.mw.show_screen('menu')
        elif e.key() == Qt.Key_Space and self._phase == 'calibration':
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
        if not self.liberty.use_mouse:
            self._read_sensor()
        if self._phase == 'running' and self._t_state:
            self._update_trial()
        self.update()

    def _read_sensor(self):
        from digitizer import track_mcp
        st = self.state
        if st.dig_mode >= 1 and st.mcp_offset_right is not None:
            s = self.liberty.get_sensor(st.dig_sensor_right)
            if s is None:
                return
            pos = track_mcp(s, st.mcp_offset_right)
            y = pos[1] - st.sensor_y_offset
            z = pos[2] - st.sensor_z_offset
        else:
            s = self.liberty.get_sensor(st.dig_sensor_right)
            if s is None:
                return
            y = s.y * 2.54 - st.sensor_y_offset
            z = s.z * 2.54 - st.sensor_z_offset
        self._cursor_in_ws = (st.WORKSPACE_Y_MIN <= y <= st.WORKSPACE_Y_MAX and
                              st.WORKSPACE_Z_MIN <= z <= st.WORKSPACE_Z_MAX)
        self._cursor_y = max(st.WORKSPACE_Y_MIN, min(st.WORKSPACE_Y_MAX, y))
        self._cursor_z = max(st.WORKSPACE_Z_MIN, min(st.WORKSPACE_Z_MAX, z))

    # ------------------------------------------------------------------ calibration

    def _confirm_calibration(self):
        self._home_y = self._cursor_y
        self._home_z = self._cursor_z
        self._build_trials()
        if not self._trials:
            return
        self._phase = 'running'
        self._trial_idx = -1
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

        elif self._t_state == 'ShowDirection':
            if not self._in_zone(cy, cz, self._home_y, self._home_z, HOME_RADIUS_CM):
                self._t_state = 'MoveToStart'
            else:
                self._ready_elapsed += self._dt
                if self._ready_elapsed >= t['wait_s']:
                    self._t_state        = 'Executing'
                    self._exec_elapsed   = 0.0
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
            if self._feedback_elapsed >= 1.0:
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

        # Target circle — always shown during trial
        if self._t_state in ('MoveToStart', 'HoldInStart', 'ShowDirection', 'Executing', 'Feedback'):
            tsx, tsy = self._to_screen(t['target_y'], t['target_z'])
            trx, trz = self._r_px(t['target_r'])
            p.setBrush(QBrush(QColor(120, 120, 120)))
            p.setPen(Qt.NoPen)
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
        p.setPen(QColor(160, 160, 160))
        p.setFont(QFont('Arial', 14))
        p.drawText(20, 30, f"Trial  {self._trial_idx + 1} / {len(self._trials)}")

        # Live cursor (not during Feedback)
        if self._t_state != 'Feedback':
            self._draw_cursor(p)

    def _draw_done(self, p):
        p.setPen(QColor(220, 220, 220))
        p.setFont(QFont('Arial', 30, QFont.Bold))
        p.drawText(self.rect(), Qt.AlignCenter,
                   "Session complete!\nPress ESC to return to menu.")
