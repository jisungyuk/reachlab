from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QComboBox, QFrame, QCheckBox,
                             QDoubleSpinBox)
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

        # ── Guide Line ── single row ─────────────────────────────────
        row3 = QHBoxLayout()
        self.guide_chk = QCheckBox("Guide Line")
        self.guide_chk.setStyleSheet(CHKBOX)
        self.guide_chk.setChecked(self.state.ws_guide_line_on)
        self.guide_chk.setFixedWidth(160)
        self.guide_chk.toggled.connect(lambda v: setattr(self.state, 'ws_guide_line_on', v))
        row3.addWidget(self.guide_chk)
        row3.addSpacing(20)

        row3.addWidget(_label("R Speed:"))
        self.guide_spd_R = QDoubleSpinBox()
        self.guide_spd_R.setRange(1.0, 180.0)
        self.guide_spd_R.setSingleStep(5.0)
        self.guide_spd_R.setDecimals(1)
        self.guide_spd_R.setValue(self.state.ws_guide_speed_R)
        self.guide_spd_R.setFixedWidth(80)
        self.guide_spd_R.setStyleSheet(SPIN)
        self.guide_spd_R.valueChanged.connect(lambda v: setattr(self.state, 'ws_guide_speed_R', v))
        row3.addWidget(self.guide_spd_R)
        row3.addWidget(_label(" °/s"))
        row3.addSpacing(20)

        row3.addWidget(_label("L Speed:"))
        self.guide_spd_L = QDoubleSpinBox()
        self.guide_spd_L.setRange(1.0, 180.0)
        self.guide_spd_L.setSingleStep(5.0)
        self.guide_spd_L.setDecimals(1)
        self.guide_spd_L.setValue(self.state.ws_guide_speed_L)
        self.guide_spd_L.setFixedWidth(80)
        self.guide_spd_L.setStyleSheet(SPIN)
        self.guide_spd_L.valueChanged.connect(lambda v: setattr(self.state, 'ws_guide_speed_L', v))
        row3.addWidget(self.guide_spd_L)
        row3.addWidget(_label(" °/s"))
        row3.addSpacing(16)
        row3.addWidget(_label("(R: left→right, L: right→left, sweeps 180°)"))
        row3.addStretch()
        root.addLayout(row3)

        root.addStretch()

