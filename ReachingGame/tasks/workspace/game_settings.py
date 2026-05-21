from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QComboBox, QFrame, QCheckBox,
                             QSpinBox, QDoubleSpinBox)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from screens.utils import CooldownButton

BTN = """
QPushButton {
    background-color: #888888; color: white; border: none;
    border-radius: 5px; font-size: 15px; padding: 6px 14px;
}
QPushButton:hover   { background-color: #999999; }
QPushButton:pressed { background-color: #777777; }
"""

SPIN = (
    "QDoubleSpinBox, QSpinBox { background:#ffffff; color:#000000;"
    " border:1px solid #aaaaaa; border-radius:4px; padding:2px 6px; font-size:14px; }"
    "QDoubleSpinBox::up-button, QSpinBox::up-button { width:0; }"
    "QDoubleSpinBox::down-button, QSpinBox::down-button { width:0; }"
)

CHKBOX = (
    "QCheckBox { font-size:15px; color:#000000; spacing:6px; }"
    "QCheckBox::indicator { width:18px; height:18px; }"
)


def _label(text, w=None):
    lbl = QLabel(text)
    lbl.setStyleSheet("color: #444444; font-size: 14px;")
    if w:
        lbl.setFixedWidth(w)
    return lbl


def _sep():
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet("color: #cccccc;")
    return f


class GameSettingsScreen(QWidget):
    def __init__(self, state, main_window):
        super().__init__()
        self.setObjectName('WorkspaceGameSettings')
        self.setStyleSheet('#WorkspaceGameSettings { background-color: #f0f0f0; }')
        self.state = state
        self.mw    = main_window
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 20, 30, 20)
        root.setSpacing(18)

        # Top bar
        top = QHBoxLayout()
        back = CooldownButton("← Back")
        back.setStyleSheet(BTN)
        back.clicked.connect(lambda: self.mw.show_screen('menu'))
        top.addWidget(back)
        top.addStretch()
        title = QLabel("Game Settings — Workspace Task")
        title.setFont(QFont('Arial', 22, QFont.Bold))
        title.setStyleSheet("color: #000000;")
        top.addWidget(title)
        top.addStretch()
        root.addLayout(top)

        root.addWidget(_sep())

        # ── Previous Trajectory ──────────────────────────────────────
        row = QHBoxLayout()
        lbl = QLabel("Previous Trajectory")
        lbl.setFont(QFont('Arial', 15))
        lbl.setStyleSheet("color: #000000;")
        lbl.setFixedWidth(220)
        row.addWidget(lbl)
        row.addSpacing(12)
        self.ghost_combo = QComboBox()
        self.ghost_combo.addItem("Individual", userData='individual')
        self.ghost_combo.addItem("Average",    userData='average')
        self.ghost_combo.setFixedWidth(160)
        self.ghost_combo.setStyleSheet(
            "QComboBox { background:#fff; color:#000; border:1px solid #aaa;"
            " border-radius:4px; padding:3px 8px; font-size:14px; }"
            "QComboBox QAbstractItemView { background:#fff; color:#000;"
            " selection-background-color:#b0c8e0; }"
        )
        for i in range(self.ghost_combo.count()):
            if self.ghost_combo.itemData(i) == self.state.ws_ghost_mode:
                self.ghost_combo.setCurrentIndex(i)
                break
        self.ghost_combo.currentIndexChanged.connect(
            lambda i: setattr(self.state, 'ws_ghost_mode', self.ghost_combo.itemData(i)))
        row.addWidget(self.ghost_combo)
        row.addSpacing(16)
        row.addWidget(_label("Individual: up to 5 past envelopes  |  Average: single running average"))
        row.addStretch()
        root.addLayout(row)

        root.addWidget(_sep())

        # ── Speed Gauge ── single row ────────────────────────────────
        row2 = QHBoxLayout()
        self.spd_chk = QCheckBox("Speed Gauge")
        self.spd_chk.setStyleSheet(CHKBOX)
        self.spd_chk.setChecked(self.state.ws_speed_gauge_on)
        self.spd_chk.setFixedWidth(160)
        self.spd_chk.toggled.connect(self._on_spd_toggled)
        row2.addWidget(self.spd_chk)
        row2.addSpacing(20)

        row2.addWidget(_label("Window:"))
        self.spd_win = QSpinBox()
        self.spd_win.setRange(50, 1000)
        self.spd_win.setSingleStep(50)
        self.spd_win.setValue(self.state.ws_speed_window_ms)
        self.spd_win.setFixedWidth(80)
        self.spd_win.setStyleSheet(SPIN)
        self.spd_win.valueChanged.connect(lambda v: setattr(self.state, 'ws_speed_window_ms', v))
        row2.addWidget(self.spd_win)
        row2.addWidget(_label(" ms"))
        row2.addSpacing(16)

        row2.addWidget(_label("R — Min:"))
        self.spd_min_R = QDoubleSpinBox()
        self.spd_min_R.setRange(0.0, 100.0)
        self.spd_min_R.setSingleStep(0.5)
        self.spd_min_R.setDecimals(1)
        self.spd_min_R.setValue(self.state.ws_speed_min_R)
        self.spd_min_R.setFixedWidth(72)
        self.spd_min_R.setStyleSheet(SPIN)
        self.spd_min_R.valueChanged.connect(lambda v: setattr(self.state, 'ws_speed_min_R', v))
        row2.addWidget(self.spd_min_R)
        row2.addSpacing(6)
        row2.addWidget(_label("Max:"))
        self.spd_max_R = QDoubleSpinBox()
        self.spd_max_R.setRange(0.1, 200.0)
        self.spd_max_R.setSingleStep(0.5)
        self.spd_max_R.setDecimals(1)
        self.spd_max_R.setValue(self.state.ws_speed_max_R)
        self.spd_max_R.setFixedWidth(72)
        self.spd_max_R.setStyleSheet(SPIN)
        self.spd_max_R.valueChanged.connect(lambda v: setattr(self.state, 'ws_speed_max_R', v))
        row2.addWidget(self.spd_max_R)
        row2.addWidget(_label(" cm/s"))
        row2.addSpacing(20)

        row2.addWidget(_label("L — Min:"))
        self.spd_min_L = QDoubleSpinBox()
        self.spd_min_L.setRange(0.0, 100.0)
        self.spd_min_L.setSingleStep(0.5)
        self.spd_min_L.setDecimals(1)
        self.spd_min_L.setValue(self.state.ws_speed_min_L)
        self.spd_min_L.setFixedWidth(72)
        self.spd_min_L.setStyleSheet(SPIN)
        self.spd_min_L.valueChanged.connect(lambda v: setattr(self.state, 'ws_speed_min_L', v))
        row2.addWidget(self.spd_min_L)
        row2.addSpacing(6)
        row2.addWidget(_label("Max:"))
        self.spd_max_L = QDoubleSpinBox()
        self.spd_max_L.setRange(0.1, 200.0)
        self.spd_max_L.setSingleStep(0.5)
        self.spd_max_L.setDecimals(1)
        self.spd_max_L.setValue(self.state.ws_speed_max_L)
        self.spd_max_L.setFixedWidth(72)
        self.spd_max_L.setStyleSheet(SPIN)
        self.spd_max_L.valueChanged.connect(lambda v: setattr(self.state, 'ws_speed_max_L', v))
        row2.addWidget(self.spd_max_L)
        row2.addWidget(_label(" cm/s"))
        row2.addStretch()
        root.addLayout(row2)

        root.addWidget(_sep())

        # ── Guide Line ── single row ─────────────────────────────────
        row3 = QHBoxLayout()
        self.guide_chk = QCheckBox("Guide Line")
        self.guide_chk.setStyleSheet(CHKBOX)
        self.guide_chk.setChecked(self.state.ws_guide_line_on)
        self.guide_chk.setFixedWidth(160)
        self.guide_chk.toggled.connect(lambda v: setattr(self.state, 'ws_guide_line_on', v))
        row3.addWidget(self.guide_chk)
        row3.addSpacing(20)

        row3.addWidget(_label("Speed:"))
        self.guide_spd = QDoubleSpinBox()
        self.guide_spd.setRange(1.0, 180.0)
        self.guide_spd.setSingleStep(5.0)
        self.guide_spd.setDecimals(1)
        self.guide_spd.setValue(self.state.ws_guide_speed_degs)
        self.guide_spd.setFixedWidth(80)
        self.guide_spd.setStyleSheet(SPIN)
        self.guide_spd.valueChanged.connect(lambda v: setattr(self.state, 'ws_guide_speed_degs', v))
        row3.addWidget(self.guide_spd)
        row3.addWidget(_label(" °/s"))
        row3.addSpacing(16)
        row3.addWidget(_label("(sweeps 180° from arm side; R: left→right, L: right→left)"))
        row3.addStretch()
        root.addLayout(row3)

        root.addStretch()

    def _on_spd_toggled(self, checked):
        self.state.ws_speed_gauge_on = checked
        for w in (self.spd_win, self.spd_min_R, self.spd_max_R, self.spd_min_L, self.spd_max_L):
            w.setEnabled(checked)
