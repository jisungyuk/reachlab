import csv
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QTableWidget, QTableWidgetItem,
                             QHeaderView, QFileDialog, QMessageBox, QSpinBox)
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

COLUMNS    = ['#', 'Arm', 'Display (s)', 'Draw']
CSV_FIELDS = ['trial', 'arm', 'display_s', 'draw']
NUM_COLS   = len(COLUMNS)
DEFAULTS   = ['1', 'R', '3', '1']


def _cell(text):
    item = QTableWidgetItem(str(text))
    item.setTextAlignment(Qt.AlignCenter)
    return item


class SessionScreen(QWidget):
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
        title = QLabel("Session Settings — Workspace Task")
        title.setFont(QFont('Arial', 24, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #000000; background: transparent;")
        top.addWidget(title, 1)
        top.addWidget(QLabel())
        root.addLayout(top)

        body = QHBoxLayout()
        body.setSpacing(12)

        self.table = QTableWidget(0, NUM_COLS)
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
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
            ('Duplicate',  self._duplicate_row),
        ]:
            b = CooldownButton(label)
            b.clicked.connect(fn)
            btns.addWidget(b)

        self.dup_count = QSpinBox()
        self.dup_count.setRange(1, 99)
        self.dup_count.setValue(1)
        self.dup_count.setAlignment(Qt.AlignCenter)
        self.dup_count.setStyleSheet(
            "QSpinBox { background: white; color: black; border: 1px solid #aaa;"
            " border-radius: 4px; padding: 4px; font-size: 15px; }"
        )
        btns.addWidget(self.dup_count)

        for label, fn in [
            ('All Clear', self._clear_all),
            ('Save CSV',  self._save_csv),
            ('Load CSV',  self._load_csv),
        ]:
            b = CooldownButton(label)
            b.clicked.connect(fn)
            btns.addWidget(b)
        btns.addStretch()
        body.addLayout(btns)
        root.addLayout(body)

    def _add_row(self, values=None):
        row = self.table.rowCount()
        self.table.insertRow(row)
        vals = list(values) if values else DEFAULTS[:]
        vals[0] = str(row + 1)
        for c, v in enumerate(vals):
            self.table.setItem(row, c, _cell(v))
        self.table.scrollToBottom()

    def _selected_rows(self):
        rows = sorted(set(idx.row() for idx in self.table.selectedIndexes()))
        if not rows:
            last = self.table.rowCount() - 1
            if last >= 0:
                rows = [last]
        return rows

    def _delete_row(self):
        rows = self._selected_rows()
        if not rows:
            return
        for row in sorted(rows, reverse=True):
            self.table.removeRow(row)
        self._renumber()

    def _duplicate_row(self):
        rows = self._selected_rows()
        if not rows:
            return
        count = self.dup_count.value()
        for _ in range(count):
            for row in rows:
                vals = [self.table.item(row, c).text() for c in range(NUM_COLS)]
                self._add_row(values=vals)

    def _clear_all(self):
        self.table.setRowCount(0)

    def _renumber(self):
        for i in range(self.table.rowCount()):
            item = self.table.item(i, 0)
            if item:
                item.setText(str(i + 1))
                item.setTextAlignment(Qt.AlignCenter)

    def _save_csv(self):
        if self.table.rowCount() == 0:
            QMessageBox.warning(self, "Empty", "No trials to save.")
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Save Session CSV', '', 'CSV Files (*.csv)')
        if not path:
            return
        with open(path, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(CSV_FIELDS)
            for r in range(self.table.rowCount()):
                w.writerow([self.table.item(r, c).text() for c in range(NUM_COLS)])

    def _load_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Load Session CSV', '', 'CSV Files (*.csv)')
        if not path:
            return
        try:
            self.table.setRowCount(0)
            with open(path, 'r') as f:
                for row_data in csv.DictReader(f):
                    r = self.table.rowCount()
                    self.table.insertRow(r)
                    self.table.setItem(r, 0, _cell(row_data.get('trial',     str(r + 1))))
                    self.table.setItem(r, 1, _cell(row_data.get('arm',       'R')))
                    self.table.setItem(r, 2, _cell(row_data.get('display_s', '3')))
                    self.table.setItem(r, 3, _cell(row_data.get('draw',      '1')))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load CSV:\n{e}")
