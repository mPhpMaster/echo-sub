# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""EchoSub Lens: how the translations look — font, size, colours — and the settings page that changes it."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFontComboBox, QFormLayout, QHBoxLayout, QPushButton, QSlider,
                               QSpinBox, QWidget)

from .settings_widgets import ColorButton

AUTO = "auto"  # colours: match the page under the text
DEFAULT_STYLE = {
    "font_family": "Segoe UI",
    "size_mode": "fit",          # fit: as big as the original text | fixed: always font_px
    "size_scale": 100,           # % of the fitted size
    "font_px": 16,
    "bold": False,
    "text_color": AUTO,          # AUTO: black or white, whichever reads best on the background
    "background": AUTO,          # AUTO: the page's own colour under the text
    "opacity": 1.0,              # of the background (the text itself is always solid)
    "radius": 2,                 # rounded corners, px
}


def merged(style):
    """`style` completed with the defaults; unknown keys dropped (a settings file from another version)."""
    result = dict(DEFAULT_STYLE)
    if isinstance(style, dict):
        result.update({k: v for k, v in style.items() if k in DEFAULT_STYLE})
    return result


def hex_to_rgb(color):
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def colors(style, page_background, page_foreground):
    """(background, text) colours for one block, as (r, g, b): the page's own unless the user chose some."""
    background = page_background if style["background"] == AUTO else hex_to_rgb(style["background"])
    if style["text_color"] != AUTO:
        return background, hex_to_rgb(style["text_color"])
    if style["background"] == AUTO:
        return background, page_foreground
    luminance = 0.299 * background[0] + 0.587 * background[1] + 0.114 * background[2]
    return background, ((0, 0, 0) if luminance > 140 else (255, 255, 255))


class _ColorChoice(QWidget):
    """"Match the page" or a colour of your own."""

    def __init__(self, value, on_change, default_color):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.mode = QComboBox()
        self.mode.addItems(["Match the page", "My colour"])
        self.button = ColorButton(default_color if value == AUTO else value)
        self.mode.setCurrentIndex(0 if value == AUTO else 1)
        self.button.setEnabled(value != AUTO)
        row.addWidget(self.mode)
        row.addWidget(self.button)
        self.mode.currentIndexChanged.connect(lambda i: (self.button.setEnabled(i == 1), on_change()))
        self.button.changed.connect(on_change)

    def value(self):
        return AUTO if self.mode.currentIndex() == 0 else self.button.color


class AppearancePage(QWidget):
    """The Appearance settings. `changed(style)` fires on every change, so it shows on the screen at once."""
    changed = Signal(dict)

    def __init__(self, style, parent=None):
        super().__init__(parent)
        form = QFormLayout(self)

        self.font_box = QFontComboBox()
        self.font_box.setCurrentFont(QFont(style["font_family"]))
        form.addRow("Font", self.font_box)

        self.size_mode = QComboBox()
        self.size_mode.addItems(["Fit the original text", "Always the same size"])
        self.size_mode.setCurrentIndex(0 if style["size_mode"] == "fit" else 1)
        form.addRow("Size", self.size_mode)
        self.scale = QSpinBox()
        self.scale.setRange(50, 250)
        self.scale.setSingleStep(10)
        self.scale.setSuffix(" %")
        self.scale.setValue(int(style["size_scale"]))
        form.addRow("Larger or smaller", self.scale)
        self.font_px = QSpinBox()
        self.font_px.setRange(8, 96)
        self.font_px.setSuffix(" px")
        self.font_px.setValue(int(style["font_px"]))
        form.addRow("Fixed size", self.font_px)

        self.bold = QCheckBox("Bold")
        self.bold.setChecked(bool(style["bold"]))
        form.addRow("", self.bold)
        self.text_color = _ColorChoice(style["text_color"], self._changed, "#FFFFFF")
        form.addRow("Text colour", self.text_color)
        self.background = _ColorChoice(style["background"], self._changed, "#202020")
        form.addRow("Background", self.background)

        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(0, 100)
        self.opacity.setValue(round(style["opacity"] * 100))
        self.opacity.setToolTip("0 % shows only the words, over the original text")
        form.addRow("Background opacity", self.opacity)
        self.radius = QSpinBox()
        self.radius.setRange(0, 20)
        self.radius.setSuffix(" px")
        self.radius.setValue(int(style["radius"]))
        form.addRow("Rounded corners", self.radius)

        reset = QPushButton("Restore the default look")
        reset.clicked.connect(lambda: self.load(DEFAULT_STYLE))
        form.addRow("", reset)

        for signal in (self.font_box.currentFontChanged, self.size_mode.currentIndexChanged, self.scale.valueChanged,
                       self.font_px.valueChanged, self.bold.toggled, self.opacity.valueChanged,
                       self.radius.valueChanged):
            signal.connect(self._changed)
        self._update_enabled()

    def value(self):
        return {
            "font_family": self.font_box.currentFont().family(),
            "size_mode": "fit" if self.size_mode.currentIndex() == 0 else "fixed",
            "size_scale": self.scale.value(),
            "font_px": self.font_px.value(),
            "bold": self.bold.isChecked(),
            "text_color": self.text_color.value(),
            "background": self.background.value(),
            "opacity": self.opacity.value() / 100,
            "radius": self.radius.value(),
        }

    def load(self, style):
        self.font_box.setCurrentFont(QFont(style["font_family"]))
        self.size_mode.setCurrentIndex(0 if style["size_mode"] == "fit" else 1)
        self.scale.setValue(int(style["size_scale"]))
        self.font_px.setValue(int(style["font_px"]))
        self.bold.setChecked(bool(style["bold"]))
        for choice, value in ((self.text_color, style["text_color"]), (self.background, style["background"])):
            choice.mode.setCurrentIndex(0 if value == AUTO else 1)
            if value != AUTO:
                choice.button.set_color(value)
        self.opacity.setValue(round(style["opacity"] * 100))
        self.radius.setValue(int(style["radius"]))
        self._changed()

    def _update_enabled(self):
        fit = self.size_mode.currentIndex() == 0
        self.scale.setEnabled(fit)
        self.font_px.setEnabled(not fit)

    def _changed(self, *_):
        self._update_enabled()
        self.changed.emit(self.value())
