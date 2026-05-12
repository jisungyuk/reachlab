from PyQt5.QtWidgets import QPushButton
from PyQt5.QtCore import QTimer


class CooldownButton(QPushButton):
    """QPushButton that ignores repeated clicks for 400 ms after each press."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self.setEnabled(True))
        self.clicked.connect(self._start_cooldown)

    def _start_cooldown(self):
        self.setEnabled(False)
        self._timer.start(200)
