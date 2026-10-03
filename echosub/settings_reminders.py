# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""The reminders tab: everything set by voice, and everything that has already come round.

A reminder may be added, retimed, reworded or removed here, so nothing set by speaking is stuck
with whatever was understood at the time.
"""
import datetime

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDateTimeEdit, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import reminders

WAITING, DONE = "Waiting", "Done"


class RemindersTabMixin:
    """A table of reminders, where the time is picked and the words are typed."""

    def _reminders_tab(self, cfg):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        group = QGroupBox("Reminders")
        inner = QVBoxLayout(group)
        note = QLabel(
            'Set one by saying "remind me in five minutes to check the oven", or add it here. '
            "The time can be changed with the arrows or by typing over it, and the words by typing. "
            "Finished ones stay in the list until you clear them.")
        note.setWordWrap(True)
        note.setStyleSheet("color: gray;")
        inner.addWidget(note)

        self.reminder_table = QTableWidget(0, 3)
        self.reminder_table.setHorizontalHeaderLabels(("When", "What", "State"))
        self.reminder_table.verticalHeader().setVisible(False)
        self.reminder_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.reminder_table.setMinimumHeight(240)
        header = self.reminder_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        inner.addWidget(self.reminder_table)

        buttons = QHBoxLayout()
        add = QPushButton("Add a reminder")
        add.clicked.connect(lambda: self._add_reminder())
        remove = QPushButton("Remove selected")
        remove.clicked.connect(self._remove_reminder)
        clear = QPushButton("Clear the finished ones")
        clear.clicked.connect(self._clear_finished_reminders)
        buttons.addWidget(add)
        buttons.addWidget(remove)
        buttons.addWidget(clear)
        buttons.addStretch(1)
        inner.addLayout(buttons)
        layout.addWidget(group)
        layout.addStretch(1)

        for entry in reminders.valid(cfg.get("reminders", [])):
            self._add_reminder(entry["when"], entry["what"], entry.get("done"))
        return widget

    def _add_reminder(self, when=None, what="", done=None):
        table = self.reminder_table
        row = table.rowCount()
        table.insertRow(row)

        picker = QDateTimeEdit()
        picker.setDisplayFormat("ddd d MMM yyyy  HH:mm")
        picker.setCalendarPopup(True)
        moment = (datetime.datetime.fromisoformat(when) if when
                  else datetime.datetime.now() + datetime.timedelta(minutes=10))
        picker.setDateTime(QDateTime(moment))
        picker.setEnabled(done is None)  # a reminder already shown is a record, not a plan
        table.setCellWidget(row, 0, picker)

        table.setItem(row, 1, QTableWidgetItem(str(what)))
        state = QTableWidgetItem(DONE if done else WAITING)
        state.setFlags(state.flags() & ~Qt.ItemIsEditable)
        state.setData(Qt.UserRole, done or "")
        if done:
            state.setForeground(Qt.gray)
        table.setItem(row, 2, state)
        table.setCurrentCell(row, 1)
        if when is None:
            table.editItem(table.item(row, 1))

    def _remove_reminder(self):
        for row in sorted({index.row() for index in self.reminder_table.selectedIndexes()}, reverse=True):
            self.reminder_table.removeRow(row)

    def _clear_finished_reminders(self):
        for row in range(self.reminder_table.rowCount() - 1, -1, -1):
            state = self.reminder_table.item(row, 2)
            if state is not None and state.text() == DONE:
                self.reminder_table.removeRow(row)

    def reminder_values(self):
        rows = []
        for row in range(self.reminder_table.rowCount()):
            picker = self.reminder_table.cellWidget(row, 0)
            what = self.reminder_table.item(row, 1)
            state = self.reminder_table.item(row, 2)
            if picker is None:
                continue
            entry = {"when": picker.dateTime().toPython().replace(microsecond=0).isoformat(),
                     "what": what.text() if what else ""}
            done = state.data(Qt.UserRole) if state is not None else ""
            if done:
                entry["done"] = done
            rows.append(entry)
        return {"reminders": reminders.valid(rows)}
