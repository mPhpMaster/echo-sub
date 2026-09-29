# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Settings tab for explicit, safe spoken-command mappings."""
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import config, voice_commands, voice_destinations
from .settings_screen_replies import ScreenRepliesGroupMixin
from .settings_voice_places import GoToGroupMixin

RUN_KEY = "__run__"  # the combo entry that means "start the program I typed", not a built-in action


class VoiceCommandsTabMixin(ScreenRepliesGroupMixin, GoToGroupMixin):
    """Keeps custom phrases constrained to the approved command registry."""

    def _commands_tab(self, cfg):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        base = QGroupBox("Voice command controls")
        form = QFormLayout(base)
        self.voice_commands = QCheckBox("Enable spoken commands")
        self.voice_commands.setChecked(cfg.get("voice_commands", False))
        self.voice_wake = QLineEdit(cfg.get("voice_command_wake", config.DEFAULTS["voice_command_wake"]))
        self.voice_wake.setPlaceholderText(config.DEFAULTS["voice_command_wake"])
        self.voice_wake.setMaximumWidth(280)
        self.voice_key_presses = QCheckBox("Allow short A-Z and 0-9 key presses after the wake word")
        self.voice_key_presses.setChecked(cfg.get("voice_key_presses", False))
        self.mic_wake_word = QCheckBox("My own microphone must say the wake word too")
        self.mic_wake_word.setChecked(cfg.get("mic_wake_word", False))
        self.voice_command_delay = QSpinBox()
        self.voice_command_delay.setRange(0, 30)
        self.voice_command_delay.setSuffix(" s")
        self.voice_command_delay.setSpecialValueText("run at once")
        self.voice_command_delay.setMaximumWidth(140)
        self.voice_command_delay.setValue(int(cfg.get("voice_command_delay", 3) or 0))
        form.addRow(self.voice_commands)
        form.addRow("Wake word:", self.voice_wake)
        form.addRow(self.mic_wake_word)
        form.addRow("Wait before running:", self.voice_command_delay)
        wait_note = QLabel(
            "What was understood is shown at the top of the screen for this long, and one click on it "
            "cancels the command. Set it to zero to run commands straight away.")
        wait_note.setWordWrap(True)
        wait_note.setStyleSheet("color: gray;")
        form.addRow(wait_note)
        form.addRow(self.voice_key_presses)
        info = QLabel(
            'Examples: “PC open calculator”, “PC افتح الحاسبة”, and “Alexa help”. '
            'Wake words can be separated with commas. Key presses are optional and only allow up to six '
            'single letters or digits; shortcuts, Enter, and system keys are never accepted.')
        info.setWordWrap(True)
        info.setStyleSheet("color: gray;")
        form.addRow(info)
        layout.addWidget(base)

        custom = QGroupBox("Custom commands")
        custom_layout = QVBoxLayout(custom)
        description = QLabel(
            "Add a phrase, then either pick one of the approved actions or choose “Start a program…” and "
            "type the program and its arguments yourself, the way you would in a shortcut. That line is "
            "started directly — it is not handed to a command shell, so pipes, redirection and “&&” are "
            "not run — and only ever the line you typed here: nothing that was said is ever added to it.")
        description.setWordWrap(True)
        description.setStyleSheet("color: gray;")
        custom_layout.addWidget(description)
        self.voice_custom_table = QTableWidget(0, 3)
        self.voice_custom_table.setHorizontalHeaderLabels(
            ("Spoken phrase", "Action", "Program and arguments"))
        self.voice_custom_table.verticalHeader().setVisible(False)
        self.voice_custom_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.voice_custom_table.setMinimumHeight(190)
        self.voice_custom_table.horizontalHeader().setStretchLastSection(True)
        custom_layout.addWidget(self.voice_custom_table)
        buttons = QHBoxLayout()
        add = QPushButton("Add command")
        remove = QPushButton("Remove selected")
        add.clicked.connect(self._add_voice_custom_command)
        remove.clicked.connect(self._remove_voice_custom_command)
        buttons.addWidget(add)
        buttons.addWidget(remove)
        buttons.addStretch(1)
        custom_layout.addLayout(buttons)
        layout.addWidget(custom)
        layout.addWidget(self._go_to_group(cfg))
        layout.addWidget(self._screen_replies_group(cfg))
        layout.addStretch(1)

        for item in voice_commands.valid_custom_commands(cfg.get("voice_custom_commands", [])):
            self._add_voice_custom_command(item["phrase"], item.get("command"), item.get("run", ""))
        return widget

    @staticmethod
    def _command_combo(selected=None):
        combo = QComboBox()
        combo.addItem("Start a program…", RUN_KEY)
        for item in voice_commands.COMMANDS:
            combo.addItem(item["label"], item["key"])
        index = combo.findData(selected)
        combo.setCurrentIndex(index if index >= 0 else 1)
        return combo

    def _add_voice_custom_command(self, phrase="", command_key=None, run=""):
        row = self.voice_custom_table.rowCount()
        self.voice_custom_table.insertRow(row)
        self.voice_custom_table.setItem(row, 0, QTableWidgetItem(str(phrase)))
        combo = self._command_combo(RUN_KEY if run else command_key)
        self.voice_custom_table.setCellWidget(row, 1, combo)
        line = QLineEdit(str(run))
        line.setPlaceholderText('notepad.exe "D:\\my notes.txt"')
        self.voice_custom_table.setCellWidget(row, 2, line)
        combo.currentIndexChanged.connect(lambda _index, edit=line, box=combo: self._follow_combo(box, edit))
        self._follow_combo(combo, line)
        self.voice_custom_table.setCurrentCell(row, 0)

    @staticmethod
    def _follow_combo(combo, line):
        """The program box only matters for a row that starts a program."""
        running = combo.currentData() == RUN_KEY
        line.setEnabled(running)
        if not running:
            line.clear()

    def _remove_voice_custom_command(self):
        selected = sorted({index.row() for index in self.voice_custom_table.selectedIndexes()}, reverse=True)
        for row in selected:
            self.voice_custom_table.removeRow(row)

    def voice_command_values(self):
        entries = []
        for row in range(self.voice_custom_table.rowCount()):
            item = self.voice_custom_table.item(row, 0)
            combo = self.voice_custom_table.cellWidget(row, 1)
            line = self.voice_custom_table.cellWidget(row, 2)
            phrase = item.text().strip() if item else ""
            key = combo.currentData() if combo else None
            run = line.text().strip() if line else ""
            if not phrase or not key:
                continue
            entries.append({"phrase": phrase, "run": run} if key == RUN_KEY else
                           {"phrase": phrase, "command": key})
        return {
            "voice_commands": self.voice_commands.isChecked(),
            "voice_command_wake": self.voice_wake.text().strip() or config.DEFAULTS["voice_command_wake"],
            "voice_custom_commands": voice_commands.valid_custom_commands(entries),
            "voice_key_presses": self.voice_key_presses.isChecked(),
            "voice_command_delay": self.voice_command_delay.value(),
            "mic_wake_word": self.mic_wake_word.isChecked(),
            "voice_go_folders": voice_destinations.valid_folders(self.go_folder_rows()),
            **self.screen_reply_values(),
        }
