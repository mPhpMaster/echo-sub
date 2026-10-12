# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""The "Only this program or window" field of the Settings window (see app_audio and app_windows)."""
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QPushButton, QToolTip, QWidget

from . import app_audio, app_windows

EVERYTHING = "Everything the PC plays"
NOTHING = ("", "", 0)
PICK = "Pick a window…"
PICK_SECONDS = 3
TITLE_CHARS = 60


def window_text(title, exe):
    short = title if len(title) <= TITLE_CHARS else title[:TITLE_CHARS - 1].rstrip() + "…"
    return f"Window: {short} — {exe}" if exe else f"Window: {short}"


class _Field(QComboBox):
    """An editable list that looks again at what is open each time it is opened."""

    def __init__(self, picker):
        super().__init__()
        self._picker = picker
        self.setEditable(True)

    def showPopup(self):
        self._picker.refresh()
        super().showPopup()


class AppPicker(QWidget):
    """Everything, a program playing sound now, or an open window — and a button to pick the window in front."""

    def __init__(self, cfg):
        super().__init__()
        self.field = _Field(self)
        self.pick = QPushButton(PICK)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.field, 1)
        layout.addWidget(self.pick)
        self._countdown = 0
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self.pick.clicked.connect(self._start_pick)
        app, window, pid = app_audio.chosen(cfg)
        self.refresh((app, window, pid))
        available = app_audio.available()
        self.setEnabled(available)
        self.field.setToolTip(
            "Caption only this program — Discord, say, without the game or the music — or only the program "
            "behind one window. The list shows the programs playing sound and the open windows right now; you "
            "can also type a program's file name.\nWindows keeps sound apart per program, not per window: two "
            "copies of a program can be told apart, but two windows of the same Chrome cannot."
            if available else "Needs Windows 10 version 2004 or later")
        self.pick.setToolTip(f"Click, then switch to the window you want within {PICK_SECONDS} seconds")

    def refresh(self, keep=None):
        keep = tuple(keep) if keep is not None else self.choice()
        field = self.field
        field.blockSignals(True)
        field.clear()
        field.addItem(EVERYTHING, NOTHING)
        for name in app_audio.programs_with_sound():
            field.addItem(name, (name, "", 0))
        windows = app_windows.open_windows()
        if windows:
            field.insertSeparator(field.count())
        for w in windows:
            field.addItem(window_text(w.title, w.exe), (w.exe, w.title, w.pid))
        self._select(keep)
        field.blockSignals(False)

    def _select(self, choice):
        if choice == NOTHING:
            self.field.setCurrentIndex(0)
            return
        same = [i for i in range(self.field.count()) if self._data(i)[:2] == choice[:2]]
        if not same:
            text = window_text(choice[1], choice[0]) if choice[1] else choice[0]
            self.field.addItem(text, choice)
            same = [self.field.count() - 1]
        exact = [i for i in same if self._data(i) == choice]
        self.field.setCurrentIndex((exact or same)[0])

    def _data(self, index):
        data = self.field.itemData(index)
        return tuple(data) if isinstance(data, (tuple, list)) and len(data) == 3 else NOTHING

    def choice(self):
        """(program, window title, its process) for what is shown; a typed name means that program."""
        text = self.field.currentText().strip()
        index = self.field.currentIndex()
        if index >= 0 and self.field.itemText(index) == text:
            return self._data(index)
        return NOTHING if not text or text == EVERYTHING else (text, "", 0)

    def values(self):
        app, window, pid = self.choice()
        return {"audio_app": app, "audio_window": window, "audio_window_pid": pid if window else 0}

    def _start_pick(self):
        self._countdown = PICK_SECONDS
        self.pick.setEnabled(False)
        self._show_countdown()
        self._timer.start()

    def _show_countdown(self):
        self.pick.setText(f"Switch to it… {self._countdown}")

    def _tick(self):
        self._countdown -= 1
        if self._countdown > 0:
            self._show_countdown()
            return
        self._timer.stop()
        self.pick.setText(PICK)
        self.pick.setEnabled(True)
        found = app_windows.window_in_front()
        self.window().raise_()
        self.window().activateWindow()
        if found is None:
            QToolTip.showText(self.pick.mapToGlobal(self.pick.rect().bottomLeft()),
                              f"No other window was in front — click {PICK!r} and switch to it within "
                              f"{PICK_SECONDS} seconds", self.pick)
            return
        self.refresh((found.exe, found.title, found.pid))


def app_field(cfg):
    return AppPicker(cfg)
