# SPDX-License-Identifier: GPL-3.0-only

# Copyright (C) 2026 Mohammad Al-Safadi

"""The microphone settings: capture what you say as well as what the PC plays."""

from PySide6.QtWidgets import QCheckBox, QFormLayout, QGroupBox, QLineEdit


from . import audio, config

from .settings_tabs import hint

from .settings_widgets import ColorButton, SearchableComboBox


class MicrophoneGroupMixin:

    """Adds the Microphone box to the Language & Engine tab."""

    def _microphone_group(self, cfg):
        group = QGroupBox("Microphone")
        f = QFormLayout(group)
        self.mic_enabled = QCheckBox("Also caption what the microphone hears")
        self.mic_enabled.setChecked(cfg.get("mic_enabled", False))
        self.mic_device = SearchableComboBox()
        self.mic_device.addItem("Default microphone (follows Windows)", "default")
        try:

            for _, name in audio.list_input_devices():

                self.mic_device.addItem(name, name)
        except Exception:

            pass
        self._select(self.mic_device, cfg.get("mic_device", "default"))
        self.mic_label = QLineEdit(cfg.get("mic_label", config.DEFAULTS["mic_label"]))
        self.mic_label.setMaximumWidth(140)
        self.mic_label.setPlaceholderText(config.DEFAULTS["mic_label"])
        self.mic_color = ColorButton(cfg.get("mic_color", config.DEFAULTS["mic_color"]))
        self.mic_commands = QCheckBox("Accept spoken commands from the microphone too")
        self.mic_commands.setChecked(cfg.get("mic_commands", True))
        f.addRow(self.mic_enabled)
        f.addRow("Microphone:", self.mic_device)
        f.addRow("Shown as:", self.mic_label)
        f.addRow("Its colour:", self.mic_color)
        f.addRow(self.mic_commands)
        f.addRow(hint("Your voice is captioned and translated like anything else, in its own colour and with "
                      "this label, so it is clear who said what. It is recognized on the same model, so it "
                      "costs nothing extra while nobody is talking."))
        self.mic_enabled.toggled.connect(self._update_microphone_controls)
        self._update_microphone_controls()
        return group

    def _update_microphone_controls(self):
        on = self.mic_enabled.isChecked()
        for widget in (self.mic_device, self.mic_label, self.mic_color, self.mic_commands):

            widget.setEnabled(on)

    def _microphone_values(self):
        return {
            "mic_enabled": self.mic_enabled.isChecked(),
            "mic_device": self.mic_device.currentData(),
            "mic_label": self.mic_label.text().strip(),
            "mic_color": self.mic_color.color,
            "mic_commands": self.mic_commands.isChecked(),
        }
