import csv
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QTableWidget,
                             QTableWidgetItem, QHeaderView, QFileDialog,
                             QMessageBox)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from screens.utils import CooldownButton

STYLE = """
    QWidget       { background-color: #f0f0f0; color: #000000; }
    QTableWidget  { background-color: #ffffff; gridline-color: #cccccc;
                    border: 1px solid #cccccc; font-size: 16px; color: #000000; }
    QHeaderView::section { background-color: #dddddd; color: #000000;
                           padding: 6px; border: none; font-size: 15px; }
    QTableWidget::item:selected { background-color: #b0c8e0; color: #000000; }
    QPushButton   { background-color: #888888; color: white;
                    border: none; border-radius: 6px;
                    padding: 8px 18px; font-size: 15px; }
    QPushButton:hover  { background-color: #999999; }
    QPushButton:pressed{ background-color: #777777; }
"""

COLUMNS    = ['ID', 'Angle (°)', 'Distance (cm)', 'Diameter (cm)']
CSV_FIELDS = ['id', 'angle_deg', 'distance_cm', 'diameter_cm']


def _cell(text):
    item = QTableWidgetItem(str(text))
    item.setTextAlignment(Qt.AlignCenter)
    return item


class TargetScreen(QWidget):
    def __init__(self, state, main_window):
        super().__init__()
        self.state = state
        self.mw    = main_window
        self.setStyleSheet(STYLE)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 20, 30, 20)
        root.setSpacing(14)

        top = QHBoxLayout()
        back = CooldownButton("← Back")
        back.clicked.connect(lambda: self.mw.show_screen('menu'))
        top.addWidget(back)
        title = QLabel("Target Settings")
        title.setFont(QFont('Arial', 24, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #000000; background: transparent;")
        top.addWidget(title, 1)
        top.addWidget(QLabel())
        root.addLayout(top)

        body = QHBoxLayout()
        body.setSpacing(12)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(self.table.styleSheet() +
                                 "QTableWidget { alternate-background-color: #f5f5f5; }")
        body.addWidget(self.table)

        btns = QVBoxLayout()
        btns.setSpacing(8)
        btns.setContentsMargins(0, 0, 0, 0)
        for label, fn in [
            ('Add Row',    self._add_row),
            ('Delete Row', self._delete_row),
            ('All Clear',  self._clear_all),
            ('Save CSV',   self._save_csv),
            ('Load CSV',   self._load_csv),
        ]:
            b = CooldownButton(label)
            b.clicked.connect(fn)
            btns.addWidget(b)
        btns.addStretch()
        body.addLayout(btns)
        root.addLayout(body)

    def _add_row(self):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, _cell(row + 1))
        self.table.setItem(row, 1, _cell('90'))
        self.table.setItem(row, 2, _cell('20'))
        self.table.setItem(row, 3, _cell('5'))
        self.table.scrollToBottom()

    def _clear_all(self):
        self.table.setRowCount(0)

    def _delete_row(self):
        row = self.table.currentRow()
        if row < 0:
            row = self.table.rowCount() - 1
        if row < 0:
            return
        self.table.removeRow(row)
        self._renumber()

    def _renumber(self):
        for i in range(self.table.rowCount()):
            item = self.table.item(i, 0)
            if item:
                item.setText(str(i + 1))
                item.setTextAlignment(Qt.AlignCenter)

    def _save_csv(self):
        if self.table.rowCount() == 0:
            QMessageBox.warning(self, "Empty", "No targets to save.")
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Save Targets CSV', '', 'CSV Files (*.csv)')
        if not path:
            return
        with open(path, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(CSV_FIELDS)
            for r in range(self.table.rowCount()):
                w.writerow([self.table.item(r, c).text() for c in range(4)])

    def _load_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Load Targets CSV', '', 'CSV Files (*.csv)')
        if not path:
            return
        try:
            self.table.setRowCount(0)
            with open(path, 'r') as f:
                for row_data in csv.DictReader(f):
                    r = self.table.rowCount()
                    self.table.insertRow(r)
                    self.table.setItem(r, 0, _cell(row_data.get('id',          str(r+1))))
                    self.table.setItem(r, 1, _cell(row_data.get('angle_deg',   '0')))
                    self.table.setItem(r, 2, _cell(row_data.get('distance_cm', '0')))
                    self.table.setItem(r, 3, _cell(row_data.get('diameter_cm', '5')))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load CSV:\n{e}")
