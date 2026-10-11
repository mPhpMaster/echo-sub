# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""EchoSub Lens: a keyboard shortcut for every option, each one set to any key the user likes."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QHBoxLayout, QKeySequenceEdit, QLabel, QPushButton, QTableWidget, QVBoxLayout,
                               QWidget)

from . import hotkeys

# name -> (what it does, default key). The order is the order in the Settings window.
ACTIONS = {
    "toggle": ("Start or stop translating", "Ctrl+Alt+T"),
    "area": ("Choose an area of the screen", "Ctrl+Alt+R"),
    "file": ("Translate a file (image, PDF, Word…)", "Ctrl+Alt+F"),
    "mouse_mode": ("Lens around the mouse on / off", "Ctrl+Alt+M"),
    "lens_bigger": ("Make the lens bigger", ""),
    "lens_smaller": ("Make the lens smaller", ""),
    "screen_1": ("Translate screen 1", ""),
    "screen_2": ("Translate screen 2", ""),
    "screen_3": ("Translate screen 3", ""),
    "language_next": ("Translate into the next language", ""),
    "translator_next": ("Switch to the next translator", ""),
    "select_mode": ("Select mode on / off", ""),
    "copy_all": ("Copy all translations", ""),
    "capture": ("Show in screenshots and screen sharing on / off", ""),
    "appearance": ("Appearance (font, size, colours)", ""),
    "settings": ("Open the settings", ""),
    "quit": ("Exit EchoSub Lens", ""),
}


def defaults():
    return {name: key for name, (_, key) in ACTIONS.items()}


def merged(saved):
    """Every action with its key: the user's choice where there is one ("" = no key), else the default."""
    keys = defaults()
    if isinstance(saved, dict):
        keys.update({k: str(v) for k, v in saved.items() if k in ACTIONS})
    return keys


def native(text):
    """How a shortcut reads in menus on this PC ("Ctrl+Alt+T")."""
    return QKeySequence(text, QKeySequence.PortableText).toString(QKeySequence.NativeText) if text else ""


def problems(keys):
    """{action: why its key cannot be used} — a key that is not usable, or one given to two actions."""
    found, seen = {}, {}
    taken_by_echosub = {(mods, vk): label for label, mods, vk in hotkeys.HOTKEYS.values()}
    for name, text in keys.items():
        if not text:
            continue
        parsed = hotkeys.parse(text)
        if parsed is None:
            found[name] = "This key cannot be used as a shortcut"
        elif parsed in seen:
            found[name] = f"Also used for “{ACTIONS[seen[parsed]][0]}”"
        elif parsed in taken_by_echosub:
            found[name] = "EchoSub's captions use this key"
        else:
            seen[parsed] = name
    return found


class ShortcutsPage(QWidget):
    """A table: the action, its key (click and press the keys), and a button to clear it."""
    changed = Signal()

    def __init__(self, keys, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        intro = QLabel("Click a box and press the key or the combination you want — any key works, with or "
                       "without Ctrl, Alt, Shift or the Windows key. The keys work everywhere, even while a "
                       "game or a video has the keyboard.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.table = QTableWidget(len(ACTIONS), 3)
        self.table.setHorizontalHeaderLabels(["Option", "Key", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.editors = {}
        for row, (name, (title, _)) in enumerate(ACTIONS.items()):
            label = QLabel(title)
            label.setContentsMargins(6, 0, 6, 0)
            self.table.setCellWidget(row, 0, label)
            editor = QKeySequenceEdit()
            editor.setMaximumSequenceLength(1)
            editor.keySequenceChanged.connect(self._edited)
            self.table.setCellWidget(row, 1, editor)
            clear = QPushButton("Clear")
            clear.setToolTip("No key for this option")
            clear.clicked.connect(editor.clear)
            self.table.setCellWidget(row, 2, clear)
            self.editors[name] = editor
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setColumnWidth(0, 320)
        self.table.setColumnWidth(1, 200)
        self.table.setColumnWidth(2, 70)
        self.table.resizeRowsToContents()
        layout.addWidget(self.table, 1)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color: #E57373;")
        layout.addWidget(self.status)
        row = QHBoxLayout()
        row.addStretch(1)
        reset = QPushButton("Restore default keys")
        reset.clicked.connect(lambda: self.load(defaults()))
        row.addWidget(reset)
        layout.addLayout(row)
        self.load(keys)

    def load(self, keys):
        for name, editor in self.editors.items():
            editor.blockSignals(True)
            editor.setKeySequence(QKeySequence(keys.get(name, ""), QKeySequence.PortableText))
            editor.blockSignals(False)
        self._edited()

    def value(self):
        return {name: editor.keySequence().toString(QKeySequence.PortableText)
                for name, editor in self.editors.items()}

    def show_unavailable(self, labels):
        """Keys Windows would not give Lens because another program holds them."""
        if labels:
            self.status.setText("Another program already uses: " + ", ".join(labels))

    def _edited(self, *_):
        found = problems(self.value())
        for row, name in enumerate(ACTIONS):
            self.editors[name].setStyleSheet("background: #5D2B2B;" if name in found else "")
            self.editors[name].setToolTip(found.get(name, ""))
        self.status.setText("\n".join(f"{ACTIONS[n][0]}: {why}" for n, why in found.items()))
        self.changed.emit()

    def valid(self):
        return not problems(self.value())
