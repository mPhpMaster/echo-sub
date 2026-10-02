# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Settings for your own spellings and the words you want to be told about."""
from PySide6.QtWidgets import (
    QCheckBox, QGroupBox, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)

from . import transcript_fixes


class TranscriptFixesMixin:
    """A word swap you control, and a watch list that only ever tells you."""

    def _transcript_fixes_group(self, cfg):
        group = QGroupBox("Your own spellings")
        layout = QVBoxLayout(group)
        note = QLabel(
            "Speech recognition does not know how a game, a guild or a friend of yours is spelled, so it "
            "writes something that sounds close. Put what it writes on the left and what you want on the "
            "right. Whole words only, upper or lower case, and it applies to the translation as well.")
        note.setWordWrap(True)
        note.setStyleSheet("color: gray;")
        layout.addWidget(note)

        self.fix_table = QTableWidget(0, 2)
        self.fix_table.setHorizontalHeaderLabels(("When it writes", "Put this instead"))
        self.fix_table.verticalHeader().setVisible(False)
        self.fix_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.fix_table.setMinimumHeight(130)
        self.fix_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.fix_table)

        buttons = QHBoxLayout()
        add = QPushButton("Add a row")
        add.clicked.connect(lambda: self._add_fix())
        remove = QPushButton("Remove selected")
        remove.clicked.connect(self._remove_fix)
        buttons.addWidget(add)
        buttons.addWidget(remove)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        for fix in transcript_fixes.valid_fixes(cfg.get("transcript_fixes", [])):
            self._add_fix(fix["heard"], fix["write"])
        return group

    def _add_fix(self, heard="", write=""):
        row = self.fix_table.rowCount()
        self.fix_table.insertRow(row)
        self.fix_table.setItem(row, 0, QTableWidgetItem(str(heard)))
        self.fix_table.setItem(row, 1, QTableWidgetItem(str(write)))
        self.fix_table.setCurrentCell(row, 0)
        if not heard:
            self.fix_table.editItem(self.fix_table.item(row, 0))

    def _remove_fix(self):
        for row in sorted({index.row() for index in self.fix_table.selectedIndexes()}, reverse=True):
            self.fix_table.removeRow(row)

    def _alert_words_group(self, cfg):
        group = QGroupBox("Tell me when these are said")
        layout = QVBoxLayout(group)
        self.alert_sound = QCheckBox("Show a notification when one of these words is heard")
        self.alert_sound.setChecked(cfg.get("alert_sound", True))
        layout.addWidget(self.alert_sound)
        note = QLabel(
            "One word or phrase per line — your name, your guild, anything you do not want to miss while "
            "you are busy. The caption is never changed; you are only told about it.")
        note.setWordWrap(True)
        note.setStyleSheet("color: gray;")
        layout.addWidget(note)
        self.alert_words = QPlainTextEdit("\n".join(transcript_fixes.valid_alerts(cfg.get("alert_words", []))))
        self.alert_words.setPlaceholderText("Sensei\nMegabonk")
        self.alert_words.setMaximumHeight(110)
        layout.addWidget(self.alert_words)
        return group

    def transcript_fix_values(self):
        fixes = []
        for row in range(self.fix_table.rowCount()):
            heard = self.fix_table.item(row, 0)
            write = self.fix_table.item(row, 1)
            fixes.append({"heard": heard.text() if heard else "", "write": write.text() if write else ""})
        return {
            "transcript_fixes": transcript_fixes.valid_fixes(fixes),
            "alert_words": transcript_fixes.valid_alerts(self.alert_words.toPlainText().splitlines()),
            "alert_sound": self.alert_sound.isChecked(),
        }
