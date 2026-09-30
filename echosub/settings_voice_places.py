# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""The "go to ..." part of the Commands tab: your own places, and the word you say for each."""
import os

from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QFileDialog, QGroupBox, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from . import voice_destinations

PATH_OK = "#7FB77F"  # a path that is really there, so a typo stands out in red beside it


class GoToGroupMixin:
    """Say "go to" and a name: one of your Windows folders, one you added, or a web address."""

    def _go_to_group(self, cfg):
        group = QGroupBox("Go to a place, or play a file")
        layout = QVBoxLayout(group)
        known = ", ".join(sorted(voice_destinations.windows_folders()))
        note = QLabel(
            f'Write the word you want to say and the path it stands for, one per row — type both in yourself, '
            f'or use the buttons to pick. Say “play <word>” or “go to <word>” and a file opens with the program '
            f'Windows normally uses for it, so a song plays in your music player, while a folder opens in File '
            f'Explorer. A path shown in red is not on this PC. Your Windows folders already work without being '
            f'added: {known}. “Go to …” also takes a web address (“go to www.example.com”). A spoken word never '
            f'becomes a path: it only picks one written here, and only plain http and https addresses open.')
        note.setWordWrap(True)
        note.setStyleSheet("color: gray;")
        layout.addWidget(note)

        self.go_folder_table = QTableWidget(0, 2)
        self.go_folder_table.setHorizontalHeaderLabels(("Name to say", "Folder or file"))
        self.go_folder_table.verticalHeader().setVisible(False)
        self.go_folder_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.go_folder_table.setMinimumHeight(120)
        self.go_folder_table.horizontalHeader().setStretchLastSection(True)
        self.go_folder_table.itemChanged.connect(self._check_go_paths)
        layout.addWidget(self.go_folder_table)

        buttons = QHBoxLayout()
        typed = QPushButton("Add a row")
        typed.setToolTip("Type the word to say and the path yourself")
        typed.clicked.connect(lambda: self._add_go_folder())
        add = QPushButton("Pick a folder…")
        add.clicked.connect(self._choose_go_folder)
        add_file = QPushButton("Pick a file…")
        add_file.setToolTip("A song, a playlist, a document — it opens with its usual program")
        add_file.clicked.connect(self._choose_go_file)
        remove = QPushButton("Remove selected")
        remove.clicked.connect(self._remove_go_folder)
        buttons.addWidget(typed)
        buttons.addWidget(add)
        buttons.addWidget(add_file)
        buttons.addWidget(remove)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        for entry in voice_destinations.valid_folders(cfg.get("voice_go_folders", [])):
            self._add_go_folder(entry["name"], entry["path"])
        return group

    def _add_go_folder(self, name="", path=""):
        row = self.go_folder_table.rowCount()
        self.go_folder_table.insertRow(row)
        self.go_folder_table.setItem(row, 0, QTableWidgetItem(str(name)))
        self.go_folder_table.setItem(row, 1, QTableWidgetItem(str(path)))
        self._mark_missing_path(row)
        self.go_folder_table.setCurrentCell(row, 0)
        if not name:  # a row to type into: start in the first cell straight away
            self.go_folder_table.editItem(self.go_folder_table.item(row, 0))

    def _mark_missing_path(self, row):
        """Colour a path that is not on this PC, so a typo is visible before it is saved."""
        item = self.go_folder_table.item(row, 1)
        if item is None:
            return
        path = item.text().strip().strip('"')
        missing = bool(path) and not os.path.exists(path)
        item.setForeground(QBrush(QColor("#D45B5B")) if missing else QBrush(QColor(PATH_OK)))
        item.setToolTip("There is nothing at this path yet" if missing else path)

    def _check_go_paths(self, item):
        if item is not None and item.column() == 1:
            self.go_folder_table.blockSignals(True)
            self._mark_missing_path(item.row())
            self.go_folder_table.blockSignals(False)

    @staticmethod
    def _suggested_name(path):
        """The last part of the path, without its extension: a reasonable thing to say for it."""
        tail = path.rstrip("/\\").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        return tail.rsplit(".", 1)[0] if "." in tail[1:] else tail

    def _choose_go_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Pick a folder you want to say a name for")
        if path:
            self._add_go_folder(self._suggested_name(path), path.replace("/", "\\"))

    def _choose_go_file(self):
        path, _filter = QFileDialog.getOpenFileName(self, "Pick a file you want to say a name for")
        if path:
            self._add_go_folder(self._suggested_name(path), path.replace("/", "\\"))

    def _remove_go_folder(self):
        for row in sorted({index.row() for index in self.go_folder_table.selectedIndexes()}, reverse=True):
            self.go_folder_table.removeRow(row)

    def go_folder_rows(self):
        rows = []
        for row in range(self.go_folder_table.rowCount()):
            name = self.go_folder_table.item(row, 0)
            path = self.go_folder_table.item(row, 1)
            rows.append({"name": name.text() if name else "", "path": path.text() if path else ""})
        return rows
