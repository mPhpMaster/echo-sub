# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""What EchoSub heard after the wake word but did not understand.

Until now this only ever appeared as a notification that vanished, and otherwise lived in the log
file. That is the wrong place for it: "why did nothing happen" is the commonest question a spoken
command raises, and the answer is usually either a phrase worth adding or a wake word being heard
by accident. Both are visible here, with one button to act on the first.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from . import APP_NAME, voice_commands

MAX_REMEMBERED = 60


class MissedPhrases:
    """The phrases heard after the wake word that were not commands, newest first."""

    def __init__(self, limit=MAX_REMEMBERED):
        self.limit = limit
        self._counts = {}

    def add(self, phrase):
        if not isinstance(phrase, str):
            return  # nothing heard at all; "None" is not a phrase
        phrase = " ".join(phrase.split())
        if not phrase:
            return
        self._counts[phrase] = self._counts.get(phrase, 0) + 1
        while len(self._counts) > self.limit:
            self._counts.pop(next(iter(self._counts)))

    def rows(self):
        """(phrase, how many times) with the most often heard first."""
        return sorted(self._counts.items(), key=lambda row: (-row[1], row[0]))

    def total(self):
        return sum(self._counts.values())

    def clear(self):
        self._counts.clear()


class MissedWindow(QDialog):
    """The list, with a button to turn a phrase into a command of your own."""

    def __init__(self, missed, cfg, add_command=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} — heard but not understood")
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.resize(640, 460)
        self.missed = missed
        self.add_command = add_command
        layout = QVBoxLayout(self)

        warning = voice_commands.wake_word_warning(cfg.get("voice_command_wake", ""))
        rows = missed.rows()
        note = QLabel(
            f"EchoSub heard your wake word {missed.total()} times in this session without a command after it. "
            "A phrase you meant can be made into one; the rest is usually your wake word turning up in "
            "something the PC was playing."
            if rows else "Nothing has been misheard this session.")
        note.setWordWrap(True)
        note.setStyleSheet("color: gray;")
        layout.addWidget(note)
        if warning:
            caution = QLabel("Your wake word may be the problem: " + warning)
            caution.setWordWrap(True)
            caution.setStyleSheet("color: #D4A03C;")
            layout.addWidget(caution)

        self.table = QTableWidget(len(rows), 2)
        self.table.setHorizontalHeaderLabels(("Heard", "Times"))
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        for index, (phrase, count) in enumerate(rows):
            self.table.setItem(index, 0, QTableWidgetItem(phrase))
            self.table.setItem(index, 1, QTableWidgetItem(str(count)))
        if rows:
            self.table.selectRow(0)
        layout.addWidget(self.table)

        buttons = QHBoxLayout()
        self.make = QPushButton("Make this a command…")
        self.make.setEnabled(bool(rows) and add_command is not None)
        self.make.clicked.connect(self._make_one)
        forget = QPushButton("Forget these")
        forget.clicked.connect(self._forget)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        buttons.addWidget(self.make)
        buttons.addWidget(forget)
        buttons.addStretch(1)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    def selected_phrase(self):
        item = self.table.item(self.table.currentRow(), 0)
        return item.text() if item is not None else ""

    def _make_one(self):
        phrase = self.selected_phrase()
        if phrase and self.add_command is not None:
            self.accept()
            self.add_command(phrase)

    def _forget(self):
        self.missed.clear()
        self.table.setRowCount(0)
        self.make.setEnabled(False)
