# SPDX-License-Identifier: GPL-3.0-only

# Copyright (C) 2026 Mohammad Al-Safadi

"""The on-screen answers part of the Commands tab: your phrases and your own written replies."""

from PySide6.QtWidgets import (

    QCheckBox, QGroupBox, QHBoxLayout, QLabel, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,

    QVBoxLayout,

)


from . import screen_replies


class ScreenRepliesGroupMixin:
    """Phrase in, your own sentence on screen. Nothing is sent anywhere and nothing is generated."""

    def _screen_replies_group(self, cfg):
        group = QGroupBox("On-screen answers")

        layout = QVBoxLayout(group)

        self.screen_replies = QCheckBox("Answer chosen phrases with my own text in the caption box")

        self.screen_replies.setChecked(cfg.get("screen_replies", False))

        layout.addWidget(self.screen_replies)

        note = QLabel(

            "For a shared screen: someone says the wake word and one of your phrases, and EchoSub writes "

            "your prepared line in the caption box for everyone watching. Nothing is sent to Discord or "

            "anywhere else, nothing is typed into another program, and no answer is made up — each line is "

            "the one you wrote here.")

        note.setWordWrap(True)

        note.setStyleSheet("color: gray;")

        layout.addWidget(note)

        self.screen_reply_table = QTableWidget(0, 2)

        self.screen_reply_table.setHorizontalHeaderLabels(("Spoken phrase", "What the box shows"))

        self.screen_reply_table.verticalHeader().setVisible(False)

        self.screen_reply_table.setSelectionBehavior(QTableWidget.SelectRows)

        self.screen_reply_table.setMinimumHeight(150)

        self.screen_reply_table.horizontalHeader().setStretchLastSection(True)

        layout.addWidget(self.screen_reply_table)

        buttons = QHBoxLayout()

        add = QPushButton("Add answer")

        add.clicked.connect(lambda: self._add_screen_reply())

        remove = QPushButton("Remove selected")

        remove.clicked.connect(self._remove_screen_reply)

        examples = QPushButton("Add examples")

        examples.setToolTip("A few ready-made answers you can edit")

        examples.clicked.connect(self._add_screen_reply_examples)

        self.screen_reply_seconds = QSpinBox()

        self.screen_reply_seconds.setRange(2, 60)

        self.screen_reply_seconds.setSuffix(" s")

        self.screen_reply_seconds.setMaximumWidth(90)

        self.screen_reply_seconds.setValue(int(cfg.get("screen_reply_seconds", screen_replies.DEFAULT_SECONDS)))

        buttons.addWidget(add)

        buttons.addWidget(remove)

        buttons.addWidget(examples)

        buttons.addStretch(1)

        buttons.addWidget(QLabel("Stays on screen for:"))

        buttons.addWidget(self.screen_reply_seconds)

        layout.addLayout(buttons)

        for pair in screen_replies.valid_pairs(cfg.get("screen_reply_pairs", [])):

            self._add_screen_reply(pair["phrase"], pair["reply"])

        self.screen_replies.toggled.connect(self._update_screen_reply_controls)

        self._update_screen_reply_controls()

        return group

    def _update_screen_reply_controls(self):
        on = self.screen_replies.isChecked()

        self.screen_reply_table.setEnabled(on)

        self.screen_reply_seconds.setEnabled(on)

    def _add_screen_reply(self, phrase="", reply=""):
        row = self.screen_reply_table.rowCount()

        self.screen_reply_table.insertRow(row)

        self.screen_reply_table.setItem(row, 0, QTableWidgetItem(str(phrase)))

        self.screen_reply_table.setItem(row, 1, QTableWidgetItem(str(reply)))

        self.screen_reply_table.setCurrentCell(row, 0)

    def _add_screen_reply_examples(self):
        for example in screen_replies.EXAMPLES:

            self._add_screen_reply(example["phrase"], example["reply"])

    def _remove_screen_reply(self):
        for row in sorted({index.row() for index in self.screen_reply_table.selectedIndexes()}, reverse=True):

            self.screen_reply_table.removeRow(row)

    def screen_reply_values(self):
        pairs = []

        for row in range(self.screen_reply_table.rowCount()):

            phrase = self.screen_reply_table.item(row, 0)

            reply = self.screen_reply_table.item(row, 1)

            pairs.append({"phrase": phrase.text() if phrase else "", "reply": reply.text() if reply else ""})

        return {

            "screen_replies": self.screen_replies.isChecked(),

            "screen_reply_pairs": screen_replies.valid_pairs(pairs),

            "screen_reply_seconds": self.screen_reply_seconds.value(),

        }
