# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""The "go to ..." part of the Commands tab: your own folders, and the name you say for each."""
from PySide6.QtWidgets import (
    QFileDialog, QGroupBox, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from . import voice_destinations


class GoToGroupMixin:
    """Say "go to" and a name: one of your Windows folders, one you added, or a web address."""

    def _go_to_group(self, cfg):
        group = QGroupBox("Go to a place")
        layout = QVBoxLayout(group)
        known = ", ".join(sorted(voice_destinations.windows_folders()))
        note = QLabel(
            f'Say “go to …” with a web address (“go to www.example.com”) and it opens in your browser, '
            f'or with the name of a folder and it opens in File Explorer. Your Windows folders already '
            f'work: {known}. Add more below with the name you want to say for each. A spoken word never '
            f'becomes a path — it only picks one written here — and only plain http and https addresses '
            f'are opened, never a file, a script or a download.')
        note.setWordWrap(True)
        note.setStyleSheet("color: gray;")
        layout.addWidget(note)

        self.go_folder_table = QTableWidget(0, 2)
        self.go_folder_table.setHorizontalHeaderLabels(("Name to say", "Folder"))
        self.go_folder_table.verticalHeader().setVisible(False)
        self.go_folder_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.go_folder_table.setMinimumHeight(120)
        self.go_folder_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.go_folder_table)

        buttons = QHBoxLayout()
        add = QPushButton("Add folder…")
        add.clicked.connect(self._choose_go_folder)
        remove = QPushButton("Remove selected")
        remove.clicked.connect(self._remove_go_folder)
        buttons.addWidget(add)
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
        self.go_folder_table.setCurrentCell(row, 0)

    def _choose_go_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Pick a folder you want to say a name for")
        if path:
            self._add_go_folder(path.rstrip("/\\").rsplit("/", 1)[-1].rsplit("\\", 1)[-1], path.replace("/", "\\"))

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
