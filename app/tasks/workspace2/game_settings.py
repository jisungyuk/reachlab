import os
import csv
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QDoubleSpinBox, QCheckBox, QFrame,
                             QTableWidget, QTableWidgetItem, QHeaderView,
                             QSizePolicy)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor
from screens.utils import CooldownButton

_CSV_HEADERS = [
    'date', 'time', 'hand', 'sweep_speed',
    'max_dist', 'dist_contra', 'dist_ipsi',
    'angle_range', 'angle_contra', 'angle_ipsi',
    'area_total', 'area_contra', 'area_ipsi',
]
_COL_LABELS = [
    'Date', 'Time', 'Hand', 'Speed (°/s)',
    'Max Dist (cm)', 'Dist Contra', 'Dist Ipsi',
    'Angle Range (°)', 'Angle Contra', 'Angle Ipsi',
    'Area (cm²)', 'Area Contra', 'Area Ipsi',
]


class GameSettingsScreen(QWidget):
    def __init__(self, state, main_window):
        super().__init__()
        self.setObjectName('WS2GameSettings')
        self.setStyleSheet('#WS2GameSettings { background-color: #f0f0f0; }')
        self.state = state
        self.mw    = main_window
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 20, 30, 20)
        root.setSpacing(16)

        # Title row
        top = QHBoxLayout()
        back = CooldownButton("← Back")
        back.clicked.connect(lambda: self.mw.show_screen('menu'))
        top.addWidget(back)
        top.addStretch()
        title = QLabel("Game Settings — Workspace Task 2")
        title.setFont(QFont('Arial', 22, QFont.Bold))
        title.setStyleSheet("color: #000000;")
        top.addWidget(title)
        top.addStretch()
        root.addLayout(top)

        root.addWidget(self._divider())

        # ── Sweep speed ───────────────────────────────────────
        root.addWidget(self._section_label("Sweep"))

        speed_row = QHBoxLayout()
        speed_row.setSpacing(12)

        lbl = QLabel("Speed:")
        lbl.setFont(QFont('Arial', 16))
        lbl.setStyleSheet("color: #222222;")
        speed_row.addWidget(lbl)

        self._speed_spin = QDoubleSpinBox()
        self._speed_spin.setRange(0.2, 10.0)
        self._speed_spin.setSingleStep(0.1)
        self._speed_spin.setDecimals(1)
        self._speed_spin.setSuffix(" °/s")
        self._speed_spin.setFont(QFont('Arial', 15))
        self._speed_spin.setFixedWidth(120)
        self._speed_spin.setValue(self.state.ws2_sweep_speed)
        self._speed_spin.valueChanged.connect(self._on_speed_changed)
        speed_row.addWidget(self._speed_spin)

        self._duration_lbl = QLabel()
        self._duration_lbl.setFont(QFont('Arial', 14))
        self._duration_lbl.setStyleSheet("color: #555555;")
        speed_row.addWidget(self._duration_lbl)
        speed_row.addStretch()
        root.addLayout(speed_row)
        self._update_duration_label(self.state.ws2_sweep_speed)

        # Dot offset row
        offset_row = QHBoxLayout()
        offset_row.setSpacing(12)
        offset_lbl = QLabel("Red dot offset:")
        offset_lbl.setFont(QFont('Arial', 16))
        offset_lbl.setStyleSheet("color: #222222;")
        offset_row.addWidget(offset_lbl)

        self._offset_spin = QDoubleSpinBox()
        self._offset_spin.setRange(1.0, 30.0)
        self._offset_spin.setSingleStep(0.5)
        self._offset_spin.setDecimals(1)
        self._offset_spin.setSuffix(" cm")
        self._offset_spin.setFont(QFont('Arial', 15))
        self._offset_spin.setFixedWidth(110)
        self._offset_spin.setValue(self.state.ws2_dot_offset)
        self._offset_spin.valueChanged.connect(self._on_offset_changed)
        offset_row.addWidget(self._offset_spin)

        offset_hint = QLabel("beyond max reach distance")
        offset_hint.setFont(QFont('Arial', 14))
        offset_hint.setStyleSheet("color: #555555;")
        offset_row.addWidget(offset_hint)
        offset_row.addStretch()
        root.addLayout(offset_row)

        root.addWidget(self._divider())

        # ── Result display ────────────────────────────────────
        root.addWidget(self._section_label("Result"))

        split_row = QHBoxLayout()
        split_row.setSpacing(12)
        self._split_chk = QCheckBox("Show contralateral / ipsilateral breakdown")
        self._split_chk.setFont(QFont('Arial', 15))
        self._split_chk.setStyleSheet("color: #222222;")
        self._split_chk.setChecked(self.state.ws2_show_split_stats)
        self._split_chk.toggled.connect(self._on_split_toggled)
        split_row.addWidget(self._split_chk)
        split_row.addStretch()
        root.addLayout(split_row)

        root.addWidget(self._divider())

        # ── Previous results ──────────────────────────────────
        root.addWidget(self._section_label("Previous Results"))

        self._table = QTableWidget(0, len(_COL_LABELS))
        self._table.setHorizontalHeaderLabels(_COL_LABELS)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet("""
            QTableWidget { background: #ffffff; font-size: 13px; }
            QHeaderView::section { background: #dddddd; font-weight: bold; padding: 4px; }
            QTableWidget::item:alternate { background: #f5f5f5; }
        """)
        self._table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root.addWidget(self._table)

    def showEvent(self, e):
        self._speed_spin.blockSignals(True)
        self._speed_spin.setValue(self.state.ws2_sweep_speed)
        self._speed_spin.blockSignals(False)
        self._update_duration_label(self.state.ws2_sweep_speed)

        self._offset_spin.blockSignals(True)
        self._offset_spin.setValue(self.state.ws2_dot_offset)
        self._offset_spin.blockSignals(False)

        self._split_chk.blockSignals(True)
        self._split_chk.setChecked(self.state.ws2_show_split_stats)
        self._split_chk.blockSignals(False)

        self._load_results()
        super().showEvent(e)

    def _on_speed_changed(self, value):
        self.state.ws2_sweep_speed = value
        self.state.save_config()
        self._update_duration_label(value)

    def _on_offset_changed(self, value):
        self.state.ws2_dot_offset = value
        self.state.save_config()

    def _on_split_toggled(self, checked):
        self.state.ws2_show_split_stats = checked
        self.state.save_config()

    def _update_duration_label(self, speed):
        secs = 90.0 / max(speed, 0.01)
        text = (f"(90° sweep ≈ {secs / 60:.1f} min)" if secs >= 60
                else f"(90° sweep ≈ {secs:.0f} s)")
        self._duration_lbl.setText(text)

    def _load_results(self):
        self._table.setRowCount(0)
        path = self._csv_path()
        if not path or not os.path.exists(path):
            return
        try:
            with open(path, newline='') as f:
                rows = list(csv.DictReader(f))
        except Exception:
            return

        for row in reversed(rows):  # newest first
            r = self._table.rowCount()
            self._table.insertRow(r)
            for c, key in enumerate(_CSV_HEADERS):
                val = row.get(key, '')
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignCenter)
                if key == 'hand':
                    item.setForeground(
                        QColor('#1a6fc4') if val == 'right' else QColor('#c45a1a'))
                self._table.setItem(r, c, item)

    def _csv_path(self):
        pid  = self.state.participant_id or 'unknown'
        base = self.state.data_dir if self.state.data_dir else os.path.expanduser('~')
        return os.path.join(base, pid, 'ws2_results.csv')

    def _section_label(self, text):
        lbl = QLabel(text)
        lbl.setFont(QFont('Arial', 13, QFont.Bold))
        lbl.setStyleSheet("color: #888888;")
        return lbl

    def _divider(self):
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #cccccc;")
        return line
