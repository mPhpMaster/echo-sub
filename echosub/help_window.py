# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""What you can say, in English and in the language you are translating into.

Every row is built from the command tables themselves rather than written out by hand, so this
window cannot drift away from what the app actually does. A command that is switched off is still
listed, marked as off, because "why did nothing happen" is the question this window exists for.

The translation uses the translator the app already has loaded, on a thread, so the window opens
at once and the second column fills itself in.
"""
import logging
import threading
from collections import deque

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from . import APP_NAME, languages

log = logging.getLogger(__name__)


def rows(cfg):
    """(what to say, what it does, whether it is on) for everything the app understands."""
    from . import voice_commands, voice_destinations

    wake = (cfg.get("voice_command_wake") or "echo sub").split(",")[0].strip() or "echo sub"
    on = cfg.get("voice_commands", False)
    said = []

    def add(say, does, enabled=True):
        said.append((f"{wake}, {say}" if say else wake, does, bool(on and enabled)))

    add("", "Say the name on its own to stop the captions, and again to bring them back")
    add("pause captions / resume captions", "Stop and start the captions")
    add("hide captions / show captions", "Take the caption box off the screen, and put it back")
    add("clear captions", "Empty the caption box")
    add("open <app> / close <app>", "One of the everyday apps: " + ", ".join(sorted(voice_commands.APPS)))
    add("play / stop / next / previous / mute / volume up", "The media keys, as on a keyboard")
    add("open youtube / open google", "Opens that site in your own browser")
    add("go to <web address>", "Opens a plain http or https address in your browser")
    add("go to <folder>", "Opens a folder: " + ", ".join(sorted(voice_destinations.windows_folders()))
        + ", and any you added in the settings")
    add("play <name>", "Plays a file you added in the settings, with its usual program")
    add("mute my microphone", "Stops EchoSub hearing your microphone, and again to bring it back. "
                              "Only your own microphone can say this")
    add("help", "Opens this window")
    add("press <keys>", "Presses keys by name, such as windows, windows and r, ctrl shift escape",
        cfg.get("voice_key_presses", False))
    add("type <words>", "Types what you say into the window you are using",
        cfg.get("voice_typing", False))
    add("press enter", "Presses Enter on its own", cfg.get("voice_typing", False))
    for entry in voice_commands.valid_custom_commands(cfg.get("voice_custom_commands", [])):
        what = f"Starts {entry['run']}" if "run" in entry else f"Your own command: {entry['command']}"
        add(entry["phrase"], what)
    said.append(("no", "While a command is counting down, this calls it off. No name needed", True))
    return said


class HelpWindow(QDialog):
    """The list of commands, with a translation beside each one."""

    def __init__(self, cfg, translator=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} — what you can say")
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.resize(900, 560)
        target = cfg.get("target_lang", "en")
        self._rtl = target in languages.RTL
        layout = QVBoxLayout(self)

        note = QLabel(
            "Everything EchoSub understands. Anything the PC plays has to start with your wake word; "
            "your own microphone may not need it. A row shown in grey is switched off in the settings.")
        note.setWordWrap(True)
        note.setStyleSheet("color: gray;")
        layout.addWidget(note)

        self.rows = rows(cfg)
        self.table = QTableWidget(len(self.rows), 3)
        self.table.setHorizontalHeaderLabels(("Say this", "What it does", languages.name(target)))
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setWordWrap(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        for index, (say, does, enabled) in enumerate(self.rows):
            self.table.setItem(index, 0, QTableWidgetItem(say))
            self.table.setItem(index, 1, QTableWidgetItem(does))
            self.table.setItem(index, 2, QTableWidgetItem("" if target == "en" else "…"))
            if not enabled:
                for column in range(3):
                    self.table.item(index, column).setToolTip("Switched off in Settings → Commands")
                    self.table.item(index, column).setForeground(Qt.gray)
        self.table.resizeRowsToContents()
        layout.addWidget(self.table)

        buttons = QHBoxLayout()
        copy = QPushButton("Copy all")
        copy.clicked.connect(self._copy)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        buttons.addWidget(copy)
        buttons.addStretch(1)
        buttons.addWidget(close)
        layout.addLayout(buttons)

        # The thread never touches the window. It leaves finished lines in a queue, and a timer
        # belonging to the window picks them up: a timer stops when its window goes, so closing
        # this one mid-translation cannot reach a window that is already gone.
        self._done = deque()
        self._stop = threading.Event()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._drain)
        if target != "en" and translator is not None:
            self.table.setColumnHidden(2, False)
            self._timer.start(150)
            threading.Thread(target=self._translate_all, args=(translator, target),
                             name="help-translate", daemon=True).start()
        elif target == "en":
            self.table.setColumnHidden(2, True)

    def closeEvent(self, event):
        self._stop.set()
        self._timer.stop()
        super().closeEvent(event)

    def _translate_all(self, translator, target):
        for index, (_say, does, _enabled) in enumerate(self.rows):
            if self._stop.is_set():
                return
            try:
                text = translator.translate(does, "en", target)
            except Exception as e:  # a translator that is busy or offline must not break the window
                log.info("Could not translate a help line: %s", e)
                text = ""
            self._done.append((index, text or ""))

    def _drain(self):
        while self._done:
            index, text = self._done.popleft()
            self._fill(index, text)

    def _fill(self, index, text):
        item = self.table.item(index, 2)
        if item is not None:
            item.setText(text)
            if self._rtl:  # Arabic, Persian, Hebrew and the rest read the other way
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.resizeRowToContents(index)

    def _copy(self):
        lines = []
        for index, (say, does, enabled) in enumerate(self.rows):
            extra = self.table.item(index, 2).text() if not self.table.isColumnHidden(2) else ""
            off = "" if enabled else "  (switched off)"
            lines.append(f"{say}\t{does}{off}" + (f"\t{extra}" if extra else ""))
        QGuiApplication.clipboard().setText("\n".join(lines))
