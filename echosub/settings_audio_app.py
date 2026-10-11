# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""The "Only this program" field of the Settings window (see app_audio)."""
from PySide6.QtWidgets import QComboBox

from . import app_audio

EVERYTHING = "Everything the PC plays"


def app_field(cfg):
    """An editable list: everything, the programs playing sound now, and the one already chosen."""
    field = QComboBox()
    field.setEditable(True)
    field.addItem(EVERYTHING, "")
    chosen = str(cfg.get("audio_app") or "")
    names = app_audio.programs_with_sound()
    if chosen and chosen not in names:
        names.append(chosen)
    for name in names:
        field.addItem(name, name)
    field.setCurrentIndex(max(0, field.findData(chosen)))
    available = app_audio.available()
    field.setEnabled(available)
    field.setToolTip("Caption only this program — Discord, say, without the game or the music. The list shows the "
                     "programs playing sound right now; you can also type a program's file name."
                     if available else "Needs Windows 10 version 2004 or later")
    return field


def app_value(field):
    text = field.currentText().strip()
    return "" if not text or text == EVERYTHING else text
