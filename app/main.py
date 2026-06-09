import sys
import os

if sys.platform != 'win32':
    os.environ.setdefault('QT_QPA_PLATFORM', 'wayland')

from PyQt5.QtWidgets import QApplication, QMainWindow, QStackedWidget, QTableWidgetItem

from app_state import AppState
from liberty_reader import LibertyReader
from screens.menu import MenuScreen
from screens.environment import EnvironmentScreen
from screens.calibration import CalibrationScreen
from screens.digitization import DigitizationScreen

import tasks.reaching_task  as reaching_task
import tasks.workspace_task as workspace_task

TASKS = [reaching_task, workspace_task]

DUMMY_DATA_DIR = os.path.join(os.path.expanduser('~'), 'Desktop', 'Liberty', 'test')


class GameWindow(QMainWindow):
    def __init__(self, widget):
        super().__init__()
        self.setStyleSheet("background-color: #000000;")
        self.setCentralWidget(widget)

    def show_on_external(self):
        screens = QApplication.screens()
        target = screens[1] if len(screens) > 1 else screens[0]
        self.setGeometry(target.geometry())
        self.showFullScreen()
        self.activateWindow()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ReachLab")
        self.setFixedSize(1600, 900)

        self.state   = AppState()
        self.state.load_config()
        self.liberty = LibertyReader(dummy=False)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.screens      = {}
        self.game_windows = {}
        self._add('menu', MenuScreen(self.state, self.liberty, self, TASKS))
        self._add('environment',   EnvironmentScreen(self.state, self.liberty, self))
        self._add('calibration',   CalibrationScreen(self.state, self.liberty, self))
        self._add('digitization',  DigitizationScreen(self.state, self.liberty, self))

        for task in TASKS:
            for name, widget in task.build_screens(self, self.state).items():
                if name == task.GAME_SCREEN:
                    gw = GameWindow(widget)
                    self.game_windows[name] = gw
                    self.screens[name] = widget
                else:
                    self._add(name, widget)

        if self.liberty.dummy:
            self._setup_dummy_defaults()

        self.show_screen('menu')

    def _setup_dummy_defaults(self):
        os.makedirs(DUMMY_DATA_DIR, exist_ok=True)
        self.state.data_dir = DUMMY_DATA_DIR
        self.screens['menu'].folder_edit.setText(DUMMY_DATA_DIR)

        # 3 targets: 45°, 90°, 135° — distance=20, diameter=5
        t = self.screens[reaching_task.TARGETS_SCREEN].table
        t.setRowCount(0)
        for row, (tid, ang) in enumerate([('1', '45'), ('2', '90'), ('3', '135')]):
            t.insertRow(row)
            for col, val in enumerate([tid, ang, '20', '5']):
                item = QTableWidgetItem(val)
                item.setTextAlignment(0x0004 | 0x0080)
                t.setItem(row, col, item)

        # 10 trials cycling through target IDs 1→2→3
        s = self.screens[reaching_task.SESSIONS_SCREEN].table
        s.setRowCount(0)
        target_cycle = ['1', '2', '3', '1', '2', '3', '1', '2', '3', '1']
        for i in range(10):
            s.insertRow(i)
            for col, val in enumerate([str(i + 1), '1', target_cycle[i], '0.5', '2.0', '3.0', '1']):
                item = QTableWidgetItem(val)
                item.setTextAlignment(0x0004 | 0x0080)
                s.setItem(i, col, item)

        # Workspace: 3 trials R (target arm) + 3 trials L (testing arm)
        ws = self.screens[workspace_task.SESSIONS_SCREEN].table
        ws.setRowCount(0)
        for i, arm in enumerate(['R'] * 10 + ['L'] * 10):
            ws.insertRow(i)
            for col, val in enumerate([str(i + 1), arm, '3', '1', '0']):
                item = QTableWidgetItem(val)
                item.setTextAlignment(0x0004 | 0x0080)
                ws.setItem(i, col, item)

    def _clear_dummy_defaults(self):
        self.state.data_dir = ''
        self.screens['menu'].folder_edit.setText('')
        self.screens[reaching_task.TARGETS_SCREEN].table.setRowCount(0)
        self.screens[reaching_task.SESSIONS_SCREEN].table.setRowCount(0)
        self.screens[workspace_task.SESSIONS_SCREEN].table.setRowCount(0)

    def _add(self, name, widget):
        self.screens[name] = widget
        self.stack.addWidget(widget)

    def show_screen(self, name):
        game_screen_names = {t.GAME_SCREEN for t in TASKS}

        for win in self.game_windows.values():
            win.hide()

        if name in game_screen_names and name in self.game_windows:
            self.game_windows[name].show_on_external()
            self.screens[name].setFocus()
        elif name in self.screens:
            self.show()
            self.activateWindow()
            self.stack.setCurrentWidget(self.screens[name])
            self.screens[name].setFocus()


_UDEV_RULE_PATH = '/etc/udev/rules.d/99-polhemus.rules'
_UDEV_RULE      = ('SUBSYSTEM=="usb", ATTRS{idVendor}=="0f44", '
                   'ATTRS{idProduct}=="ff12", MODE="0666"')


def _ensure_usb_permissions():
    import subprocess
    from PyQt5.QtWidgets import QMessageBox

    if os.path.exists(_UDEV_RULE_PATH):
        return

    reply = QMessageBox.question(
        None,
        "USB Permission Setup",
        "The Polhemus Liberty USB device needs a one-time permission setup.\n\n"
        "Click Yes to install automatically (requires admin password).",
        QMessageBox.Yes | QMessageBox.No,
    )

    if reply == QMessageBox.Yes:
        script = (f"echo '{_UDEV_RULE}' > {_UDEV_RULE_PATH} && "
                  "udevadm control --reload-rules && udevadm trigger")
        try:
            result = subprocess.run(['pkexec', 'bash', '-c', script], timeout=30)
            installed = result.returncode == 0
        except Exception:
            installed = False

        if installed:
            QMessageBox.information(
                None, "Done",
                "Permission installed.\n\n"
                "Please unplug and replug the Liberty device, then click OK.",
            )
        else:
            _show_usb_instructions()
    else:
        _show_usb_instructions()


def _show_usb_instructions():
    from PyQt5.QtWidgets import QMessageBox
    QMessageBox.information(
        None, "Manual Setup Required",
        "Run these commands once in a terminal, then replug the Liberty device:\n\n"
        f"echo '{_UDEV_RULE}' | sudo tee {_UDEV_RULE_PATH}\n"
        "sudo udevadm control --reload-rules\n"
        "sudo udevadm trigger",
    )


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    if sys.platform == 'linux':
        _ensure_usb_permissions()

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
    

    