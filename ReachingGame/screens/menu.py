from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QApplication, QMessageBox,
                             QLineEdit, QFileDialog, QComboBox, QSpinBox, QCheckBox)
from PyQt5.QtCore import Qt, QTimer, QPoint, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QFont
from screens.utils import CooldownButton

DARK_BG  = '#14141e'
LIGHT_BG = '#f0f0f0'

BTN_STYLE = """
    QPushButton {
        background-color: #888888; color: white;
        border: none; border-radius: 6px;
        font-size: 18px; padding: 10px;
        min-width: 300px; max-width: 300px;
    }
    QPushButton:hover     { background-color: #999999; }
    QPushButton:pressed   { background-color: #777777; }
    QPushButton:disabled  { background-color: #555555; color: #888888; }
"""


class ToggleSwitch(QWidget):
    toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(64, 30)
        self._on = False
        self.setCursor(Qt.PointingHandCursor)

    def isOn(self): return self._on

    def setOn(self, val):
        self._on = val
        self.update()

    def mousePressEvent(self, e):
        self._on = not self._on
        self.toggled.emit(self._on)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect()
        bg   = QColor(230, 230, 230) if self._on else QColor(20, 20, 20)
        knob = QColor(50,  50,  50)  if self._on else QColor(180, 180, 180)
        p.setBrush(bg)
        p.setPen(QColor(120, 120, 120))
        p.drawRoundedRect(r.adjusted(1,1,-1,-1), r.height()//2, r.height()//2)
        pad = 3
        kr  = r.height()//2 - pad
        kx  = r.right() - pad - kr if self._on else r.left() + pad + kr
        p.setBrush(knob)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPoint(kx, r.height()//2), kr, kr)
        if self._on:
            p.setPen(QColor(60, 60, 60))
            p.setFont(QFont('Arial', 11, QFont.Bold))
            p.drawText(r.adjusted(6, 0, 0, 0), Qt.AlignVCenter, "ON")


class MenuScreen(QWidget):
    def __init__(self, state, liberty, main_window, tasks):
        super().__init__()
        self.setObjectName("MenuScreen")
        self.state   = state
        self.liberty = liberty
        self.mw      = main_window
        # key → task module
        self._tasks  = {t.TASK_KEY: t for t in tasks}
        self._build(tasks)
        self._apply_theme()

        timer = QTimer(self)
        timer.timeout.connect(self._update_status)
        timer.start(500)

    def _current_task(self):
        return self._tasks.get(self.state.task_type)

    def _build(self, tasks):
        root = QVBoxLayout(self)
        root.setAlignment(Qt.AlignCenter)

        # Title row — mirror label on left keeps title truly centered
        root.addSpacing(40)
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        _mirror = QLabel("DUMMY MODE")
        _mirror.setFont(QFont('Arial', 16, QFont.Bold))
        _mirror.setStyleSheet("color: transparent;")
        title_row.addSpacing(14)
        title_row.addWidget(_mirror, 0, Qt.AlignBottom)
        title_row.addStretch()
        self.title_lbl = QLabel("ReachLab")
        self.title_lbl.setAlignment(Qt.AlignCenter)
        self.title_lbl.setFont(QFont('Arial', 54, QFont.Bold))
        self.title_lbl.setStyleSheet("color: #000000;")
        title_row.addWidget(self.title_lbl)
        title_row.addStretch()
        self.dummy_lbl = QLabel("DUMMY MODE")
        self.dummy_lbl.setFont(QFont('Arial', 16, QFont.Bold))
        title_row.addWidget(self.dummy_lbl, 0, Qt.AlignBottom)
        title_row.addSpacing(14)
        root.addLayout(title_row)

        # Status row
        root.addSpacing(6)
        status_row = QHBoxLayout()
        status_row.addStretch()
        self.status_lbl = QLabel()
        self.status_lbl.setFont(QFont('Arial', 17))
        status_row.addWidget(self.status_lbl)
        status_row.addSpacing(16)
        self.sensor_lbls = {}
        for n in range(1, 5):
            lbl = QLabel(f"S{n}")
            lbl.setFont(QFont('Arial', 13, QFont.Bold))
            lbl.setStyleSheet("color: #dc3232;")
            status_row.addWidget(lbl)
            status_row.addSpacing(4)
            self.sensor_lbls[n] = lbl
        status_row.addStretch()
        root.addLayout(status_row)

        self.game_status_lbl = QLabel("●  GAME IN PROGRESS")
        self.game_status_lbl.setAlignment(Qt.AlignCenter)
        self.game_status_lbl.setFont(QFont('Arial', 17, QFont.Bold))
        self.game_status_lbl.setStyleSheet("color: #32dc50;")
        self.game_status_lbl.setVisible(False)
        root.addWidget(self.game_status_lbl)
        root.addSpacing(10)

        # Task dropdown — built from tasks list
        task_row = QHBoxLayout()
        task_row.setContentsMargins(0, 0, 0, 0)
        task_row.addStretch()
        self.task_combo = QComboBox()
        for task in tasks:
            self.task_combo.addItem(task.TASK_LABEL, userData=task.TASK_KEY)
        self.task_combo.setFixedWidth(200)
        self.task_combo.setStyleSheet(
            "QComboBox { background: #ffffff; color: #000000; border: 1px solid #aaaaaa;"
            " border-radius: 4px; padding: 3px 8px; font-size: 15px; }"
            "QComboBox::drop-down { border: none; }"
            "QComboBox QAbstractItemView { background: #ffffff; color: #000000;"
            " selection-background-color: #b0c8e0; }"
        )
        self.task_combo.currentIndexChanged.connect(self._on_task_changed)
        # Sync combo to persisted task_type without re-triggering the slot
        for i in range(self.task_combo.count()):
            if self.task_combo.itemData(i) == self.state.task_type:
                self.task_combo.blockSignals(True)
                self.task_combo.setCurrentIndex(i)
                self.task_combo.blockSignals(False)
                break
        task_row.addWidget(self.task_combo)
        task_row.addStretch()
        root.addLayout(task_row, 0)
        root.addSpacing(6)

        # Data folder selector
        folder_wrap = QHBoxLayout()
        folder_wrap.setContentsMargins(0, 0, 0, 0)
        folder_wrap.setSpacing(0)
        folder_wrap.addStretch()

        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("Select a folder to save data")
        self.folder_edit.setReadOnly(True)
        self.folder_edit.setFixedWidth(260)
        self.folder_edit.setStyleSheet(
            "QLineEdit { background: #ffffff; color: #000000; border: 1px solid #aaaaaa;"
            " border-top-left-radius: 4px; border-bottom-left-radius: 4px;"
            " border-right: none; padding: 3px 8px; font-size: 14px; }"
        )
        folder_wrap.addWidget(self.folder_edit)

        self.browse_btn = CooldownButton("Browse")
        browse_btn = self.browse_btn
        browse_btn.setStyleSheet(
            "QPushButton { background-color: #888888; color: white; border: none;"
            " border-top-right-radius: 4px; border-bottom-right-radius: 4px;"
            " font-size: 13px;"
            " min-width: 58px; max-width: 58px;"
            " min-height: 28px; max-height: 28px; padding: 0px; }"
            "QPushButton:hover  { background-color: #999999; }"
            "QPushButton:pressed{ background-color: #777777; }"
        )
        browse_btn.clicked.connect(self._browse_folder)
        folder_wrap.addWidget(browse_btn)
        folder_wrap.addStretch()
        root.addLayout(folder_wrap, 0)
        root.addSpacing(6)

        # Sample rate
        rate_row = QHBoxLayout()
        rate_row.setContentsMargins(0, 0, 0, 0)
        rate_row.addStretch()
        rate_lbl = QLabel("Sample Rate")
        rate_lbl.setStyleSheet("color: #000000; font-size: 14px;")
        rate_row.addWidget(rate_lbl)
        rate_row.addSpacing(6)
        self.rate_spin = QSpinBox()
        self.rate_spin.setRange(10, 500)
        self.rate_spin.setValue(self.state.sample_rate_hz)
        self.rate_spin.setSuffix(" Hz")
        self.rate_spin.setFixedWidth(80)
        self.rate_spin.setReadOnly(True)
        self.rate_spin.setStyleSheet(
            "QSpinBox { background: #e8e8e8; color: #444444; border: 1px solid #aaaaaa;"
            " border-radius: 4px; padding: 2px 6px; font-size: 14px; }"
            "QSpinBox::up-button { width: 0; }"
            "QSpinBox::down-button { width: 0; }"
        )
        rate_row.addWidget(self.rate_spin)
        rate_row.addSpacing(16)
        self.liberty_rate_lbl = QLabel("Liberty: — Hz")
        self.liberty_rate_lbl.setStyleSheet("color: #666666; font-size: 14px;")
        rate_row.addWidget(self.liberty_rate_lbl)
        rate_row.addStretch()
        root.addLayout(rate_row, 0)
        root.addSpacing(16)

        # Buttons
        items = [
            ('Start',        'start'),
            ('Environment',  'environment'),
            ('Calibration',  'calibration'),
            ('Digitization', 'digitization'),
            ('Game',         'game'),
            ('Targets',      'targets'),
            ('Sessions',     'sessions'),
            ('Quit',         'quit'),
        ]
        self.btns = {}
        for label, key in items:
            btn = CooldownButton(label)
            btn.setStyleSheet(BTN_STYLE)
            btn.clicked.connect(lambda _, k=key: self._on_btn(k))
            root.addWidget(btn, 0, Qt.AlignCenter)
            root.addSpacing(4)
            self.btns[key] = btn
            if key == 'start':
                self._build_start_from_row(root)
                root.addSpacing(4)

        root.addStretch()

        # Bottom row: all right-aligned
        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 0, 20, 12)
        bottom_row.addStretch()

        self.mouse_row_widget = QWidget()
        self.mouse_row_widget.setStyleSheet("background: transparent;")
        mouse_inner = QHBoxLayout(self.mouse_row_widget)
        mouse_inner.setContentsMargins(0, 0, 0, 0)
        mouse_inner.setSpacing(8)
        self.mouse_lbl = QLabel("Mouse")
        self.mouse_lbl.setFont(QFont('Arial', 14))
        self.mouse_lbl.setStyleSheet("color: #ffffff;")
        mouse_inner.addWidget(self.mouse_lbl)
        self.mouse_toggle = ToggleSwitch()
        self.mouse_toggle.setOn(False)
        self.mouse_toggle.toggled.connect(self._on_mouse_toggle)
        mouse_inner.addWidget(self.mouse_toggle)
        bottom_row.addWidget(self.mouse_row_widget)
        self.mouse_row_widget.setVisible(self.liberty.dummy)

        bottom_row.addSpacing(20)

        lbl = QLabel("Dummy Mode")
        lbl.setFont(QFont('Arial', 14))
        lbl.setStyleSheet("color: #ffffff;")
        self.toggle_label = lbl
        bottom_row.addWidget(lbl)
        bottom_row.addSpacing(8)
        self.toggle = ToggleSwitch()
        self.toggle.setOn(self.liberty.dummy)
        self.toggle.toggled.connect(self._on_toggle)
        bottom_row.addWidget(self.toggle)

        root.addLayout(bottom_row)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            for win in self.mw.game_windows.values():
                if win.isVisible():
                    win.hide()
                    return
        super().keyPressEvent(e)

    def _on_task_changed(self, index):
        key = self.task_combo.itemData(index)
        self.state.task_type = key
        # reset env_rect to None, then load only task-specific saved values (no cross-task fallback)
        for attr in ('env_rect_x', 'env_rect_y', 'env_rect_w', 'env_rect_h'):
            setattr(self.state, attr, None)
        self.state.load_task_rect(key, fallback=False)
        # turn off dummy mode so the new task starts clean
        if self.toggle.isOn():
            self.toggle.setOn(False)
            self._on_toggle(False)
        self._update_status()

    def _browse_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Select Data Folder", self.state.data_dir or "")
        if path:
            self.state.data_dir = path
            self.folder_edit.setText(path)

    def _get_session_trial_count(self, task):
        if task is None:
            return None
        sessions_screen = getattr(task, 'SESSIONS_SCREEN', None)
        if sessions_screen is None:
            return None
        scr = self.mw.screens.get(sessions_screen)
        if scr is None:
            return None
        return scr.table.rowCount() or None

    def _build_start_from_row(self, layout):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addStretch()
        self.start_from_chk = QCheckBox("Start from trial")
        self.start_from_chk.setStyleSheet(
            "QCheckBox { color: #000000; font-size: 13px; spacing: 6px; }"
            "QCheckBox::indicator { width: 14px; height: 14px; }"
        )
        self.start_from_chk.setChecked(False)
        row.addWidget(self.start_from_chk)
        self.start_from_edit = QLineEdit()
        self.start_from_edit.setPlaceholderText("trial #")
        self.start_from_edit.setFixedWidth(64)
        self.start_from_edit.setEnabled(False)
        self.start_from_edit.setStyleSheet(
            "QLineEdit { background: #ffffff; color: #000000; border: 1px solid #aaaaaa;"
            " border-radius: 4px; padding: 2px 6px; font-size: 13px; }"
            "QLineEdit:disabled { background: #555555; color: #888888; }"
        )
        self.start_from_chk.toggled.connect(self.start_from_edit.setEnabled)
        row.addWidget(self.start_from_edit)
        row.addStretch()
        layout.addLayout(row, 0)

    def _on_btn(self, key):
        task = self._current_task()

        if key == 'quit':
            QApplication.quit()

        elif key == 'start':
            if not self.state.data_dir:
                QMessageBox.warning(self, "No Folder Selected",
                                    "Please select a data folder before starting.")
                return
            if self.start_from_chk.isChecked():
                text = self.start_from_edit.text().strip()
                if not text:
                    QMessageBox.warning(self, "Empty Trial Number",
                                        "Please enter a trial number, or uncheck 'Start from trial'.")
                    return
                try:
                    trial_num = int(text)
                except ValueError:
                    QMessageBox.warning(self, "Invalid Input", "Trial number must be an integer.")
                    return
                total = self._get_session_trial_count(task)
                if total is not None and (trial_num < 1 or trial_num > total):
                    QMessageBox.warning(self, "Trial Not Found",
                                        f"Trial {trial_num} is not defined in the current session "
                                        f"(session has {total} trials).")
                    return
                self.state.start_trial = trial_num
            else:
                self.state.start_trial = 1
            if task:
                self.mw.show_screen(task.GAME_SCREEN)

        elif key == 'game':
            if task and getattr(task, 'HAS_GAME_SETTINGS', False):
                self.mw.show_screen(task.GAME_SETTINGS_SCREEN)

        elif key == 'environment':
            self.mw.show_screen('environment')

        elif key == 'calibration':
            self.mw.show_screen('calibration')

        elif key == 'digitization':
            if not self.state.data_dir:
                QMessageBox.warning(self, "No Folder Selected",
                                    "Please select a data folder before accessing Digitization.")
                return
            self.mw.show_screen('digitization')

        elif key == 'targets':
            if task:
                self.mw.show_screen(task.TARGETS_SCREEN)

        elif key == 'sessions':
            if task:
                if getattr(task, 'HAS_TARGETS', True):
                    target_screen = self.mw.screens.get(getattr(task, 'TARGETS_SCREEN', ''))
                    if target_screen is None or target_screen.table.rowCount() == 0:
                        QMessageBox.warning(
                            self, "No Targets",
                            "Please configure at least one target in the Targets screen first."
                        )
                        return
                self.mw.show_screen(task.SESSIONS_SCREEN)

    def _on_toggle(self, on):
        self.liberty.dummy = on
        if on:
            self.liberty.use_mouse = self.mouse_toggle.isOn()
            if hasattr(self.mw, '_setup_dummy_defaults'):
                self.mw._setup_dummy_defaults()
        else:
            self.liberty.use_mouse = False
            self.mouse_toggle.setOn(False)
            if hasattr(self.mw, '_clear_dummy_defaults'):
                self.mw._clear_dummy_defaults()
        self.mouse_row_widget.setVisible(on)
        self._apply_theme()
        self._update_status()

    def _on_mouse_toggle(self, on):
        self.liberty.use_mouse = on

    def _apply_theme(self):
        dark = self.liberty.dummy
        bg   = DARK_BG if dark else LIGHT_BG
        self.setStyleSheet(f"#MenuScreen {{ background-color: {bg}; }}")
        dummy_color = '#c8a000' if dark else 'transparent'
        self.dummy_lbl.setStyleSheet(f"color: {dummy_color};")

    def _set_locked(self, locked):
        task = self._current_task()
        has_targets       = getattr(task, 'HAS_TARGETS',       True)  if task else True
        has_game_settings = getattr(task, 'HAS_GAME_SETTINGS', False) if task else False
        self.task_combo.setEnabled(not locked)
        self.browse_btn.setEnabled(not locked)
        self.rate_spin.setEnabled(not locked)
        self.toggle.setEnabled(not locked)
        self.mouse_toggle.setEnabled(not locked)
        for key, btn in self.btns.items():
            if btn is not None:
                if key == 'targets' and not has_targets:
                    btn.setEnabled(False)
                elif key == 'game' and not has_game_settings:
                    btn.setEnabled(False)
                else:
                    btn.setEnabled(not locked)

    def _update_status(self):
        game_running = any(w.isVisible() for w in self.mw.game_windows.values())
        self._set_locked(game_running)
        self.game_status_lbl.setVisible(game_running)

        if self.liberty.is_running():
            color, text = '#32dc50', '●  Liberty: RUNNING'
        elif self.liberty.is_connected():
            color, text = '#e08000', '●  Liberty: CONNECTED'
        else:
            color, text = '#dc3232', '●  Liberty: DISCONNECTED'
        if self.liberty.use_mouse:
            text += '  |  Mouse'
        self.status_lbl.setText(text)
        self.status_lbl.setStyleSheet(f"color: {color};")
        for n, lbl in self.sensor_lbls.items():
            active = self.liberty.is_sensor_active(n)
            lbl.setStyleSheet(f"color: {'#32dc50' if active else '#dc3232'};")

        rate = self.liberty.get_read_rate()
        if rate > 0:
            self.liberty_rate_lbl.setText(f"Liberty: {rate:.0f} Hz")
        else:
            self.liberty_rate_lbl.setText("Liberty: — Hz")
