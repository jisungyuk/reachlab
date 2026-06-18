import json
import os
import threading
from screens._beep import beep
from collections import Counter
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QLabel, QComboBox, QPushButton, QFrame, QScrollArea,
                             QFileDialog, QMessageBox, QCheckBox)
from PyQt5.QtCore import Qt, QTimer, QPointF
from PyQt5.QtGui import QFont, QKeySequence, QPainter, QPen, QColor
from PyQt5.QtWidgets import QShortcut

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
    ('Cursor          (Mode 0)',  0),
    ('MCP             (Mode 1)',  1),
    ('Wrist           (Mode 2)',  2),
    ('Full Arm        (Mode 3)',  3),
    ('Full Single Arm (Mode 4)',  4),
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

_LM_IDX = {'MCP': 1, 'RSP': 2, 'USP': 3, 'ME': 4, 'LE': 5}

# Mode 3: Full Arm landmarks
ARM_LANDMARKS = ['MCP', 'RSP', 'USP', 'ME', 'LE', 'AP']
ARM_LM_FULL = {
    'MCP': 'MCP (metacarpal)',
    'RSP': 'RSP (radial styloid)',
    'USP': 'USP (ulnar styloid)',
    'ME':  'ME  (medial epicondyle)',
    'LE':  'LE  (lateral epicondyle)',
    'AP':  'AP  (acromion process)',
}
_ARM_LM_IDX = {'MCP': 1, 'RSP': 2, 'USP': 3, 'ME': 4, 'LE': 5, 'AP': 6}

# Mode 4: Full Single Arm landmarks
ARM4_LANDMARKS = ['MCP', 'USP', 'RSP', 'LE', 'ME', 'AP', 'AP_opp']
ARM4_LM_FULL = {
    'MCP':    'MCP (metacarpal)',
    'USP':    'USP (ulnar styloid)',
    'RSP':    'RSP (radial styloid)',
    'LE':     'LE  (lateral epicondyle)',
    'ME':     'ME  (medial epicondyle)',
    'AP':     'AP  (acromion process)',
    'AP_opp': 'AP_opp (opposite acromion)',
}
_ARM4_LM_IDX = {'MCP': 1, 'USP': 2, 'RSP': 3, 'LE': 4, 'ME': 5, 'AP': 6, 'AP_opp': 7}

_VIEW_RATIO = 0.30  # display at 30% of real size


def _beep_complete():
    """Ascending C-major arpeggio — played in a background thread."""
    for freq, dur in [(523, 80), (659, 80), (784, 80), (1047, 280)]:
        beep(freq, dur)

C_RIGHT = QColor(210, 50,  50)
C_LEFT  = QColor(50,  80, 210)
C_TRUNK = QColor(50,  160, 80)


class _DigCanvas(QWidget):
    """Top-down 2-D view: Y = left/right, Z = front/back (player at top)."""

    def __init__(self, state, liberty, dig_screen=None):
        super().__init__()
        self.state      = state
        self.liberty    = liberty
        self.dig_screen = dig_screen
        self.setMinimumHeight(650)
        self.setAttribute(Qt.WA_OpaquePaintEvent)

    def paintEvent(self, _):
        from digitizer import track_mcp

        p   = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(250, 250, 250))

        W, H = self.width(), self.height()
        PAD  = 24
        st   = self.state
        dw, dh = st.env_desk_w, st.env_desk_h   # cm
        import math

        # Physical scale: display at 30% of real size, derived from monitor settings
        _RATIOS = [(16, 9), (16, 10), (4, 3), (21, 9)]
        r = _RATIOS[min(st.env_mon_ratio_idx, len(_RATIOS) - 1)]
        diag_in = st.env_mon_size
        w_in = diag_in * r[0] / math.sqrt(r[0]**2 + r[1]**2)
        from PyQt5.QtWidgets import QApplication
        scr = QApplication.primaryScreen()
        ppi = scr.geometry().width() / max(w_in, 1)
        _ppc = ppi / 2.54
        scale = _ppc * _VIEW_RATIO

        rx = st.env_rect_x

        # Align monitor rect to top-center if configured, otherwise center on desk
        if rx is not None:
            mon_cx_cm = rx + st.env_rect_w / 2
            ox = W / 2 - mon_cx_cm * scale
            oy = PAD - (dh - st.env_rect_y - st.env_rect_h) * scale
        else:
            ox = PAD + (W - 2*PAD - dw * scale) / 2
            oy = PAD + (H - 2*PAD - dh * scale) / 2

        def px(y_cm, z_cm):
            return QPointF(ox + y_cm * scale, oy + (dh - z_cm) * scale)

        def _sh(s):   return s.y * 2.54 - st.sensor_y_offset
        def _sv(s):   return s.z * 2.54 - st.sensor_z_offset
        def _ph(pos): return pos[1] - st.sensor_y_offset
        def _pv(pos): return pos[2] - st.sensor_z_offset

        # Monitor rect
        if rx is not None:
            mon_x = int(ox + rx * scale)
            mon_y = int(oy + (dh - st.env_rect_y - st.env_rect_h) * scale)
            mon_w = int(st.env_rect_w * scale)
            mon_h = int(st.env_rect_h * scale)
            p.setPen(QPen(QColor(100, 100, 190), 1))
            p.setBrush(QColor(190, 210, 255, 150))
            p.drawRect(mon_x, mon_y, mon_w, mon_h)
            p.setPen(QColor(100, 100, 190))
            p.setBrush(Qt.NoBrush)
            p.setFont(QFont('Arial', 9))
            p.drawText(QPointF(mon_x + 4, mon_y + 13), "monitor rect")

        # Sensors + MCPs — mode-aware
        mode = st.dig_mode
        if mode == 2:
            sides = [
                ('right', st.wrist_sensor_R_hand,    st.wrist_R_MCP, C_RIGHT),
                ('left',  st.wrist_sensor_L_hand,    st.wrist_L_MCP, C_LEFT),
                ('right', st.wrist_sensor_R_ptr,     None,           C_RIGHT),
                ('left',  st.wrist_sensor_L_forearm, None,           C_LEFT),
            ]
        elif mode == 3:
            sides = [
                ('right', st.arm_sensor_R_forearm, st.arm_R_MCP, C_RIGHT),
                ('left',  st.arm_sensor_L_forearm, st.arm_L_MCP, C_LEFT),
                ('right', st.arm_sensor_R_ptr,     None,         C_RIGHT),
                ('left',  st.arm_sensor_L_upper,   None,         C_LEFT),
            ]
        elif mode == 4:
            side_color = C_RIGHT if st.dig_hand_setup == 0 else C_LEFT
            sides = [
                ('s', st.arm4_sensor_hand,    st.arm4_MCP, side_color),
                ('s', st.arm4_sensor_forearm, None,        side_color),
                ('s', st.arm4_sensor_upper,   None,        side_color),
                ('s', st.arm4_sensor_trunk,   None,        side_color),
            ]
        elif mode == 1:
            C_PTR = QColor(120, 120, 120)
            sides = [
                ('right', st.dig_sensor_right,    st.mcp_offset_right, C_RIGHT),
                ('left',  st.dig_sensor_left,     st.mcp_offset_left,  C_LEFT),
                ('ptr',   st.mcp_sensor_pointer,  None,                C_PTR),
            ]
        else:
            sides = [
                ('right', st.dig_sensor_right, st.mcp_offset_right, C_RIGHT),
                ('left',  st.dig_sensor_left,  st.mcp_offset_left,  C_LEFT),
            ]
            if st.dig_trunk_enabled:
                sides.append(('trunk', st.dig_sensor_trunk, None, C_TRUNK))
        for _, s_n, offset, color in sides:
            s = self.liberty.get_sensor(s_n)
            if s is None:
                continue
            sp  = px(_sh(s), _sv(s))

            # Sensor dot
            p.setPen(QPen(color.darker(130), 1))
            p.setBrush(color)
            p.drawEllipse(sp, 5, 5)

            # Label
            p.setPen(color.darker(160))
            p.setFont(QFont('Arial', 9, QFont.Bold))
            p.drawText(QPointF(sp.x() + 7, sp.y() + 4), f"S{s_n}")

            if offset is None:
                continue

            pos = track_mcp(s, offset)
            mp  = px(_ph(pos), _pv(pos))

            # Line sensor → MCP
            p.setPen(QPen(color, 1))
            p.drawLine(sp, mp)

            # MCP dot (hollow-ish)
            p.setPen(QPen(color.darker(130), 1))
            p.setBrush(color.lighter(170))
            p.drawEllipse(mp, 4, 4)

            p.setPen(color.darker(160))
            p.setFont(QFont('Arial', 9))
            p.drawText(QPointF(mp.x() + 6, mp.y() + 4), "MCP")

        # ── Mode 2 extra: RSP/USP/ME/LE dots + skeleton ──────
        if mode == 2:
            dig    = self.dig_screen
            r_tmp  = dig._wrist_R_tmp if dig is not None else {}

            def get_lm_pt(sensor_n, offset):
                if offset is None:
                    return None
                s = self.liberty.get_sensor(sensor_n)
                if s is None:
                    return None
                pos = track_mcp(s, offset)
                return px(_ph(pos), _pv(pos))

            def sensor_canvas_pt(sensor_n):
                s = self.liberty.get_sensor(sensor_n)
                if s is None:
                    return None
                return px(_sh(s), _sv(s))

            # Build landmark list: (side_key, lm, sensor_n, offset, color)
            # Left: MCP in L.Hand frame; RSP/USP/ME/LE all in L.Forearm frame
            lm_specs = []
            for lm, s_n in [('RSP', st.wrist_sensor_L_forearm),
                             ('USP', st.wrist_sensor_L_forearm),
                             ('ME',  st.wrist_sensor_L_forearm),
                             ('LE',  st.wrist_sensor_L_forearm)]:
                lm_specs.append(('L', lm, s_n,
                                  getattr(st, f'wrist_L_{lm}'), C_LEFT))

            # Right: RSP/USP/ME/LE — tmp (R.Hand) before Finalize, state (R.Forearm) after
            for lm in ['RSP', 'USP', 'ME', 'LE']:
                stored = getattr(st, f'wrist_R_{lm}')
                tmp    = r_tmp.get(lm)
                if stored is not None:
                    lm_specs.append(('R', lm, st.wrist_sensor_R_ptr,
                                     stored, C_RIGHT))
                elif tmp is not None:
                    lm_specs.append(('R', lm, st.wrist_sensor_R_hand,
                                     tmp, C_RIGHT))

            # Draw lines from sensor → landmark, then landmark dot
            lm_pts = {}
            for side_key, lm, s_n, offset, color in lm_specs:
                lm_pt  = get_lm_pt(s_n, offset)
                if lm_pt is None:
                    continue
                lm_pts[(side_key, lm)] = lm_pt
                sen_pt = sensor_canvas_pt(s_n)
                if sen_pt is not None:
                    p.setPen(QPen(color, 1))
                    p.drawLine(sen_pt, lm_pt)
                p.setPen(QPen(color.darker(130), 1))
                p.setBrush(color.lighter(180))
                p.drawEllipse(lm_pt, 3, 3)
                p.setPen(color.darker(160))
                p.setFont(QFont('Arial', 8))
                p.drawText(QPointF(lm_pt.x() + 5, lm_pt.y() + 3), lm)

            # Skeleton — wrist joint, elbow joint, hand & forearm segments
            def mid(a, b):
                return QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)

            BLACK = QColor(30, 30, 30)
            for side_key, hand_s_n in [('L', st.wrist_sensor_L_hand),
                                        ('R', st.wrist_sensor_R_hand)]:
                rsp = lm_pts.get((side_key, 'RSP'))
                usp = lm_pts.get((side_key, 'USP'))
                me  = lm_pts.get((side_key, 'ME'))
                le  = lm_pts.get((side_key, 'LE'))

                wj = mid(rsp, usp) if (rsp and usp) else None
                ej = mid(me,  le)  if (me  and le)  else None

                if wj is not None:
                    # Hand segment: hand sensor → wrist joint
                    hp = sensor_canvas_pt(hand_s_n)
                    if hp is not None:
                        p.setPen(QPen(BLACK, 2))
                        p.drawLine(hp, wj)
                    # Wrist joint dot
                    p.setPen(Qt.NoPen)
                    p.setBrush(BLACK)
                    p.drawEllipse(wj, 4, 4)

                if ej is not None:
                    # Forearm segment: wrist joint → elbow joint
                    if wj is not None:
                        p.setPen(QPen(BLACK, 2))
                        p.drawLine(wj, ej)
                    # Elbow joint dot
                    p.setPen(Qt.NoPen)
                    p.setBrush(BLACK)
                    p.drawEllipse(ej, 4, 4)

        # ── Mode 3 extra: RSP/USP/ME/LE/AP dots + skeleton ───
        if mode == 3:
            dig   = self.dig_screen
            r_tmp = dig._arm_R_tmp if dig is not None else {}

            def get_lm_pt3(sensor_n, offset):
                if offset is None:
                    return None
                s = self.liberty.get_sensor(sensor_n)
                if s is None:
                    return None
                pos = track_mcp(s, offset)
                return px(_ph(pos), _pv(pos))

            def sensor_canvas_pt3(sensor_n):
                s = self.liberty.get_sensor(sensor_n)
                if s is None:
                    return None
                return px(_sh(s), _sv(s))

            # Left: MCP/RSP/USP → L.Forearm; ME/LE/AP → L.UpperArm
            lm_specs3 = []
            for lm, s_n in [('RSP', st.arm_sensor_L_forearm),
                             ('USP', st.arm_sensor_L_forearm),
                             ('ME',  st.arm_sensor_L_upper),
                             ('LE',  st.arm_sensor_L_upper),
                             ('AP',  st.arm_sensor_L_upper)]:
                lm_specs3.append(('L', lm, s_n,
                                   getattr(st, f'arm_L_{lm}'), C_LEFT))

            # Right: MCP/RSP/USP in R.Forearm (permanent);
            #        ME/LE/AP tmp(R.Forearm) or state(R.UpperArm)
            for lm in ['RSP', 'USP']:
                stored = getattr(st, f'arm_R_{lm}')
                if stored is not None:
                    lm_specs3.append(('R', lm, st.arm_sensor_R_forearm, stored, C_RIGHT))
            for lm in ['ME', 'LE', 'AP']:
                stored = getattr(st, f'arm_R_{lm}')
                tmp    = r_tmp.get(lm)
                if stored is not None:
                    lm_specs3.append(('R', lm, st.arm_sensor_R_ptr, stored, C_RIGHT))
                elif tmp is not None:
                    lm_specs3.append(('R', lm, st.arm_sensor_R_forearm, tmp, C_RIGHT))

            lm_pts3 = {}
            for side_key, lm, s_n, offset, color in lm_specs3:
                lm_pt  = get_lm_pt3(s_n, offset)
                if lm_pt is None:
                    continue
                lm_pts3[(side_key, lm)] = lm_pt
                sen_pt = sensor_canvas_pt3(s_n)
                if sen_pt is not None:
                    p.setPen(QPen(color, 1))
                    p.drawLine(sen_pt, lm_pt)
                p.setPen(QPen(color.darker(130), 1))
                p.setBrush(color.lighter(180))
                p.drawEllipse(lm_pt, 3, 3)
                p.setPen(color.darker(160))
                p.setFont(QFont('Arial', 8))
                p.drawText(QPointF(lm_pt.x() + 5, lm_pt.y() + 3), lm)

            def mid3(a, b):
                return QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)

            BLACK = QColor(30, 30, 30)
            for side_key, fore_s_n in [('L', st.arm_sensor_L_forearm),
                                        ('R', st.arm_sensor_R_forearm)]:
                rsp = lm_pts3.get((side_key, 'RSP'))
                usp = lm_pts3.get((side_key, 'USP'))
                me  = lm_pts3.get((side_key, 'ME'))
                le  = lm_pts3.get((side_key, 'LE'))
                ap  = lm_pts3.get((side_key, 'AP'))

                wj = mid3(rsp, usp) if (rsp and usp) else None
                ej = mid3(me,  le)  if (me  and le)  else None

                if wj is not None:
                    fp = sensor_canvas_pt3(fore_s_n)
                    if fp is not None:
                        p.setPen(QPen(BLACK, 2))
                        p.drawLine(fp, wj)
                    p.setPen(Qt.NoPen)
                    p.setBrush(BLACK)
                    p.drawEllipse(wj, 4, 4)

                if ej is not None:
                    if wj is not None:
                        p.setPen(QPen(BLACK, 2))
                        p.drawLine(wj, ej)
                    p.setPen(Qt.NoPen)
                    p.setBrush(BLACK)
                    p.drawEllipse(ej, 4, 4)

                if ap is not None:
                    if ej is not None:
                        p.setPen(QPen(BLACK, 2))
                        p.drawLine(ej, ap)
                    p.setPen(Qt.NoPen)
                    p.setBrush(BLACK)
                    p.drawEllipse(ap, 4, 4)

        # ── Mode 4 extra: landmarks + skeleton ───────────────
        if mode == 4:
            dig   = self.dig_screen
            a4tmp = dig._arm4_tmp if dig is not None else {}
            side_color = C_RIGHT if st.dig_hand_setup == 0 else C_LEFT

            def get_lm_pt4(sensor_n, offset):
                if offset is None:
                    return None
                s = self.liberty.get_sensor(sensor_n)
                if s is None:
                    return None
                pos = track_mcp(s, offset)
                return px(_ph(pos), _pv(pos))

            def sensor_canvas_pt4(sensor_n):
                s = self.liberty.get_sensor(sensor_n)
                if s is None:
                    return None
                return px(_sh(s), _sv(s))

            lm_specs4 = []
            for lm, s_n in [('USP', st.arm4_sensor_forearm),
                             ('RSP', st.arm4_sensor_forearm),
                             ('ME',  st.arm4_sensor_upper),
                             ('LE',  st.arm4_sensor_upper),
                             ('AP',  st.arm4_sensor_upper)]:
                lm_specs4.append((lm, s_n, getattr(st, f'arm4_{lm}')))

            # AP_opp: stored = Trunk frame; tmp = UpperArm frame
            ap_opp_stored = st.arm4_AP_opp
            ap_opp_tmp    = a4tmp.get('AP_opp')
            if ap_opp_stored is not None:
                lm_specs4.append(('AP_opp', st.arm4_sensor_trunk, ap_opp_stored))
            elif ap_opp_tmp is not None:
                lm_specs4.append(('AP_opp', st.arm4_sensor_upper, ap_opp_tmp))

            lm_pts4 = {}
            for lm, s_n, offset in lm_specs4:
                lm_pt  = get_lm_pt4(s_n, offset)
                if lm_pt is None:
                    continue
                lm_pts4[lm] = lm_pt
                sen_pt = sensor_canvas_pt4(s_n)
                if sen_pt is not None:
                    p.setPen(QPen(side_color, 1))
                    p.drawLine(sen_pt, lm_pt)
                p.setPen(QPen(side_color.darker(130), 1))
                p.setBrush(side_color.lighter(180))
                p.drawEllipse(lm_pt, 3, 3)
                p.setPen(side_color.darker(160))
                p.setFont(QFont('Arial', 8))
                p.drawText(QPointF(lm_pt.x() + 5, lm_pt.y() + 3), lm)

            BLACK = QColor(30, 30, 30)
            rsp = lm_pts4.get('RSP')
            usp = lm_pts4.get('USP')
            me  = lm_pts4.get('ME')
            le  = lm_pts4.get('LE')
            ap  = lm_pts4.get('AP')

            def mid4(a, b):
                return QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)

            wj = mid4(rsp, usp) if (rsp and usp) else None
            ej = mid4(me,  le)  if (me  and le)  else None

            if wj is not None:
                fp = sensor_canvas_pt4(st.arm4_sensor_forearm)
                if fp is not None:
                    p.setPen(QPen(BLACK, 2))
                    p.drawLine(fp, wj)
                p.setPen(Qt.NoPen)
                p.setBrush(BLACK)
                p.drawEllipse(wj, 4, 4)

            if ej is not None:
                if wj is not None:
                    p.setPen(QPen(BLACK, 2))
                    p.drawLine(wj, ej)
                p.setPen(Qt.NoPen)
                p.setBrush(BLACK)
                p.drawEllipse(ej, 4, 4)

            if ap is not None and ej is not None:
                p.setPen(QPen(BLACK, 2))
                p.drawLine(ej, ap)
                p.setPen(Qt.NoPen)
                p.setBrush(BLACK)
                p.drawEllipse(ap, 4, 4)

            # Hand segment: wrist joint → MCP
            if wj is not None:
                mcp_pt = get_lm_pt4(st.arm4_sensor_hand, st.arm4_MCP)
                if mcp_pt is not None:
                    p.setPen(QPen(BLACK, 2))
                    p.drawLine(wj, mcp_pt)

            # Trunk oval: horizontal oval spanning AP → AP_opp
            ap_opp_pt = lm_pts4.get('AP_opp')
            if ap is not None and ap_opp_pt is not None:
                cx = (ap.x() + ap_opp_pt.x()) / 2
                cy = (ap.y() + ap_opp_pt.y()) / 2
                dx = ap_opp_pt.x() - ap.x()
                dy = ap_opp_pt.y() - ap.y()
                half_len = math.sqrt(dx * dx + dy * dy) / 2
                angle    = math.degrees(math.atan2(dy, dx))
                p.save()
                p.translate(cx, cy)
                p.rotate(angle)
                p.setPen(QPen(BLACK, 1))
                p.setBrush(QColor(100, 100, 100, 80))
                p.drawEllipse(QPointF(0, 0), half_len, 8.0)
                p.restore()

        # ── Coordinate axis indicator (bottom-left corner) ───
        ax_ox, ax_oy = float(PAD + 10), float(H - PAD - 10)
        ax_len = 28
        ax_col = QColor(80, 80, 80)
        horiz_lbl = 'Y'
        vert_lbl  = 'Z'
        p.setPen(QPen(ax_col, 1))
        p.drawLine(QPointF(ax_ox, ax_oy), QPointF(ax_ox + ax_len, ax_oy))
        p.drawLine(QPointF(ax_ox + ax_len, ax_oy),
                   QPointF(ax_ox + ax_len - 5, ax_oy - 4))
        p.drawLine(QPointF(ax_ox + ax_len, ax_oy),
                   QPointF(ax_ox + ax_len - 5, ax_oy + 4))
        p.drawLine(QPointF(ax_ox, ax_oy), QPointF(ax_ox, ax_oy - ax_len))
        p.drawLine(QPointF(ax_ox, ax_oy - ax_len),
                   QPointF(ax_ox - 4, ax_oy - ax_len + 5))
        p.drawLine(QPointF(ax_ox, ax_oy - ax_len),
                   QPointF(ax_ox + 4, ax_oy - ax_len + 5))
        p.setFont(QFont('Arial', 9, QFont.Bold))
        p.setPen(ax_col)
        p.drawText(QPointF(ax_ox + ax_len + 3, ax_oy + 4), horiz_lbl)
        p.drawText(QPointF(ax_ox - 6, ax_oy - ax_len - 3), vert_lbl)


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

        # Currently applied mode for this session (None = not yet applied)
        self._active_mode = None

        # Currently applied hand setup (2=Both until Set is pressed)
        self._active_hand = 2   # 0=Right, 1=Left, 2=Both

        # Top-down canvas
        self._canvas = None

        # Wrist mode cell status labels  {(side, lm): QLabel}
        self._wrist_status_lbls = {}

        # Full Arm mode cell status labels  {(side, lm): QLabel}
        self._arm_status_lbls = {}

        # Full Single Arm mode cell status labels  {lm: QLabel}
        self._arm4_status_lbls = {}

        # Full Single Arm mode: AP_opp temp offset in UpperArm frame before trunk finalize
        self._arm4_tmp = {}

        # Wrist mode: R-side temp offsets in R.Hand frame before finalization
        self._wrist_R_tmp = {}  # {landmark: [x,y,z]}

        # Full Arm mode: R-side temp offsets in R.Forearm frame before finalization
        self._arm_R_tmp = {}   # {landmark: [x,y,z]}

        # Non-pointer combo boxes for current mode (for mutual exclusion)
        self._non_ptr_cbs = []

        # Sensors assigned in the current mode (for live color coding)
        self._assigned_sensors = set()

        # Live update references (rebuilt per mode)
        self._live_rows      = {}   # sensor_n -> QLabel
        self._mcp_pos_lbls   = {}   # 'right'/'left' -> QLabel
        self._mcp_status_lbls = {}  # 'right'/'left' -> QLabel (record status)

        self._live_timer = QTimer(self)
        self._live_timer.timeout.connect(self._update_live)

        # Keyboard shortcuts (enabled only while this screen is visible)
        # Key 1 / F1 — mode 1: MCP record; mode 2: wrist MCP record
        self._sc1   = QShortcut(QKeySequence('1'),  self)
        self._sc_f1 = QShortcut(QKeySequence('F1'), self)
        self._sc1.activated.connect(lambda: self._shortcut_record('right'))
        self._sc_f1.activated.connect(lambda: self._shortcut_record('left'))
        self._sc1.setEnabled(False)
        self._sc_f1.setEnabled(False)

        # Keys 2–5 / F2–F5 — mode 2: RSP/USP/ME/LE (wrist); mode 3: same landmarks
        self._wrist_scs = []
        for lm in WRIST_LANDMARKS[1:]:   # RSP, USP, LE, ME
            idx = _LM_IDX[lm]
            sc_n = QShortcut(QKeySequence(str(idx)), self)
            sc_f = QShortcut(QKeySequence(f'F{idx}'), self)
            sc_n.activated.connect(lambda l=lm: self._shortcut_lm('right', l))
            sc_f.activated.connect(lambda l=lm: self._shortcut_lm('left',  l))
            sc_n.setEnabled(False)
            sc_f.setEnabled(False)
            self._wrist_scs.extend([sc_n, sc_f])

        # Key 6 — mode 2: Finalize Right Forearm; mode 3: record AP
        self._sc6   = QShortcut(QKeySequence('6'),  self)
        self._sc_f6 = QShortcut(QKeySequence('F6'), self)
        self._sc6.activated.connect(self._shortcut_key6)
        self._sc_f6.activated.connect(lambda: self._shortcut_arm('left', 'AP'))
        self._sc6.setEnabled(False)
        self._sc_f6.setEnabled(False)

        # Key 7 — mode 3: Finalize Right Upper Arm; mode 4: record AP_opp
        self._sc7 = QShortcut(QKeySequence('7'), self)
        self._sc7.activated.connect(self._shortcut_key7)
        self._sc7.setEnabled(False)

        # Key 8 — mode 4: Finalize Trunk
        self._sc8 = QShortcut(QKeySequence('8'), self)
        self._sc8.activated.connect(self._shortcut_finalize_arm4)
        self._sc8.setEnabled(False)

        self._build()

    def showEvent(self, e):
        self._live_timer.start(125)
        self._sc1.setEnabled(True)
        self._sc_f1.setEnabled(True)
        for sc in self._wrist_scs:
            sc.setEnabled(True)
        self._sc6.setEnabled(True)
        self._sc_f6.setEnabled(True)
        self._sc7.setEnabled(True)
        self._sc8.setEnabled(True)
        if self._active_mode is None:
            # First entry this session: auto-apply Mode 0
            self._active_mode = 0
            self.state.dig_mode = 0
            self.mode_cb.setCurrentIndex(0)
            self._update_current_lbl()
            self._rebuild_content()
        else:
            # Sync trunk checkbox to current task state without rebuilding
            if self._active_mode == 0 and hasattr(self, '_trunk_chk'):
                self._trunk_chk.blockSignals(True)
                self._trunk_chk.setChecked(self.state.dig_trunk_enabled)
                self._trunk_chk.blockSignals(False)
                self._trunk_cb.setEnabled(self.state.dig_trunk_enabled)
                self._apply_trunk_style(self.state.dig_trunk_enabled)
                self._refresh_cursor_assigned()
        super().showEvent(e)

    def hideEvent(self, e):
        self._live_timer.stop()
        self._cd_timer.stop()
        self._sc1.setEnabled(False)
        self._sc_f1.setEnabled(False)
        for sc in self._wrist_scs:
            sc.setEnabled(False)
        self._sc6.setEnabled(False)
        self._sc_f6.setEnabled(False)
        self._sc7.setEnabled(False)
        self._sc8.setEnabled(False)
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
        back.clicked.connect(self._on_back)
        top.addWidget(back)
        top.addStretch()
        title = QLabel("Digitization")
        title.setFont(QFont('Arial', 22, QFont.Bold))
        title.setStyleSheet("color: #000000;")
        top.addWidget(title)
        top.addStretch()
        root.addLayout(top)
        root.addWidget(self._sep())

        # Mode selector row
        mode_row = QHBoxLayout()
        mode_row.addWidget(self._bold("Mode:"))
        mode_row.addSpacing(8)
        self.mode_cb = QComboBox()
        self.mode_cb.setStyleSheet(COMBO)
        self.mode_cb.setFixedWidth(240)
        for label, val in MODES:
            self.mode_cb.addItem(label, val)
        # default dropdown to Mode 0
        self.mode_cb.setCurrentIndex(0)
        mode_row.addWidget(self.mode_cb)
        mode_row.addSpacing(10)
        apply_btn = QPushButton("Apply")
        apply_btn.setStyleSheet(BTN)
        apply_btn.setFixedWidth(90)
        apply_btn.clicked.connect(self._on_apply)
        mode_row.addWidget(apply_btn)
        mode_row.addSpacing(24)
        hand_lbl = QLabel("Hand:")
        hand_lbl.setFont(QFont('Arial', 14))
        hand_lbl.setStyleSheet("color: #333333;")
        mode_row.addWidget(hand_lbl)
        mode_row.addSpacing(6)
        self.hand_cb = QComboBox()
        self.hand_cb.setStyleSheet(COMBO)
        self.hand_cb.setFixedWidth(90)
        for label, val in [("Both", 2), ("Right", 0), ("Left", 1)]:
            self.hand_cb.addItem(label, val)
        self.hand_cb.setCurrentIndex(0)
        self.hand_cb.currentIndexChanged.connect(
            lambda _: setattr(self.state, 'dig_hand_setup', self.hand_cb.currentData()))
        mode_row.addWidget(self.hand_cb)
        mode_row.addSpacing(6)
        hand_set_btn = QPushButton("Set")
        hand_set_btn.setStyleSheet(BTN)
        hand_set_btn.setFixedWidth(60)
        hand_set_btn.clicked.connect(self._on_hand_set)
        mode_row.addWidget(hand_set_btn)
        mode_row.addSpacing(16)
        self._current_mode_lbl = QLabel("")
        self._current_mode_lbl.setFont(QFont('Arial', 14))
        self._current_mode_lbl.setStyleSheet("color: #555555;")
        mode_row.addWidget(self._current_mode_lbl)
        mode_row.addStretch()
        root.addLayout(mode_row)
        root.addWidget(self._sep())

        # Scrollable content area (rebuilt on Apply)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setStyleSheet("background: transparent;")
        root.addWidget(self._scroll)

        self._rebuild_content()

    def _update_current_lbl(self):
        hand_label = {0: 'Right', 1: 'Left', 2: 'Both'}[self._active_hand]
        self._current_mode_lbl.setText(
            f"Current:  {self.mode_cb.currentText().strip()}  |  Hand: {hand_label}")

    def _on_hand_set(self):
        self._active_hand = self.hand_cb.currentData()
        self.state.dig_hand_setup = self._active_hand
        if self.state.dig_mode == 4:
            for lm in ARM4_LANDMARKS:
                setattr(self.state, f'arm4_{lm}', None)
            self._arm4_tmp.clear()
            self.state.save_config()
        self._update_current_lbl()
        self._rebuild_content()

    def _mcp_field(self, mode, side):
        """Return the recorded MCP offset for the given mode and side."""
        if mode == 1:
            return self.state.mcp_offset_right if side == 'right' else self.state.mcp_offset_left
        if mode == 2:
            return self.state.wrist_R_MCP if side == 'right' else self.state.wrist_L_MCP
        if mode == 3:
            return self.state.arm_R_MCP if side == 'right' else self.state.arm_L_MCP
        if mode == 4:
            return self.state.arm4_MCP
        return None

    def _on_back(self):
        mode  = self.state.dig_mode
        setup = self.state.dig_hand_setup  # 0=Right, 1=Left, 2=Both
        if mode >= 1:
            need_right = setup in (0, 2)
            need_left  = setup in (1, 2)
            missing = []
            if need_right and self._mcp_field(mode, 'right') is None:
                missing.append("Right MCP")
            if need_left and self._mcp_field(mode, 'left') is None:
                missing.append("Left MCP")
            if missing:
                QMessageBox.warning(
                    self, "MCP Not Recorded",
                    f"Mode {mode} is selected but the following have not been recorded:\n"
                    f"  {', '.join(missing)}\n\n"
                    "Please record them before leaving, or switch to Mode 0."
                )
                return
        self.mw.show_screen('menu')

    def _rebuild_content(self):
        self._canvas = None
        self._live_rows.clear()
        self._mcp_pos_lbls.clear()
        self._mcp_status_lbls.clear()
        self._wrist_status_lbls.clear()
        self._arm_status_lbls.clear()
        self._arm4_status_lbls.clear()
        self._non_ptr_cbs.clear()
        self._assigned_sensors.clear()

        page = QWidget()
        page.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        mode = self._active_mode
        if mode is None:
            hint = QLabel("Select a mode and press  Apply  to begin.")
            hint.setFont(QFont('Arial', 15))
            hint.setStyleSheet("color: #999999;")
            lay.addWidget(hint)
        elif mode == 0:
            self._build_cursor(lay)
        elif mode == 1:
            self._build_mcp(lay)
        elif mode == 2:
            self._build_wrist(lay)
        elif mode == 3:
            self._build_arm(lay)
        elif mode == 4:
            self._build_arm4(lay)

        # Common live section — always S1–S4
        lay.addWidget(self._sep())
        lay.addWidget(self._bold("Live Sensor Data"))
        for n in [1, 2, 3, 4]:
            self._live_rows[n] = self._live_row_widget(lay, n)

        lay.addStretch()
        self._scroll.setWidget(page)

    def _on_apply(self):
        self._active_mode = self.mode_cb.currentData()
        self.state.dig_mode = self._active_mode

        # Re-enable Both option in case mode 4 had disabled it
        self.hand_cb.model().item(0).setEnabled(True)

        if self._active_mode == 4:
            # Mode 4 is single-arm only — disable Both, default to Right
            self.hand_cb.model().item(0).setEnabled(False)
            self._active_hand = 0
            self.state.dig_hand_setup = 0
            self.hand_cb.blockSignals(True)
            self.hand_cb.setCurrentIndex(1)  # Right
            self.hand_cb.blockSignals(False)
        else:
            # Reset hand setup to Both
            self._active_hand = 2
            self.state.dig_hand_setup = 2
            self.hand_cb.blockSignals(True)
            self.hand_cb.setCurrentIndex(0)  # Both is index 0
            self.hand_cb.blockSignals(False)

        # Clear recorded data for the newly selected mode
        if self._active_mode == 1:
            self.state.mcp_offset_right = None
            self.state.mcp_offset_left  = None
        elif self._active_mode == 2:
            for lm in WRIST_LANDMARKS:
                setattr(self.state, f'wrist_L_{lm}', None)
                setattr(self.state, f'wrist_R_{lm}', None)
            self._wrist_R_tmp.clear()
        elif self._active_mode == 3:
            for lm in ARM_LANDMARKS:
                setattr(self.state, f'arm_L_{lm}', None)
                setattr(self.state, f'arm_R_{lm}', None)
            self._arm_R_tmp.clear()
        elif self._active_mode == 4:
            for lm in ARM4_LANDMARKS:
                setattr(self.state, f'arm4_{lm}', None)
            self._arm4_tmp.clear()

        self.state.save_config()
        self._update_current_lbl()
        self._rebuild_content()

    # ── MODE 0: Cursor ────────────────────────────────────────

    def _build_cursor(self, lay):
        lay.addWidget(self._mode_note("Hold the sensor in your hand."))
        lay.addSpacing(4)
        lay.addWidget(self._bold("Sensor Assignment"))
        row = QHBoxLayout()
        cbs = []
        for label, key, default in [
            ("Right Hand:", 'right', self.state.dig_sensor_right),
            ("Left Hand:",  'left',  self.state.dig_sensor_left),
        ]:
            l = QLabel(label)
            l.setFont(QFont('Arial', 14))
            l.setStyleSheet("color: #333333;")
            row.addWidget(l)
            cb = self._sensor_cb(default)
            cb.currentIndexChanged.connect(
                lambda _, k=key, c=cb: self._save_cursor_assign(k, c))
            row.addWidget(cb)
            row.addSpacing(20)
            cbs.append(cb)

        # Trunk — optional, toggled by checkbox
        self._trunk_chk = QCheckBox("Trunk:")
        self._trunk_chk.setFont(QFont('Arial', 14))
        self._trunk_chk.setChecked(self.state.dig_trunk_enabled)
        self._apply_trunk_style(self.state.dig_trunk_enabled)
        row.addWidget(self._trunk_chk)
        self._trunk_cb = self._sensor_cb(self.state.dig_sensor_trunk)
        self._trunk_cb.setEnabled(self.state.dig_trunk_enabled)
        self._trunk_cb.currentIndexChanged.connect(
            lambda _: self._save_cursor_assign('trunk', self._trunk_cb))
        row.addWidget(self._trunk_cb)
        row.addSpacing(20)

        self._trunk_chk.toggled.connect(self._on_trunk_toggled)

        row.addStretch()
        lay.addLayout(row)

        self._non_ptr_cbs = cbs
        for cb in cbs:
            cb.currentIndexChanged.connect(lambda _: self._apply_exclusions())
        self._apply_exclusions()
        self._refresh_cursor_assigned()

        lay.addWidget(self._sep())
        self._canvas = _DigCanvas(self.state, self.liberty)
        self._add_canvas_section(lay)

    def _apply_trunk_style(self, checked):
        text_color = "#333333" if checked else "#aaaaaa"
        self._trunk_chk.setStyleSheet(
            f"QCheckBox {{ color: {text_color}; spacing: 6px; }}"
            "QCheckBox::indicator { width: 16px; height: 16px;"
            " border: 2px solid #888888; border-radius: 3px; background: #ffffff; }"
            "QCheckBox::indicator:checked { background: #4a90d9; border: 2px solid #2a70b9; }"
        )

    def _on_trunk_toggled(self, checked):
        self.state.dig_trunk_enabled = checked
        self._trunk_cb.setEnabled(checked)
        self._apply_trunk_style(checked)
        self._refresh_cursor_assigned()

    def _refresh_cursor_assigned(self):
        self._assigned_sensors = {
            self.state.dig_sensor_right,
            self.state.dig_sensor_left,
        }
        if self.state.dig_trunk_enabled:
            self._assigned_sensors.add(self.state.dig_sensor_trunk)

    def _save_cursor_assign(self, side, cb):
        if side == 'right':
            self.state.dig_sensor_right = cb.currentData()
        elif side == 'left':
            self.state.dig_sensor_left = cb.currentData()
        else:
            self.state.dig_sensor_trunk = cb.currentData()
        self.state.save_config()
        self._refresh_assigned()

    # ── MODE 1: MCP ───────────────────────────────────────────

    def _build_mcp(self, lay):
        lay.addWidget(self._mode_note("Place a sensor on the dorsum of the hand."))
        lay.addSpacing(4)
        lay.addWidget(self._bold("Sensor Assignment"))
        arow = QHBoxLayout()
        non_ptr = []
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
            if key != 'ptr':
                non_ptr.append(cb)
        arow.addStretch()
        lay.addLayout(arow)

        self._non_ptr_cbs = non_ptr
        for cb in non_ptr:
            cb.currentIndexChanged.connect(lambda _: self._apply_exclusions())
        self._apply_exclusions()
        self._assigned_sensors = {self.state.dig_sensor_right,
                                   self.state.dig_sensor_left,
                                   self.state.mcp_sensor_pointer}
        lay.addWidget(self._sep())

        # Landmarks — 2-column grid
        lay.addWidget(self._bold("Landmarks"))

        grid_w = QWidget()
        grid_w.setStyleSheet("background: transparent;")
        grid = QGridLayout(grid_w)
        grid.setSpacing(6)
        grid.setContentsMargins(0, 0, 0, 0)

        for col, text, side in [(0, "Left", 'left'), (1, "Right", 'right')]:
            active = self._side_active(side)
            color  = ("#3050d0" if side == 'left' else "#c03030") if active else "#aaaaaa"
            hdr = QLabel(text)
            hdr.setFont(QFont('Arial', 14, QFont.Bold))
            hdr.setStyleSheet(f"color: {color};")
            hdr.setAlignment(Qt.AlignCenter)
            grid.addWidget(hdr, 0, col)

        grid.addWidget(self._mcp_cell('left'),  1, 0)
        grid.addWidget(self._mcp_cell('right'), 1, 1)

        lay.addWidget(grid_w)
        lay.addWidget(self._sep())

        # Save / Load
        sl_row = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(BTN)
        save_btn.clicked.connect(self._save_dig)
        load_btn = QPushButton("Load")
        load_btn.setStyleSheet(BTN)
        load_btn.clicked.connect(self._load_dig)
        self._save_status_lbl = QLabel(self._save_path_hint())
        self._save_status_lbl.setFont(QFont('Arial', 13))
        self._save_status_lbl.setStyleSheet("color: #777777;")
        sl_row.addWidget(save_btn)
        sl_row.addSpacing(8)
        sl_row.addWidget(load_btn)
        sl_row.addSpacing(12)
        sl_row.addWidget(self._save_status_lbl)
        sl_row.addStretch()
        lay.addLayout(sl_row)

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

        # Top-down canvas
        lay.addWidget(self._sep())
        self._canvas = _DigCanvas(self.state, self.liberty)
        self._add_canvas_section(lay)

    def _save_mcp_assign(self, key, cb):
        val = cb.currentData()
        if key == 'right': self.state.dig_sensor_right = val
        elif key == 'left': self.state.dig_sensor_left = val
        elif key == 'ptr':  self.state.mcp_sensor_pointer = val
        self.state.save_config()
        self._refresh_assigned()

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
        self._autosave_dig()
        threading.Thread(target=beep, args=(880, 120), daemon=True).start()
        status_lbl.setText(self._offset_text(offset))

    def _shortcut_record(self, side):
        mode = self.state.dig_mode
        if mode == 1:
            lbl = self._mcp_status_lbls.get(side)
            if lbl is not None:
                self._record_mcp(side, lbl)
        elif mode == 2:
            self._shortcut_wrist(side, 'MCP')
        elif mode == 3:
            self._shortcut_arm(side, 'MCP')
        elif mode == 4 and side == 'right':
            self._shortcut_arm4('MCP')

    def _shortcut_lm(self, side, lm):
        """Dispatch landmark shortcut keys 2-5 to the active mode."""
        mode = self.state.dig_mode
        if mode == 2:
            self._shortcut_wrist(side, lm)
        elif mode == 3:
            self._shortcut_arm(side, lm)
        elif mode == 4 and side == 'right':
            # Keys are labeled for mode 2/3 order; remap for mode 4
            remap = {'RSP': 'USP', 'USP': 'RSP', 'ME': 'LE', 'LE': 'ME'}
            self._shortcut_arm4(remap.get(lm, lm))

    def _shortcut_wrist(self, side, lm):
        if self.state.dig_mode != 2:
            return
        lbl = self._wrist_status_lbls.get((side, lm))
        if lbl is None:
            return
        if side == 'right':
            self._record_wrist_R(lm, lbl)
        else:
            self._record_wrist_L(lm, lbl)

    def _shortcut_arm(self, side, lm):
        if self.state.dig_mode != 3:
            return
        lbl = self._arm_status_lbls.get((side, lm))
        if lbl is None:
            return
        if side == 'right':
            self._record_arm_R(lm, lbl)
        else:
            self._record_arm_L(lm, lbl)

    def _shortcut_key6(self):
        mode = self.state.dig_mode
        if mode == 2:
            self._finalize_wrist_R()
        elif mode == 3:
            self._shortcut_arm('right', 'AP')
        elif mode == 4:
            self._shortcut_arm4('AP')

    def _shortcut_key7(self):
        mode = self.state.dig_mode
        if mode == 3:
            self._finalize_arm_R()
        elif mode == 4:
            self._shortcut_arm4('AP_opp')

    def _shortcut_finalize_arm4(self):
        if self.state.dig_mode != 4:
            return
        self._finalize_arm4_trunk()

    def _shortcut_arm4(self, lm):
        if self.state.dig_mode != 4:
            return
        lbl = self._arm4_status_lbls.get(lm)
        if lbl is None:
            return
        self._record_arm4(lm, lbl)

    # ── save / load ───────────────────────────────────────────

    def _dig_save_path(self):
        if not self.state.data_dir:
            return None
        return os.path.join(self.state.data_dir, 'digitization_mode1.json')

    def _save_path_hint(self):
        p = self._dig_save_path()
        if p is None:
            return "No data folder set"
        return os.path.basename(p)

    def _autosave_dig(self):
        path = self._dig_save_path()
        if path is None:
            return
        data = {
            'mode': 1,
            'sensor_right':   self.state.dig_sensor_right,
            'sensor_left':    self.state.dig_sensor_left,
            'sensor_pointer': self.state.mcp_sensor_pointer,
            'mcp_offset_right': self.state.mcp_offset_right,
            'mcp_offset_left':  self.state.mcp_offset_left,
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        if hasattr(self, '_save_status_lbl'):
            self._save_status_lbl.setText(f"Auto-saved  →  {os.path.basename(path)}")

    def _save_dig(self):
        self._autosave_dig()
        if hasattr(self, '_save_status_lbl'):
            path = self._dig_save_path()
            self._save_status_lbl.setText(f"Saved  →  {os.path.basename(path) if path else '—'}")

    def _load_dig(self):
        path = self._dig_save_path()
        if path is None or not os.path.exists(path):
            if hasattr(self, '_save_status_lbl'):
                self._save_status_lbl.setText("No save file found")
            return
        try:
            with open(path) as f:
                data = json.load(f)
            self.state.dig_sensor_right    = data.get('sensor_right',   self.state.dig_sensor_right)
            self.state.dig_sensor_left     = data.get('sensor_left',    self.state.dig_sensor_left)
            self.state.mcp_sensor_pointer  = data.get('sensor_pointer', self.state.mcp_sensor_pointer)
            self.state.mcp_offset_right    = data.get('mcp_offset_right')
            self.state.mcp_offset_left     = data.get('mcp_offset_left')
            self.state.save_config()
            self._rebuild_content()
        except Exception as e:
            if hasattr(self, '_save_status_lbl'):
                self._save_status_lbl.setText(f"Load failed: {e}")

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
        lay.addWidget(self._mode_note(
            "Place a sensor on the dorsum of the hand, "
            "and a sensor on the distal dorsal forearm."))
        lay.addSpacing(4)
        lay.addWidget(self._bold("Sensor Assignment"))
        arow = QHBoxLayout()
        arow.setSpacing(10)
        assigns = [
            ("L.Hand:",              'wrist_sensor_L_hand',    False),
            ("R.Hand:",              'wrist_sensor_R_hand',    False),
            ("L.Forearm:",           'wrist_sensor_L_forearm', False),
            ("R.Forearm & Pointer:", 'wrist_sensor_R_ptr',     True),
        ]
        non_ptr = []
        for label, attr, is_ptr in assigns:
            l = QLabel(label)
            l.setFont(QFont('Arial', 13))
            l.setStyleSheet("color: #333333;")
            arow.addWidget(l)
            cb = self._sensor_cb(getattr(self.state, attr))
            cb.currentIndexChanged.connect(
                lambda _, a=attr, c=cb: self._save_wrist_assign(a, c))
            arow.addWidget(cb)
            arow.addSpacing(8)
            if not is_ptr:
                non_ptr.append(cb)
        arow.addStretch()
        lay.addLayout(arow)

        self._non_ptr_cbs = non_ptr
        for cb in non_ptr:
            cb.currentIndexChanged.connect(lambda _: self._apply_exclusions())
        self._apply_exclusions()
        self._assigned_sensors = {self.state.wrist_sensor_L_hand,
                                   self.state.wrist_sensor_R_hand,
                                   self.state.wrist_sensor_L_forearm,
                                   self.state.wrist_sensor_R_ptr}
        lay.addWidget(self._sep())

        # Landmarks — 4-column grid
        lay.addWidget(self._bold("Landmarks"))

        grid_w = QWidget()
        grid_w.setStyleSheet("background: transparent;")
        grid = QGridLayout(grid_w)
        grid.setSpacing(6)
        grid.setContentsMargins(0, 0, 0, 0)

        self._grid_header(grid, 0, "Left",  'left')
        self._grid_header(grid, 2, "Right", 'right')

        # Row 1 — MCP (each side spans 2 cols)
        grid.addWidget(self._wrist_cell('left',  'MCP'), 1, 0, 1, 2)
        grid.addWidget(self._wrist_cell('right', 'MCP'), 1, 2, 1, 2)

        # Row 2 — L.USP | L.RSP | R.RSP | R.USP
        for col, side, lm in [(0, 'left',  'USP'),
                               (1, 'left',  'RSP'),
                               (2, 'right', 'RSP'),
                               (3, 'right', 'USP')]:
            grid.addWidget(self._wrist_cell(side, lm), 2, col)

        # Row 3 — L.LE | L.ME | R.ME | R.LE
        for col, side, lm in [(0, 'left',  'LE'),
                               (1, 'left',  'ME'),
                               (2, 'right', 'ME'),
                               (3, 'right', 'LE')]:
            grid.addWidget(self._wrist_cell(side, lm), 3, col)

        lay.addWidget(grid_w)

        # Finalize
        fin_row = QHBoxLayout()
        self._finalize_btn = QPushButton("Finalize Right Forearm  [6]")
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

        # Save / Load
        sl_row = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(BTN)
        save_btn.clicked.connect(self._save_wrist)
        load_btn = QPushButton("Load")
        load_btn.setStyleSheet(BTN)
        load_btn.clicked.connect(self._load_wrist)
        self._wrist_save_lbl = QLabel(self._wrist_save_path_hint())
        self._wrist_save_lbl.setFont(QFont('Arial', 13))
        self._wrist_save_lbl.setStyleSheet("color: #777777;")
        sl_row.addWidget(save_btn)
        sl_row.addSpacing(8)
        sl_row.addWidget(load_btn)
        sl_row.addSpacing(12)
        sl_row.addWidget(self._wrist_save_lbl)
        sl_row.addStretch()
        lay.addLayout(sl_row)

        lay.addWidget(self._sep())

        # Clear buttons
        crow = QHBoxLayout()
        for label, fn in [("Clear Right", self._clear_wrist_R),
                          ("Clear Left",  self._clear_wrist_L),
                          ("Clear All",   self._clear_wrist_all)]:
            b = QPushButton(label)
            b.setStyleSheet(BTN)
            b.clicked.connect(fn)
            crow.addWidget(b)
            crow.addSpacing(8)
        crow.addStretch()
        lay.addLayout(crow)

        # Canvas
        lay.addWidget(self._sep())
        self._canvas = _DigCanvas(self.state, self.liberty, self)
        self._add_canvas_section(lay)

    def _wrist_cell(self, side, lm):
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setStyleSheet(
            "QFrame { background: #f8f8f8; border: 1px solid #dddddd;"
            " border-radius: 4px; }"
        )
        vlay = QVBoxLayout(frame)
        vlay.setContentsMargins(8, 6, 8, 6)
        vlay.setSpacing(4)

        color = "#3050d0" if side == 'left' else "#c03030"
        name_lbl = QLabel(WRIST_LM_FULL[lm])
        name_lbl.setFont(QFont('Arial', 12, QFont.Bold))
        name_lbl.setStyleSheet(
            f"color: {color}; background: transparent; border: none;")
        vlay.addWidget(name_lbl)

        if side == 'left':
            stored = getattr(self.state, f'wrist_L_{lm}')
            status_text = self._wrist_lm_text(side, lm, stored)
        else:
            stored = getattr(self.state, f'wrist_R_{lm}')
            tmp    = self._wrist_R_tmp.get(lm)
            status_text = self._wrist_lm_text(side, lm, stored, tmp)

        status_lbl = QLabel(status_text)
        status_lbl.setFont(QFont('Arial', 11))
        status_lbl.setStyleSheet(
            "color: #555555; background: transparent; border: none;")
        status_lbl.setWordWrap(True)
        vlay.addWidget(status_lbl)

        self._wrist_status_lbls[(side, lm)] = status_lbl

        idx  = _LM_IDX[lm]
        hint = f"[F{idx}]" if side == 'left' else f"[{idx}]"
        btn  = QPushButton(f"Record  {hint}")
        btn.setStyleSheet(BTN_SM)
        if side == 'left':
            btn.clicked.connect(
                lambda _, l=lm, s=status_lbl: self._record_wrist_L(l, s))
        else:
            btn.clicked.connect(
                lambda _, l=lm, s=status_lbl: self._record_wrist_R(l, s))
        if not self._side_active(side):
            btn.setEnabled(False)
        vlay.addWidget(btn)

        return frame

    def _mcp_cell(self, side):
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setStyleSheet(
            "QFrame { background: #f8f8f8; border: 1px solid #dddddd;"
            " border-radius: 4px; }"
        )
        vlay = QVBoxLayout(frame)
        vlay.setContentsMargins(8, 6, 8, 6)
        vlay.setSpacing(4)

        color = "#3050d0" if side == 'left' else "#c03030"
        hint  = "[F1]"    if side == 'left' else "[1]"
        attr  = 'mcp_offset_left' if side == 'left' else 'mcp_offset_right'

        name_lbl = QLabel("MCP (metacarpal)")
        name_lbl.setFont(QFont('Arial', 12, QFont.Bold))
        name_lbl.setStyleSheet(
            f"color: {color}; background: transparent; border: none;")
        vlay.addWidget(name_lbl)

        status_lbl = QLabel(self._offset_text(getattr(self.state, attr)))
        status_lbl.setFont(QFont('Arial', 11))
        status_lbl.setStyleSheet(
            "color: #555555; background: transparent; border: none;")
        status_lbl.setWordWrap(True)
        vlay.addWidget(status_lbl)

        btn = QPushButton(f"Record  {hint}")
        btn.setStyleSheet(BTN_SM)
        btn.clicked.connect(lambda _, s=side, l=status_lbl: self._record_mcp(s, l))
        if not self._side_active(side):
            btn.setEnabled(False)
        vlay.addWidget(btn)

        live_hdr = QLabel("Live MCP Position:")
        live_hdr.setFont(QFont('Arial', 11))
        live_hdr.setStyleSheet(
            "color: #444444; background: transparent; border: none;")
        vlay.addWidget(live_hdr)

        pos_lbl = QLabel("—")
        pos_lbl.setFont(QFont('Arial', 11))
        pos_lbl.setStyleSheet(
            "color: #888888; background: transparent; border: none;")
        vlay.addWidget(pos_lbl)

        self._mcp_status_lbls[side] = status_lbl
        self._mcp_pos_lbls[side]    = pos_lbl
        return frame

    def _save_wrist_assign(self, attr, cb):
        setattr(self.state, attr, cb.currentData())
        self.state.save_config()
        self._refresh_assigned()

    def _record_wrist_L(self, lm, status_lbl):
        from digitizer import compute_offset
        ptr_n  = self.state.wrist_sensor_R_ptr
        ptr_s  = self.liberty.get_sensor(ptr_n)
        if lm == 'MCP':
            # MCP only — in L.Hand sensor frame
            hand_n = self.state.wrist_sensor_L_hand
            hand_s = self.liberty.get_sensor(hand_n)
            if hand_s is None or ptr_s is None:
                status_lbl.setText("No sensor data — try again")
                return
            offset = compute_offset(hand_s, ptr_s)
            self.state.wrist_L_MCP = offset
        else:
            # RSP / USP / ME / LE — all in L.Forearm sensor frame
            fore_n = self.state.wrist_sensor_L_forearm
            fore_s = self.liberty.get_sensor(fore_n)
            if fore_s is None or ptr_s is None:
                status_lbl.setText("No sensor data — try again")
                return
            offset = compute_offset(fore_s, ptr_s)
            setattr(self.state, f'wrist_L_{lm}', offset)
        self.state.save_config()
        self._autosave_wrist()
        threading.Thread(target=beep, args=(880, 120), daemon=True).start()
        status_lbl.setText(self._wrist_lm_text('left', lm, offset))

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
            # MCP only — in R.Hand sensor frame (permanent)
            self.state.wrist_R_MCP = offset
            self.state.save_config()
        else:
            # RSP / USP / ME / LE — temp in R.Hand frame until Finalize
            self._wrist_R_tmp[lm] = offset
        self._autosave_wrist()
        threading.Thread(target=beep, args=(880, 120), daemon=True).start()
        status_lbl.setText(self._wrist_lm_text(
            'right', lm, getattr(self.state, f'wrist_R_{lm}'), self._wrist_R_tmp.get(lm)))

    def _finalize_wrist_R(self):
        from digitizer import finalize_forearm
        needed = {lm: self._wrist_R_tmp.get(lm) for lm in ['RSP', 'USP', 'ME', 'LE']}
        if any(v is None for v in needed.values()):
            self._finalize_lbl.setText("Record RSP/USP/ME/LE first")
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
        self._autosave_wrist()
        threading.Thread(target=_beep_complete, daemon=True).start()
        self._finalize_lbl.setText("✓  RSP/USP/ME/LE converted to R.Forearm frame")
        for lm in ['RSP', 'USP', 'ME', 'LE']:
            lbl = self._wrist_status_lbls.get(('right', lm))
            if lbl is not None:
                lbl.setText(self._wrist_lm_text(
                    'right', lm, getattr(self.state, f'wrist_R_{lm}')))

    def _finalize_status(self):
        done = all(getattr(self.state, f'wrist_R_{lm}') is not None
                   for lm in ['RSP', 'USP', 'ME', 'LE'])
        if done:
            return "✓  Finalized"
        tmp_done = all(self._wrist_R_tmp.get(lm) is not None
                       for lm in ['RSP', 'USP', 'ME', 'LE'])
        if tmp_done:
            return "Ready — place S4 on R.Forearm then press"
        return "Record RSP/USP/ME/LE first"

    def _offset_text_wrist_R(self, lm, stored, tmp):
        if lm == 'MCP':
            return self._offset_text(stored)
        if stored is not None:
            return f"✓  ({stored[0]:.2f}, {stored[1]:.2f}, {stored[2]:.2f}) cm  [R.Forearm frame]"
        if tmp is not None:
            return f"(tmp)  ({tmp[0]:.2f}, {tmp[1]:.2f}, {tmp[2]:.2f}) cm  [R.Hand frame — needs Finalize]"
        return "Not recorded"

    def _wrist_lm_text(self, side, lm, stored, tmp=None):
        """HTML status text for a wrist landmark cell.
        Frame label is shown at 80% font size (9pt vs 11pt base).
        """
        SMALL = '<span style="font-size:9pt; color:#999999;">'
        END   = '</span>'

        if side == 'left':
            frame = 'L.Hand' if lm == 'MCP' else 'L.Forearm'
        else:
            frame = 'R.Hand' if lm == 'MCP' else 'R.Forearm'

        def fmt(c):
            return f'({c[0]:.2f}, {c[1]:.2f}, {c[2]:.2f}) cm'

        if side == 'right' and lm != 'MCP':
            if stored is not None:
                return (f'✓ {fmt(stored)}<br>'
                        f'{SMALL}[R.Forearm frame]{END}')
            if tmp is not None:
                return (f'(tmp) {fmt(tmp)}<br>'
                        f'{SMALL}[R.Hand frame — needs Finalize]{END}')
            return "Not recorded"

        if stored is None:
            return "Not recorded"
        return (f'✓ {fmt(stored)}<br>'
                f'{SMALL}[{frame} frame]{END}')

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

    def _wrist_save_path(self):
        if not self.state.data_dir:
            return None
        return os.path.join(self.state.data_dir, 'digitization_mode2.json')

    def _wrist_save_path_hint(self):
        p = self._wrist_save_path()
        return os.path.basename(p) if p else "No data folder set"

    def _autosave_wrist(self):
        path = self._wrist_save_path()
        if path is None:
            return
        data = {
            'mode': 2,
            'sensor_L_hand':    self.state.wrist_sensor_L_hand,
            'sensor_R_hand':    self.state.wrist_sensor_R_hand,
            'sensor_L_forearm': self.state.wrist_sensor_L_forearm,
            'sensor_R_ptr':     self.state.wrist_sensor_R_ptr,
            'wrist_L_MCP': self.state.wrist_L_MCP,
            'wrist_L_RSP': self.state.wrist_L_RSP,
            'wrist_L_USP': self.state.wrist_L_USP,
            'wrist_L_LE':  self.state.wrist_L_LE,
            'wrist_L_ME':  self.state.wrist_L_ME,
            'wrist_R_MCP': self.state.wrist_R_MCP,
            'wrist_R_RSP': self.state.wrist_R_RSP,
            'wrist_R_USP': self.state.wrist_R_USP,
            'wrist_R_LE':  self.state.wrist_R_LE,
            'wrist_R_ME':  self.state.wrist_R_ME,
            'wrist_R_tmp': self._wrist_R_tmp,
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        if hasattr(self, '_wrist_save_lbl'):
            self._wrist_save_lbl.setText(
                f"Auto-saved  →  {os.path.basename(path)}")

    def _save_wrist(self):
        self._autosave_wrist()
        if hasattr(self, '_wrist_save_lbl'):
            path = self._wrist_save_path()
            self._wrist_save_lbl.setText(
                f"Saved  →  {os.path.basename(path) if path else '—'}")

    def _load_wrist(self):
        path = self._wrist_save_path()
        if path is None or not os.path.exists(path):
            if hasattr(self, '_wrist_save_lbl'):
                self._wrist_save_lbl.setText("No save file found")
            return
        try:
            with open(path) as f:
                data = json.load(f)
            self.state.wrist_sensor_L_hand    = data.get('sensor_L_hand',    self.state.wrist_sensor_L_hand)
            self.state.wrist_sensor_R_hand    = data.get('sensor_R_hand',    self.state.wrist_sensor_R_hand)
            self.state.wrist_sensor_L_forearm = data.get('sensor_L_forearm', self.state.wrist_sensor_L_forearm)
            self.state.wrist_sensor_R_ptr     = data.get('sensor_R_ptr',     self.state.wrist_sensor_R_ptr)
            for lm in WRIST_LANDMARKS:
                setattr(self.state, f'wrist_L_{lm}', data.get(f'wrist_L_{lm}'))
                setattr(self.state, f'wrist_R_{lm}', data.get(f'wrist_R_{lm}'))
            self._wrist_R_tmp = {k: v for k, v in data.get('wrist_R_tmp', {}).items()}
            self._rebuild_content()
        except Exception as e:
            if hasattr(self, '_wrist_save_lbl'):
                self._wrist_save_lbl.setText(f"Load failed: {e}")

    # ── MODE 3: Full Arm ──────────────────────────────────────

    def _build_arm(self, lay):
        lay.addWidget(self._mode_note(
            "Place a sensor on the distal forearm "
            "and a sensor on the lateral mid-upper arm."))
        lay.addWidget(self._mode_note(
            "Note: In Full Arm mode, the wrist joint must be fixed "
            "to ensure reliable MCP tracking.", warn=True))
        lay.addSpacing(4)

        lay.addWidget(self._bold("Sensor Assignment"))
        arow = QHBoxLayout()
        arow.setSpacing(10)
        assigns = [
            ("L.Forearm:",              'arm_sensor_L_forearm', False),
            ("R.Forearm:",              'arm_sensor_R_forearm', False),
            ("L.UpperArm:",             'arm_sensor_L_upper',   False),
            ("R.UpperArm & Pointer:",   'arm_sensor_R_ptr',     True),
        ]
        non_ptr = []
        for label, attr, is_ptr in assigns:
            l = QLabel(label)
            l.setFont(QFont('Arial', 13))
            l.setStyleSheet("color: #333333;")
            arow.addWidget(l)
            cb = self._sensor_cb(getattr(self.state, attr))
            cb.currentIndexChanged.connect(
                lambda _, a=attr, c=cb: self._save_arm_assign(a, c))
            arow.addWidget(cb)
            arow.addSpacing(8)
            if not is_ptr:
                non_ptr.append(cb)
        arow.addStretch()
        lay.addLayout(arow)

        self._non_ptr_cbs = non_ptr
        for cb in non_ptr:
            cb.currentIndexChanged.connect(lambda _: self._apply_exclusions())
        self._apply_exclusions()
        self._assigned_sensors = {self.state.arm_sensor_L_forearm,
                                   self.state.arm_sensor_R_forearm,
                                   self.state.arm_sensor_L_upper,
                                   self.state.arm_sensor_R_ptr}
        lay.addWidget(self._sep())

        # Landmarks — 4-column grid (same layout as wrist + AP row)
        lay.addWidget(self._bold("Landmarks"))

        grid_w = QWidget()
        grid_w.setStyleSheet("background: transparent;")
        grid = QGridLayout(grid_w)
        grid.setSpacing(6)
        grid.setContentsMargins(0, 0, 0, 0)

        self._grid_header(grid, 0, "Left",  'left')
        self._grid_header(grid, 2, "Right", 'right')

        # Row 1 — MCP (spans 2 cols per side)
        grid.addWidget(self._arm_cell('left',  'MCP'), 1, 0, 1, 2)
        grid.addWidget(self._arm_cell('right', 'MCP'), 1, 2, 1, 2)

        # Row 2 — L.USP | L.RSP | R.RSP | R.USP
        for col, side, lm in [(0, 'left',  'USP'),
                               (1, 'left',  'RSP'),
                               (2, 'right', 'RSP'),
                               (3, 'right', 'USP')]:
            grid.addWidget(self._arm_cell(side, lm), 2, col)

        # Row 3 — L.LE | L.ME | R.ME | R.LE
        for col, side, lm in [(0, 'left',  'LE'),
                               (1, 'left',  'ME'),
                               (2, 'right', 'ME'),
                               (3, 'right', 'LE')]:
            grid.addWidget(self._arm_cell(side, lm), 3, col)

        # Row 4 — AP (spans 2 cols per side)
        grid.addWidget(self._arm_cell('left',  'AP'), 4, 0, 1, 2)
        grid.addWidget(self._arm_cell('right', 'AP'), 4, 2, 1, 2)

        lay.addWidget(grid_w)

        # Finalize
        fin_row = QHBoxLayout()
        self._arm_finalize_btn = QPushButton("Finalize Right Upper Arm  [7]")
        self._arm_finalize_btn.setStyleSheet(BTN)
        self._arm_finalize_btn.clicked.connect(self._finalize_arm_R)
        self._arm_finalize_lbl = QLabel(self._arm_finalize_status())
        self._arm_finalize_lbl.setFont(QFont('Arial', 13))
        self._arm_finalize_lbl.setStyleSheet("color: #555555;")
        fin_row.addWidget(self._arm_finalize_btn)
        fin_row.addSpacing(10)
        fin_row.addWidget(self._arm_finalize_lbl)
        fin_row.addStretch()
        lay.addLayout(fin_row)

        lay.addWidget(self._sep())

        # Save / Load
        sl_row = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(BTN)
        save_btn.clicked.connect(self._save_arm)
        load_btn = QPushButton("Load")
        load_btn.setStyleSheet(BTN)
        load_btn.clicked.connect(self._load_arm)
        self._arm_save_lbl = QLabel(self._arm_save_path_hint())
        self._arm_save_lbl.setFont(QFont('Arial', 13))
        self._arm_save_lbl.setStyleSheet("color: #777777;")
        sl_row.addWidget(save_btn)
        sl_row.addSpacing(8)
        sl_row.addWidget(load_btn)
        sl_row.addSpacing(12)
        sl_row.addWidget(self._arm_save_lbl)
        sl_row.addStretch()
        lay.addLayout(sl_row)

        lay.addWidget(self._sep())

        # Clear buttons
        crow = QHBoxLayout()
        for label, fn in [("Clear Right", self._clear_arm_R),
                          ("Clear Left",  self._clear_arm_L),
                          ("Clear All",   self._clear_arm_all)]:
            b = QPushButton(label)
            b.setStyleSheet(BTN)
            b.clicked.connect(fn)
            crow.addWidget(b)
            crow.addSpacing(8)
        crow.addStretch()
        lay.addLayout(crow)

        # Canvas
        lay.addWidget(self._sep())
        self._canvas = _DigCanvas(self.state, self.liberty, self)
        self._add_canvas_section(lay)

    def _arm_cell(self, side, lm):
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setStyleSheet(
            "QFrame { background: #f8f8f8; border: 1px solid #dddddd;"
            " border-radius: 4px; }"
        )
        vlay = QVBoxLayout(frame)
        vlay.setContentsMargins(8, 6, 8, 6)
        vlay.setSpacing(4)

        color = "#3050d0" if side == 'left' else "#c03030"
        name_lbl = QLabel(ARM_LM_FULL[lm])
        name_lbl.setFont(QFont('Arial', 12, QFont.Bold))
        name_lbl.setStyleSheet(
            f"color: {color}; background: transparent; border: none;")
        vlay.addWidget(name_lbl)

        if side == 'left':
            stored = getattr(self.state, f'arm_L_{lm}')
            status_text = self._arm_lm_text(side, lm, stored)
        else:
            stored = getattr(self.state, f'arm_R_{lm}')
            tmp    = self._arm_R_tmp.get(lm)
            status_text = self._arm_lm_text(side, lm, stored, tmp)

        status_lbl = QLabel(status_text)
        status_lbl.setFont(QFont('Arial', 11))
        status_lbl.setStyleSheet(
            "color: #555555; background: transparent; border: none;")
        status_lbl.setWordWrap(True)
        vlay.addWidget(status_lbl)

        self._arm_status_lbls[(side, lm)] = status_lbl

        idx  = _ARM_LM_IDX[lm]
        hint = f"[F{idx}]" if side == 'left' else f"[{idx}]"
        btn  = QPushButton(f"Record  {hint}")
        btn.setStyleSheet(BTN_SM)
        if side == 'left':
            btn.clicked.connect(
                lambda _, l=lm, s=status_lbl: self._record_arm_L(l, s))
        else:
            btn.clicked.connect(
                lambda _, l=lm, s=status_lbl: self._record_arm_R(l, s))
        if not self._side_active(side):
            btn.setEnabled(False)
        vlay.addWidget(btn)

        return frame

    def _save_arm_assign(self, attr, cb):
        setattr(self.state, attr, cb.currentData())
        self.state.save_config()
        self._refresh_assigned()

    def _record_arm_L(self, lm, status_lbl):
        from digitizer import compute_offset
        ptr_n  = self.state.arm_sensor_R_ptr
        ptr_s  = self.liberty.get_sensor(ptr_n)
        if lm in ('MCP', 'RSP', 'USP'):
            ref_n = self.state.arm_sensor_L_forearm
        else:
            ref_n = self.state.arm_sensor_L_upper
        ref_s = self.liberty.get_sensor(ref_n)
        if ref_s is None or ptr_s is None:
            status_lbl.setText("No sensor data — try again")
            return
        offset = compute_offset(ref_s, ptr_s)
        setattr(self.state, f'arm_L_{lm}', offset)
        self.state.save_config()
        self._autosave_arm()
        threading.Thread(target=beep, args=(880, 120), daemon=True).start()
        status_lbl.setText(self._arm_lm_text('left', lm, offset))

    def _record_arm_R(self, lm, status_lbl):
        from digitizer import compute_offset
        ptr_n  = self.state.arm_sensor_R_ptr
        fore_n = self.state.arm_sensor_R_forearm
        ptr_s  = self.liberty.get_sensor(ptr_n)
        fore_s = self.liberty.get_sensor(fore_n)
        if fore_s is None or ptr_s is None:
            status_lbl.setText("No sensor data — try again")
            return
        offset = compute_offset(fore_s, ptr_s)
        if lm in ('MCP', 'RSP', 'USP'):
            setattr(self.state, f'arm_R_{lm}', offset)
            self.state.save_config()
        else:
            self._arm_R_tmp[lm] = offset
        self._autosave_arm()
        threading.Thread(target=beep, args=(880, 120), daemon=True).start()
        status_lbl.setText(self._arm_lm_text(
            'right', lm, getattr(self.state, f'arm_R_{lm}'), self._arm_R_tmp.get(lm)))

    def _finalize_arm_R(self):
        from digitizer import finalize_forearm
        needed = {lm: self._arm_R_tmp.get(lm) for lm in ['ME', 'LE', 'AP']}
        if any(v is None for v in needed.values()):
            self._arm_finalize_lbl.setText("Record ME/LE/AP first")
            return
        fore_n = self.state.arm_sensor_R_forearm
        upper_n = self.state.arm_sensor_R_ptr
        fore_s  = self.liberty.get_sensor(fore_n)
        upper_s = self.liberty.get_sensor(upper_n)
        if fore_s is None or upper_s is None:
            self._arm_finalize_lbl.setText("No sensor data — try again")
            return
        converted = finalize_forearm(fore_s, upper_s, needed)
        for lm, off in converted.items():
            setattr(self.state, f'arm_R_{lm}', off)
        self._arm_R_tmp.clear()
        self.state.save_config()
        self._autosave_arm()
        threading.Thread(target=_beep_complete, daemon=True).start()
        self._arm_finalize_lbl.setText("✓  ME/LE/AP converted to R.UpperArm frame")
        for lm in ['ME', 'LE', 'AP']:
            lbl = self._arm_status_lbls.get(('right', lm))
            if lbl is not None:
                lbl.setText(self._arm_lm_text(
                    'right', lm, getattr(self.state, f'arm_R_{lm}')))

    def _arm_finalize_status(self):
        done = all(getattr(self.state, f'arm_R_{lm}') is not None
                   for lm in ['ME', 'LE', 'AP'])
        if done:
            return "✓  Finalized"
        tmp_done = all(self._arm_R_tmp.get(lm) is not None
                       for lm in ['ME', 'LE', 'AP'])
        if tmp_done:
            return "Ready — place R.ptr on R.UpperArm then press"
        return "Record ME/LE/AP first"

    def _arm_lm_text(self, side, lm, stored, tmp=None):
        SMALL = '<span style="font-size:9pt; color:#999999;">'
        END   = '</span>'

        if side == 'left':
            frame = 'L.Forearm' if lm in ('MCP', 'RSP', 'USP') else 'L.UpperArm'
        else:
            frame = 'R.Forearm' if lm in ('MCP', 'RSP', 'USP') else 'R.UpperArm'

        def fmt(c):
            return f'({c[0]:.2f}, {c[1]:.2f}, {c[2]:.2f}) cm'

        if side == 'right' and lm not in ('MCP', 'RSP', 'USP'):
            if stored is not None:
                return (f'✓ {fmt(stored)}<br>'
                        f'{SMALL}[R.UpperArm frame]{END}')
            if tmp is not None:
                return (f'(tmp) {fmt(tmp)}<br>'
                        f'{SMALL}[R.Forearm frame — needs Finalize]{END}')
            return "Not recorded"

        if stored is None:
            return "Not recorded"
        return (f'✓ {fmt(stored)}<br>'
                f'{SMALL}[{frame} frame]{END}')

    def _clear_arm_L(self):
        for lm in ARM_LANDMARKS:
            setattr(self.state, f'arm_L_{lm}', None)
        self.state.save_config()
        self._rebuild_content()

    def _clear_arm_R(self):
        for lm in ARM_LANDMARKS:
            setattr(self.state, f'arm_R_{lm}', None)
        self._arm_R_tmp.clear()
        self.state.save_config()
        self._rebuild_content()

    def _clear_arm_all(self):
        self._clear_arm_L()
        self._clear_arm_R()

    def _arm_save_path(self):
        if not self.state.data_dir:
            return None
        return os.path.join(self.state.data_dir, 'digitization_mode3.json')

    def _arm_save_path_hint(self):
        p = self._arm_save_path()
        return os.path.basename(p) if p else "No data folder set"

    def _autosave_arm(self):
        path = self._arm_save_path()
        if path is None:
            return
        data = {
            'mode': 3,
            'sensor_L_forearm': self.state.arm_sensor_L_forearm,
            'sensor_R_forearm': self.state.arm_sensor_R_forearm,
            'sensor_L_upper':   self.state.arm_sensor_L_upper,
            'sensor_R_ptr':     self.state.arm_sensor_R_ptr,
        }
        for lm in ARM_LANDMARKS:
            data[f'arm_L_{lm}'] = getattr(self.state, f'arm_L_{lm}')
            data[f'arm_R_{lm}'] = getattr(self.state, f'arm_R_{lm}')
        data['arm_R_tmp'] = self._arm_R_tmp
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        if hasattr(self, '_arm_save_lbl'):
            self._arm_save_lbl.setText(f"Auto-saved  →  {os.path.basename(path)}")

    def _save_arm(self):
        self._autosave_arm()
        if hasattr(self, '_arm_save_lbl'):
            path = self._arm_save_path()
            self._arm_save_lbl.setText(
                f"Saved  →  {os.path.basename(path) if path else '—'}")

    def _load_arm(self):
        path = self._arm_save_path()
        if path is None or not os.path.exists(path):
            if hasattr(self, '_arm_save_lbl'):
                self._arm_save_lbl.setText("No save file found")
            return
        try:
            with open(path) as f:
                data = json.load(f)
            self.state.arm_sensor_L_forearm = data.get('sensor_L_forearm', self.state.arm_sensor_L_forearm)
            self.state.arm_sensor_R_forearm = data.get('sensor_R_forearm', self.state.arm_sensor_R_forearm)
            self.state.arm_sensor_L_upper   = data.get('sensor_L_upper',   self.state.arm_sensor_L_upper)
            self.state.arm_sensor_R_ptr     = data.get('sensor_R_ptr',     self.state.arm_sensor_R_ptr)
            for lm in ARM_LANDMARKS:
                setattr(self.state, f'arm_L_{lm}', data.get(f'arm_L_{lm}'))
                setattr(self.state, f'arm_R_{lm}', data.get(f'arm_R_{lm}'))
            self._arm_R_tmp = {k: v for k, v in data.get('arm_R_tmp', {}).items()}
            self._rebuild_content()
        except Exception as e:
            if hasattr(self, '_arm_save_lbl'):
                self._arm_save_lbl.setText(f"Load failed: {e}")

    # ── MODE 4: Full Single Arm ───────────────────────────────

    def _build_arm4(self, lay):
        lay.addWidget(self._mode_note(
            "Place a sensor on the dorsum of the hand, "
            "a sensor on the distal forearm, "
            "and a sensor on the lateral mid-upper arm. "
            "Use the 4th sensor as pointer first, then place it on the opposite upper arm."))
        lay.addSpacing(4)

        lay.addWidget(self._bold("Sensor Assignment"))
        arow = QHBoxLayout()
        arow.setSpacing(10)
        assigns = [
            ("Hand:",              'arm4_sensor_hand',    False),
            ("Forearm:",           'arm4_sensor_forearm', False),
            ("UpperArm:",          'arm4_sensor_upper',   False),
            ("UpperArm_opp & Pointer:", 'arm4_sensor_trunk', True),
        ]
        non_ptr = []
        for label, attr, is_ptr in assigns:
            l = QLabel(label)
            l.setFont(QFont('Arial', 13))
            l.setStyleSheet("color: #333333;")
            arow.addWidget(l)
            cb = self._sensor_cb(getattr(self.state, attr))
            cb.currentIndexChanged.connect(
                lambda _, a=attr, c=cb: self._save_arm4_assign(a, c))
            arow.addWidget(cb)
            arow.addSpacing(8)
            if not is_ptr:
                non_ptr.append(cb)
        arow.addStretch()
        lay.addLayout(arow)

        self._non_ptr_cbs = non_ptr
        for cb in non_ptr:
            cb.currentIndexChanged.connect(lambda _: self._apply_exclusions())
        self._apply_exclusions()
        self._assigned_sensors = {self.state.arm4_sensor_hand,
                                   self.state.arm4_sensor_forearm,
                                   self.state.arm4_sensor_upper,
                                   self.state.arm4_sensor_trunk}
        lay.addWidget(self._sep())

        lay.addWidget(self._bold("Landmarks"))

        grid_w = QWidget()
        grid_w.setStyleSheet("background: transparent;")
        grid = QGridLayout(grid_w)
        grid.setSpacing(6)
        grid.setContentsMargins(0, 0, 0, 0)

        side_color = "#c03030" if self._active_hand == 0 else "#3050d0"
        side_label = "Right" if self._active_hand == 0 else "Left"
        hdr = QLabel(side_label)
        hdr.setFont(QFont('Arial', 14, QFont.Bold))
        hdr.setStyleSheet(f"color: {side_color};")
        hdr.setAlignment(Qt.AlignCenter)
        grid.addWidget(hdr, 0, 0)

        for row_idx, lm in enumerate(ARM4_LANDMARKS, 1):
            grid.addWidget(self._arm4_cell(lm), row_idx, 0)

        lay.addWidget(grid_w)

        # Finalize Trunk
        fin_row = QHBoxLayout()
        self._arm4_finalize_btn = QPushButton("Finalize UpperArm_opp  [8]")
        self._arm4_finalize_btn.setStyleSheet(BTN)
        self._arm4_finalize_btn.clicked.connect(self._finalize_arm4_trunk)
        self._arm4_finalize_lbl = QLabel(self._arm4_finalize_status())
        self._arm4_finalize_lbl.setFont(QFont('Arial', 13))
        self._arm4_finalize_lbl.setStyleSheet("color: #555555;")
        fin_row.addWidget(self._arm4_finalize_btn)
        fin_row.addSpacing(10)
        fin_row.addWidget(self._arm4_finalize_lbl)
        fin_row.addStretch()
        lay.addLayout(fin_row)

        lay.addWidget(self._sep())

        # Save / Load
        sl_row = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(BTN)
        save_btn.clicked.connect(self._save_arm4)
        load_btn = QPushButton("Load")
        load_btn.setStyleSheet(BTN)
        load_btn.clicked.connect(self._load_arm4)
        self._arm4_save_lbl = QLabel(self._arm4_save_path_hint())
        self._arm4_save_lbl.setFont(QFont('Arial', 13))
        self._arm4_save_lbl.setStyleSheet("color: #777777;")
        sl_row.addWidget(save_btn)
        sl_row.addSpacing(8)
        sl_row.addWidget(load_btn)
        sl_row.addSpacing(12)
        sl_row.addWidget(self._arm4_save_lbl)
        sl_row.addStretch()
        lay.addLayout(sl_row)

        lay.addWidget(self._sep())

        # Clear
        crow = QHBoxLayout()
        clear_btn = QPushButton("Clear All")
        clear_btn.setStyleSheet(BTN)
        clear_btn.clicked.connect(self._clear_arm4_all)
        crow.addWidget(clear_btn)
        crow.addStretch()
        lay.addLayout(crow)

        # Canvas
        lay.addWidget(self._sep())
        self._canvas = _DigCanvas(self.state, self.liberty, self)
        self._add_canvas_section(lay)

    def _arm4_cell(self, lm):
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setStyleSheet(
            "QFrame { background: #f8f8f8; border: 1px solid #dddddd;"
            " border-radius: 4px; }"
        )
        vlay = QVBoxLayout(frame)
        vlay.setContentsMargins(8, 6, 8, 6)
        vlay.setSpacing(4)

        color = "#c03030" if self._active_hand == 0 else "#3050d0"
        name_lbl = QLabel(ARM4_LM_FULL[lm])
        name_lbl.setFont(QFont('Arial', 12, QFont.Bold))
        name_lbl.setStyleSheet(
            f"color: {color}; background: transparent; border: none;")
        vlay.addWidget(name_lbl)

        stored = getattr(self.state, f'arm4_{lm}')
        tmp    = self._arm4_tmp.get(lm)
        status_lbl = QLabel(self._arm4_lm_text(lm, stored, tmp))
        status_lbl.setFont(QFont('Arial', 11))
        status_lbl.setStyleSheet(
            "color: #555555; background: transparent; border: none;")
        status_lbl.setWordWrap(True)
        vlay.addWidget(status_lbl)

        self._arm4_status_lbls[lm] = status_lbl

        idx = _ARM4_LM_IDX[lm]
        btn = QPushButton(f"Record  [{idx}]")
        btn.setStyleSheet(BTN_SM)
        btn.clicked.connect(lambda _, l=lm, s=status_lbl: self._record_arm4(l, s))
        vlay.addWidget(btn)

        return frame

    def _save_arm4_assign(self, attr, cb):
        setattr(self.state, attr, cb.currentData())
        self.state.save_config()
        self._refresh_assigned()

    def _record_arm4(self, lm, status_lbl):
        from digitizer import compute_offset
        ptr_n = self.state.arm4_sensor_trunk
        ptr_s = self.liberty.get_sensor(ptr_n)
        if ptr_s is None:
            status_lbl.setText("No sensor data — try again")
            return

        if lm == 'MCP':
            ref_n = self.state.arm4_sensor_hand
        elif lm in ('USP', 'RSP'):
            ref_n = self.state.arm4_sensor_forearm
        else:  # ME, LE, AP, AP_opp
            ref_n = self.state.arm4_sensor_upper

        ref_s = self.liberty.get_sensor(ref_n)
        if ref_s is None:
            status_lbl.setText("No sensor data — try again")
            return

        offset = compute_offset(ref_s, ptr_s)

        if lm == 'AP_opp':
            self._arm4_tmp['AP_opp'] = offset
        else:
            setattr(self.state, f'arm4_{lm}', offset)
            self.state.save_config()

        self._autosave_arm4()
        threading.Thread(target=beep, args=(880, 120), daemon=True).start()
        status_lbl.setText(self._arm4_lm_text(
            lm, getattr(self.state, f'arm4_{lm}'), self._arm4_tmp.get(lm)))

    def _finalize_arm4_trunk(self):
        from digitizer import finalize_forearm
        ap_opp_tmp = self._arm4_tmp.get('AP_opp')
        if ap_opp_tmp is None:
            self._arm4_finalize_lbl.setText("Record AP_opp first")
            return
        upper_n = self.state.arm4_sensor_upper
        trunk_n = self.state.arm4_sensor_trunk
        upper_s = self.liberty.get_sensor(upper_n)
        trunk_s = self.liberty.get_sensor(trunk_n)
        if upper_s is None or trunk_s is None:
            self._arm4_finalize_lbl.setText("No sensor data — try again")
            return
        converted = finalize_forearm(upper_s, trunk_s, {'AP_opp': ap_opp_tmp})
        self.state.arm4_AP_opp = converted['AP_opp']
        self._arm4_tmp.clear()
        self.state.save_config()
        self._autosave_arm4()
        threading.Thread(target=_beep_complete, daemon=True).start()
        self._arm4_finalize_lbl.setText("✓  Shoulder_opp converted to UpperArm_opp frame")
        lbl = self._arm4_status_lbls.get('AP_opp')
        if lbl is not None:
            lbl.setText(self._arm4_lm_text('AP_opp', self.state.arm4_AP_opp))

    def _arm4_finalize_status(self):
        if self.state.arm4_AP_opp is not None:
            return "✓  Finalized"
        if self._arm4_tmp.get('AP_opp') is not None:
            return "Ready — place S4 on UpperArm_opp then press"
        return "Record AP_opp first"

    def _arm4_lm_text(self, lm, stored, tmp=None):
        SMALL = '<span style="font-size:9pt; color:#999999;">'
        END   = '</span>'

        if lm == 'MCP':
            frame = 'Hand'
        elif lm in ('USP', 'RSP'):
            frame = 'Forearm'
        elif lm in ('ME', 'LE', 'AP'):
            frame = 'UpperArm'
        else:
            frame = 'Trunk'

        def fmt(c):
            return f'({c[0]:.2f}, {c[1]:.2f}, {c[2]:.2f}) cm'

        if lm == 'AP_opp':
            if stored is not None:
                return (f'✓ {fmt(stored)}<br>'
                        f'{SMALL}[UpperArm_opp frame]{END}')
            if tmp is not None:
                return (f'(tmp) {fmt(tmp)}<br>'
                        f'{SMALL}[UpperArm frame — needs Finalize]{END}')
            return "Not recorded"

        if stored is None:
            return "Not recorded"
        return (f'✓ {fmt(stored)}<br>'
                f'{SMALL}[{frame} frame]{END}')

    def _clear_arm4_all(self):
        for lm in ARM4_LANDMARKS:
            setattr(self.state, f'arm4_{lm}', None)
        self._arm4_tmp.clear()
        self.state.save_config()
        self._rebuild_content()

    def _arm4_save_path(self):
        if not self.state.data_dir:
            return None
        side = 'right' if self._active_hand == 0 else 'left'
        return os.path.join(self.state.data_dir, f'digitization_mode4_{side}.json')

    def _arm4_save_path_hint(self):
        p = self._arm4_save_path()
        if p is None:
            return "No data folder set"
        name = os.path.basename(p)
        return f"{name}  ✓ exists" if os.path.exists(p) else f"{name}  (not saved yet)"

    def _autosave_arm4(self):
        path = self._arm4_save_path()
        if path is None:
            return
        data = {
            'mode': 4,
            'hand_setup':     self._active_hand,
            'sensor_hand':    self.state.arm4_sensor_hand,
            'sensor_forearm': self.state.arm4_sensor_forearm,
            'sensor_upper':   self.state.arm4_sensor_upper,
            'sensor_trunk':   self.state.arm4_sensor_trunk,
        }
        for lm in ARM4_LANDMARKS:
            data[f'arm4_{lm}'] = getattr(self.state, f'arm4_{lm}')
        data['arm4_tmp'] = self._arm4_tmp
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        if hasattr(self, '_arm4_save_lbl'):
            self._arm4_save_lbl.setText(f"Auto-saved  →  {os.path.basename(path)}")

    def _save_arm4(self):
        self._autosave_arm4()
        if hasattr(self, '_arm4_save_lbl'):
            path = self._arm4_save_path()
            self._arm4_save_lbl.setText(
                f"Saved  →  {os.path.basename(path) if path else '—'}")

    def _load_arm4(self):
        path = self._arm4_save_path()
        if path is None or not os.path.exists(path):
            if hasattr(self, '_arm4_save_lbl'):
                self._arm4_save_lbl.setText("No save file found")
            return
        try:
            with open(path) as f:
                data = json.load(f)
            self.state.arm4_sensor_hand    = data.get('sensor_hand',    self.state.arm4_sensor_hand)
            self.state.arm4_sensor_forearm = data.get('sensor_forearm', self.state.arm4_sensor_forearm)
            self.state.arm4_sensor_upper   = data.get('sensor_upper',   self.state.arm4_sensor_upper)
            self.state.arm4_sensor_trunk   = data.get('sensor_trunk',   self.state.arm4_sensor_trunk)
            for lm in ARM4_LANDMARKS:
                setattr(self.state, f'arm4_{lm}', data.get(f'arm4_{lm}'))
            self._arm4_tmp = {k: v for k, v in data.get('arm4_tmp', {}).items()}
            self._rebuild_content()
        except Exception as e:
            if hasattr(self, '_arm4_save_lbl'):
                self._arm4_save_lbl.setText(f"Load failed: {e}")

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

        # MCP mode: live MCP positions + canvas
        if self.state.dig_mode == 1:
            self._update_mcp_positions()
        if self._canvas is not None:
            self._canvas.update()

    def _refresh_sensor_lbl(self, lbl, sensor_n):
        s      = self.liberty.get_sensor(sensor_n)
        active = self.liberty.is_sensor_active(sensor_n)
        assigned = sensor_n in self._assigned_sensors
        if s is None or not active:
            lbl.setText("● INACTIVE")
            lbl.setStyleSheet("color: #dc3232;")
        else:
            y = s.y * 2.54 - self.state.sensor_y_offset
            z = s.z * 2.54 - self.state.sensor_z_offset
            x = s.x * 2.54 - self.state.sensor_x_offset
            lbl.setText(f"● ACTIVE    Y: {y:.1f}   Z: {z:.1f}   X: {x:.1f} cm")
            lbl.setStyleSheet("color: #228822;" if assigned else "color: #888888;")

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
            lbl.setText(f"Y: {y:.1f}   Z: {z:.1f}   X: {pos[0] - self.state.sensor_x_offset:.1f} cm")
            lbl.setStyleSheet("color: #228822;")

    # ── helpers ───────────────────────────────────────────────

    def _mode_note(self, text, warn=False):
        lbl = QLabel(text)
        lbl.setFont(QFont('Arial', 13))
        if warn:
            lbl.setStyleSheet(
                "color: #886600; background: #fffbe6; border: 1px solid #e0c840;"
                " border-radius: 4px; padding: 6px 10px;")
        else:
            lbl.setStyleSheet(
                "color: #336699; background: #eef4fb; border: 1px solid #aaccee;"
                " border-radius: 4px; padding: 6px 10px;")
        lbl.setWordWrap(True)
        return lbl

    def _side_active(self, side):
        """Return True if this side is enabled under the current hand setup."""
        h = self._active_hand
        if h == 0: return side == 'right'
        if h == 1: return side == 'left'
        return True  # Both

    def _grid_header(self, grid, col, text, side):
        active = self._side_active(side)
        color  = ("#3050d0" if side == 'left' else "#c03030") if active else "#aaaaaa"
        hdr = QLabel(text)
        hdr.setFont(QFont('Arial', 14, QFont.Bold))
        hdr.setStyleSheet(f"color: {color};")
        hdr.setAlignment(Qt.AlignCenter)
        grid.addWidget(hdr, 0, col, 1, 2)

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

    def _refresh_assigned(self):
        mode = self.state.dig_mode
        if mode == 0:
            self._assigned_sensors = {self.state.dig_sensor_right,
                                       self.state.dig_sensor_left}
        elif mode == 1:
            self._assigned_sensors = {self.state.dig_sensor_right,
                                       self.state.dig_sensor_left,
                                       self.state.mcp_sensor_pointer}
        elif mode == 2:
            self._assigned_sensors = {self.state.wrist_sensor_L_hand,
                                       self.state.wrist_sensor_R_hand,
                                       self.state.wrist_sensor_L_forearm,
                                       self.state.wrist_sensor_R_ptr}
        elif mode == 3:
            self._assigned_sensors = {self.state.arm_sensor_L_forearm,
                                       self.state.arm_sensor_R_forearm,
                                       self.state.arm_sensor_L_upper,
                                       self.state.arm_sensor_R_ptr}
        elif mode == 4:
            self._assigned_sensors = {self.state.arm4_sensor_hand,
                                       self.state.arm4_sensor_forearm,
                                       self.state.arm4_sensor_upper,
                                       self.state.arm4_sensor_trunk}

    def _apply_exclusions(self):
        counts = Counter(cb.currentData() for cb in self._non_ptr_cbs)
        for cb in self._non_ptr_cbs:
            own = cb.currentData()
            for i in range(cb.count()):
                val = cb.itemData(i)
                other_uses = counts[val] - (1 if val == own else 0)
                cb.model().item(i).setEnabled(other_uses == 0 or val == own)

    def _live_row_widget(self, lay, sensor_n):
        row = QHBoxLayout()
        rl = QLabel(f"S{sensor_n}:")
        rl.setFixedWidth(50)
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

    # ── canvas + 3D button helper ─────────────────────────────

    def _add_canvas_section(self, lay):
        lay.addWidget(self._canvas)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        view3d_btn = QPushButton("View 3D")
        view3d_btn.setStyleSheet(BTN)
        view3d_btn.clicked.connect(self._show_3d_view)
        btn_row.addWidget(view3d_btn)
        lay.addLayout(btn_row)

    # ── 3D view ───────────────────────────────────────────────

    def _check_3d_ready(self):
        mode = self.state.dig_mode
        hand = self._active_hand
        st   = self.state

        if mode == 0:
            return True, ""

        sides = []
        if mode == 4:
            sides = ['single']
        else:
            if hand in (0, 2): sides.append('right')
            if hand in (1, 2): sides.append('left')

        missing = []
        if mode == 1:
            for s in sides:
                attr = 'mcp_offset_right' if s == 'right' else 'mcp_offset_left'
                if getattr(st, attr) is None:
                    missing.append(f'{s.capitalize()} MCP')
        elif mode == 2:
            for s in sides:
                p = 'wrist_R' if s == 'right' else 'wrist_L'
                for lm in WRIST_LANDMARKS:
                    if getattr(st, f'{p}_{lm}') is None:
                        missing.append(f'{s.capitalize()} {lm}')
        elif mode == 3:
            for s in sides:
                p = 'arm_R' if s == 'right' else 'arm_L'
                for lm in ARM_LANDMARKS:
                    if getattr(st, f'{p}_{lm}') is None:
                        missing.append(f'{s.capitalize()} {lm}')
        elif mode == 4:
            for lm in ARM4_LANDMARKS:
                if getattr(st, f'arm4_{lm}') is None:
                    missing.append(lm)

        if missing:
            return False, "Not yet recorded:\n  " + ",  ".join(missing)
        return True, ""

    def _show_3d_view(self):
        ok, msg = self._check_3d_ready()
        if not ok:
            QMessageBox.warning(self, "Incomplete Digitization",
                                msg + "\n\nRecord all landmarks before viewing in 3D.")
            return

        try:
            from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
            from matplotlib.figure import Figure
            from mpl_toolkits.mplot3d.art3d import Line3DCollection, Poly3DCollection
        except ImportError:
            QMessageBox.warning(self, "Missing dependency",
                                "matplotlib is required.\n pip install matplotlib")
            return

        from digitizer import track_mcp
        import numpy as np

        st   = self.state
        lib  = self.liberty
        mode = st.dig_mode
        hand = self._active_hand

        def sensor_xyz(n):
            s = lib.get_sensor(n)
            if s is None:
                return None
            return (s.y * 2.54 - st.sensor_y_offset,
                    s.z * 2.54 - st.sensor_z_offset,
                    s.x * 2.54 - st.sensor_x_offset)

        def lm_xyz(sensor_n, offset):
            if offset is None:
                return None
            s = lib.get_sensor(sensor_n)
            if s is None:
                return None
            pos = track_mcp(s, offset)
            return (pos[1] - st.sensor_y_offset,
                    pos[2] - st.sensor_z_offset,
                    pos[0] - st.sensor_x_offset)

        def mid3(a, b):
            if a and b:
                return ((a[0]+b[0])/2, (a[1]+b[1])/2, (a[2]+b[2])/2)
            return None

        # ── collect data ──────────────────────────────────────
        sensor_pts  = {}
        sensor_clrs = {}
        lm_pts      = {}
        lm_clrs     = {}
        joint_pts   = {}   # wrist / elbow joints (computed midpoints)
        joint_clrs  = {}
        lines        = []   # skeleton lines (full mode)
        simple_lines = []   # skeleton lines (simplified — same geometry)
        trunk_pairs  = []   # (pt1, pt2) pairs for trunk ovals

        def add_line(a, b):
            if a and b:
                lines.append((a, b))
                simple_lines.append((a, b))

        R, L, G = '#d03030', '#3050d0', '#888888'

        sides = []
        if mode == 4:
            sides = ['single']
        else:
            if hand in (0, 2): sides.append('right')
            if hand in (1, 2): sides.append('left')

        if mode == 0:
            color_map = {'right': R, 'left': L}
            sn_map    = {'right': st.dig_sensor_right, 'left': st.dig_sensor_left}
            for s in sides:
                pt = sensor_xyz(sn_map[s])
                if pt is not None:
                    sensor_pts[f'S_{s[0].upper()}'] = pt
                    sensor_clrs[f'S_{s[0].upper()}'] = color_map[s]

        elif mode == 1:
            color_map = {'right': R, 'left': L}
            sn_map    = {'right': st.dig_sensor_right, 'left': st.dig_sensor_left}
            attr_map  = {'right': 'mcp_offset_right', 'left': 'mcp_offset_left'}
            ptr_pt = sensor_xyz(st.mcp_sensor_pointer)
            if ptr_pt is not None:
                sensor_pts['S_ptr'] = ptr_pt
                sensor_clrs['S_ptr'] = G
            for s in sides:
                c  = color_map[s]
                sp = sensor_xyz(sn_map[s])
                if sp is not None:
                    sensor_pts[f'S_{s[0].upper()}'] = sp
                    sensor_clrs[f'S_{s[0].upper()}'] = c
                mcp = lm_xyz(sn_map[s], getattr(st, attr_map[s]))
                if mcp is not None:
                    lm_pts[f'MCP_{s[0].upper()}'] = mcp
                    lm_clrs[f'MCP_{s[0].upper()}'] = c
                    add_line(sp, mcp)

        elif mode == 2:
            sn_map = {
                'right': (st.wrist_sensor_R_hand, st.wrist_sensor_R_ptr,     R, 'wrist_R'),
                'left':  (st.wrist_sensor_L_hand, st.wrist_sensor_L_forearm, L, 'wrist_L'),
            }
            ptr_pt = sensor_xyz(st.wrist_sensor_R_ptr)
            if ptr_pt is not None:
                sensor_pts['S_ptr'] = ptr_pt
                sensor_clrs['S_ptr'] = G
            for s in sides:
                hand_n, fore_n, c, prefix = sn_map[s]
                for lbl, n in [(f'S_{s[0].upper()}H', hand_n),
                                (f'S_{s[0].upper()}F', fore_n)]:
                    pt = sensor_xyz(n)
                    if pt is not None:
                        sensor_pts[lbl] = pt
                        sensor_clrs[lbl] = c
                for lm, ref_n in [('MCP', hand_n),
                                   ('RSP', fore_n), ('USP', fore_n),
                                   ('ME',  fore_n), ('LE',  fore_n)]:
                    pt = lm_xyz(ref_n, getattr(st, f'{prefix}_{lm}'))
                    key = f'{lm}_{s[0].upper()}'
                    if pt is not None:
                        lm_pts[key] = pt
                        lm_clrs[key] = c
                key = s[0].upper()
                wj = mid3(lm_pts.get(f'RSP_{key}'), lm_pts.get(f'USP_{key}'))
                ej = mid3(lm_pts.get(f'ME_{key}'),  lm_pts.get(f'LE_{key}'))
                if wj:
                    joint_pts[f'Wrist_{key}'] = wj
                    joint_clrs[f'Wrist_{key}'] = c
                if ej:
                    joint_pts[f'Elbow_{key}'] = ej
                    joint_clrs[f'Elbow_{key}'] = c
                add_line(wj, lm_pts.get(f'MCP_{key}'))
                add_line(wj, ej)

        elif mode == 3:
            sn_map = {
                'right': (st.arm_sensor_R_forearm, st.arm_sensor_R_ptr,   R, 'arm_R'),
                'left':  (st.arm_sensor_L_forearm, st.arm_sensor_L_upper, L, 'arm_L'),
            }
            for s in sides:
                fore_n, upper_n, c, prefix = sn_map[s]
                for lbl, n in [(f'S_{s[0].upper()}F', fore_n),
                                (f'S_{s[0].upper()}U', upper_n)]:
                    pt = sensor_xyz(n)
                    if pt is not None:
                        sensor_pts[lbl] = pt
                        sensor_clrs[lbl] = c
                for lm, ref_n in [('MCP', fore_n), ('RSP', fore_n), ('USP', fore_n),
                                   ('ME', upper_n), ('LE', upper_n), ('AP', upper_n)]:
                    pt = lm_xyz(ref_n, getattr(st, f'{prefix}_{lm}'))
                    display_lm = 'Shoulder' if lm == 'AP' else lm
                    key = f'{display_lm}_{s[0].upper()}'
                    if pt is not None:
                        lm_pts[key] = pt
                        lm_clrs[key] = c
                key = s[0].upper()
                wj = mid3(lm_pts.get(f'RSP_{key}'), lm_pts.get(f'USP_{key}'))
                ej = mid3(lm_pts.get(f'ME_{key}'),  lm_pts.get(f'LE_{key}'))
                if wj:
                    joint_pts[f'Wrist_{key}'] = wj
                    joint_clrs[f'Wrist_{key}'] = c
                if ej:
                    joint_pts[f'Elbow_{key}'] = ej
                    joint_clrs[f'Elbow_{key}'] = c
                add_line(wj, lm_pts.get(f'MCP_{key}'))
                add_line(wj, ej)
                add_line(ej, lm_pts.get(f'Shoulder_{key}'))
            if 'Shoulder_R' in lm_pts and 'Shoulder_L' in lm_pts:
                trunk_pairs.append((lm_pts['Shoulder_R'], lm_pts['Shoulder_L']))

        elif mode == 4:
            side_c = R if st.dig_hand_setup == 0 else L
            for lbl, n in [('S_hand',      st.arm4_sensor_hand),
                            ('S_forearm',   st.arm4_sensor_forearm),
                            ('S_upper',     st.arm4_sensor_upper),
                            ('S_upper_opp', st.arm4_sensor_trunk)]:
                pt = sensor_xyz(n)
                if pt is not None:
                    sensor_pts[lbl] = pt
                    sensor_clrs[lbl] = side_c
            for lm, ref_n in [('MCP', st.arm4_sensor_hand),
                               ('USP', st.arm4_sensor_forearm),
                               ('RSP', st.arm4_sensor_forearm),
                               ('ME',  st.arm4_sensor_upper),
                               ('LE',  st.arm4_sensor_upper),
                               ('AP',  st.arm4_sensor_upper)]:
                pt = lm_xyz(ref_n, getattr(st, f'arm4_{lm}'))
                display_lm = 'Shoulder' if lm == 'AP' else lm
                if pt is not None:
                    lm_pts[display_lm] = pt
                    lm_clrs[display_lm] = side_c
            if st.arm4_AP_opp is not None:
                pt = lm_xyz(st.arm4_sensor_trunk, st.arm4_AP_opp)
                if pt is not None:
                    lm_pts['Shoulder_opp'] = pt
                    lm_clrs['Shoulder_opp'] = side_c
            wj = mid3(lm_pts.get('RSP'), lm_pts.get('USP'))
            ej = mid3(lm_pts.get('ME'),  lm_pts.get('LE'))
            if wj:
                joint_pts['Wrist'] = wj
                joint_clrs['Wrist'] = side_c
            if ej:
                joint_pts['Elbow'] = ej
                joint_clrs['Elbow'] = side_c
            add_line(wj, lm_pts.get('MCP'))
            add_line(wj, ej)
            add_line(ej, lm_pts.get('Shoulder'))
            if 'Shoulder' in lm_pts and 'Shoulder_opp' in lm_pts:
                trunk_pairs.append((lm_pts['Shoulder'], lm_pts['Shoulder_opp']))

        # Simplified: key anatomical points + skeleton only
        # (MCP, wrist joint, elbow joint, AP/shoulder, AP_opp)
        SIMPLE_LM_KEYS = {'MCP', 'MCP_R', 'MCP_L',
                          'Shoulder', 'Shoulder_R', 'Shoulder_L', 'Shoulder_opp'}

        # ── desk-coordinate axis helper ───────────────────────
        def _equalize_axes(ax_3d):
            # Fix axes to physical desk dimensions for spatial accuracy
            y_range = st.WORKSPACE_Y_MAX - st.WORKSPACE_Y_MIN  # lateral, ~86.36 cm
            z_range = st.WORKSPACE_Z_MAX - st.WORKSPACE_Z_MIN  # anterior, ~55.88 cm
            x_range = 50.0                                      # elevation, ~50 cm
            ax_3d.set_xlim(st.WORKSPACE_Y_MIN, st.WORKSPACE_Y_MAX)
            ax_3d.set_ylim(st.WORKSPACE_Z_MIN, st.WORKSPACE_Z_MAX)
            ax_3d.set_zlim(0, x_range)
            ax_3d.set_box_aspect([y_range, z_range, x_range])

        # ── render function ───────────────────────────────────
        side_str = {0: 'Right', 1: 'Left', 2: 'Both'}.get(hand, 'Single')

        fig = Figure(figsize=(7, 6), facecolor='#f8f8f8')
        ax  = fig.add_subplot(111, projection='3d')

        simplified_state = [False]

        def render(simplified):
            ax.clear()
            ax.set_facecolor('#f8f8f8')
            ax.set_xlabel('Y  (lateral, cm)',   fontsize=9)
            ax.set_ylabel('Z  (anterior, cm)',  fontsize=9)
            ax.set_zlabel('X  (elevation, cm)', fontsize=9)
            view_lbl = 'Simplified' if simplified else 'Full'
            ax.set_title(f'Mode {mode}  |  {side_str}  —  {view_lbl}', fontsize=11)

            draw_lines = simple_lines if simplified else lines
            if draw_lines:
                segs = [[(a[0], a[1], a[2]), (b[0], b[1], b[2])]
                        for a, b in draw_lines]
                ax.add_collection3d(
                    Line3DCollection(segs, colors='#333333', linewidths=2, zorder=1))

            if not simplified:
                for lbl, (x, y, z) in sensor_pts.items():
                    ax.scatter(x, y, z, c=sensor_clrs[lbl], s=55,
                               depthshade=False, zorder=3)
                    ax.text(x, y, z, f'  {lbl}', fontsize=7,
                            color=sensor_clrs[lbl])
                for lbl, (x, y, z) in lm_pts.items():
                    ax.scatter(x, y, z, c=lm_clrs[lbl], s=35, marker='^',
                               depthshade=False, zorder=4)
                    ax.text(x, y, z, f'  {lbl}', fontsize=7,
                            color=lm_clrs[lbl])
                for lbl, (x, y, z) in joint_pts.items():
                    ax.scatter(x, y, z, c='#333333', s=50,
                               depthshade=False, zorder=5)
                    ax.text(x, y, z, f'  {lbl}', fontsize=7, color='#333333')
            else:
                # Simplified: joints + MCP/AP/AP_opp only
                for lbl, (x, y, z) in joint_pts.items():
                    ax.scatter(x, y, z, c='#333333', s=60,
                               depthshade=False, zorder=5)
                    ax.text(x, y, z, f'  {lbl}', fontsize=8,
                            color='#333333', fontweight='bold')
                for lbl, (x, y, z) in lm_pts.items():
                    if lbl in SIMPLE_LM_KEYS:
                        ax.scatter(x, y, z, c=lm_clrs[lbl], s=50, marker='^',
                                   depthshade=False, zorder=4)
                        ax.text(x, y, z, f'  {lbl}', fontsize=8,
                                color=lm_clrs[lbl], fontweight='bold')

            ax.grid(True, linewidth=0.4)

            # Trunk oval cylinder (elliptic cylinder, top at shoulder height)
            for (p1, p2) in trunk_pairs:
                cx    = (p1[0] + p2[0]) / 2
                cy    = (p1[1] + p2[1]) / 2
                z_top = (p1[2] + p2[2]) / 2     # shoulder elevation = top
                z_bot = 0.0                      # down to table surface

                # Major axis: shoulder-to-shoulder in horizontal plane
                a_x   = (p2[0] - p1[0]) / 2
                a_y   = (p2[1] - p1[1]) / 2
                a_len = np.sqrt(a_x**2 + a_y**2)
                if a_len < 1e-6:
                    continue
                a_ux, a_uy = a_x / a_len, a_y / a_len
                # Minor axis: perpendicular in horizontal plane, 5 cm semi-minor (10 cm depth)
                b_ux, b_uy = -a_uy, a_ux
                semi_minor  = 5.0

                theta = np.linspace(0, 2 * np.pi, 65)  # 65 pts to close ring
                rx = cx + np.cos(theta) * a_len * a_ux + np.sin(theta) * semi_minor * b_ux
                ry = cy + np.cos(theta) * a_len * a_uy + np.sin(theta) * semi_minor * b_uy

                ring_top = np.column_stack([rx, ry, np.full(65, z_top)])
                ring_bot = np.column_stack([rx, ry, np.full(65, z_bot)])

                # Side surface — 64 quads connecting top and bottom rings
                verts = [[(ring_top[i,   0], ring_top[i,   1], ring_top[i,   2]),
                           (ring_top[i+1, 0], ring_top[i+1, 1], ring_top[i+1, 2]),
                           (ring_bot[i+1, 0], ring_bot[i+1, 1], ring_bot[i+1, 2]),
                           (ring_bot[i,   0], ring_bot[i,   1], ring_bot[i,   2])]
                          for i in range(64)]
                poly = Poly3DCollection(verts, alpha=0.75,
                                         facecolor='#cccccc', edgecolor='none')
                ax.add_collection3d(poly)

                # Top cap (filled oval)
                top_cap = Poly3DCollection(
                    [list(zip(ring_top[:, 0], ring_top[:, 1], ring_top[:, 2]))],
                    alpha=0.75, facecolor='#cccccc', edgecolor='#666666', linewidth=1.0)
                ax.add_collection3d(top_cap)

                # Bottom ring outline only
                ax.plot(ring_bot[:, 0], ring_bot[:, 1], ring_bot[:, 2],
                        color='#666666', linewidth=1.0)

            _equalize_axes(ax)
            fig.tight_layout()
            canvas.draw()

        # ── dialog ────────────────────────────────────────────
        from PyQt5.QtWidgets import (QDialog, QVBoxLayout as _VL,
                                     QHBoxLayout as _HL)
        dlg = QDialog(self)
        dlg.setWindowTitle(f"3D View — Mode {mode}  |  {side_str}")
        dlg.resize(760, 700)
        vl = _VL(dlg)
        vl.setContentsMargins(6, 6, 6, 6)
        vl.setSpacing(6)

        # Toolbar
        toolbar = _HL()
        toolbar.setSpacing(6)

        BTN3D = ("QPushButton { background:#777; color:white; border:none;"
                 " border-radius:4px; font-size:13px; padding:5px 14px; }"
                 "QPushButton:hover { background:#999; }")

        for lbl, ev, az in [("Frontal",    0, -90),
                             ("Sagittal",   0,   0),
                             ("Horizontal", 90, -90)]:
            b = QPushButton(lbl)
            b.setStyleSheet(BTN3D)
            b.clicked.connect(lambda _, e=ev, a=az: (
                ax.view_init(elev=e, azim=a), canvas.draw()))
            toolbar.addWidget(b)

        toolbar.addSpacing(20)
        toggle_btn = QPushButton("Simplified")
        toggle_btn.setStyleSheet(BTN3D)

        def _toggle():
            simplified_state[0] = not simplified_state[0]
            toggle_btn.setText("Full" if simplified_state[0] else "Simplified")
            render(simplified_state[0])

        toggle_btn.clicked.connect(_toggle)
        toolbar.addWidget(toggle_btn)

        toolbar.addSpacing(20)
        save_fig_btn = QPushButton("Save PNG")
        save_fig_btn.setStyleSheet(BTN3D)

        def _save_fig():
            import datetime
            if not st.data_dir:
                QMessageBox.warning(dlg, "No data folder",
                                    "Set a data folder in the menu first.")
                return
            ts       = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            side_tag = {0: 'right', 1: 'left', 2: 'both'}.get(hand, 'single')
            fname    = os.path.join(st.data_dir,
                                    f"3d_view_mode{mode}_{side_tag}_{ts}.png")
            fig.savefig(fname, dpi=150, bbox_inches='tight', facecolor='#f8f8f8')
            save_fig_btn.setText("Saved!")
            QTimer.singleShot(2000, lambda: save_fig_btn.setText("Save PNG"))

        save_fig_btn.clicked.connect(_save_fig)
        toolbar.addWidget(save_fig_btn)
        toolbar.addStretch()
        vl.addLayout(toolbar)

        canvas = FigureCanvasQTAgg(fig)
        vl.addWidget(canvas)

        render(False)
        dlg.show()
