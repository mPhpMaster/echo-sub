# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""The Text & Colors tab: fonts, colours, and the language labels beside each line."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox, QFontComboBox, QFormLayout, QGroupBox, QLabel, QSlider, QVBoxLayout, QWidget,
)

from . import config
from .settings_widgets import ColorButton, make_searchable


class TextTabMixin:
    """Builds the tab; the small helpers (_spin, _row, _combo, _label_size) live on the dialog."""

    def _text_tab(self, cfg):
        w = QWidget()
        v = QVBoxLayout(w)

        g = QGroupBox("General")
        f = QFormLayout(g)
        self.font_family = QFontComboBox()
        self.font_family.setCurrentFont(QFont(cfg["font_family"]))
        make_searchable(self.font_family)
        self.show_original = QCheckBox("Show original text above the translation")
        self.show_original.setChecked(cfg["show_original"])
        self.show_partial = QCheckBox("Show text while speaking (before the sentence ends)")
        self.show_partial.setChecked(cfg["show_partial"])
        self.copy_buttons = QCheckBox("Show a copy button on each caption while the mouse is over the box")
        self.copy_buttons.setToolTip("Click the button next to a caption to copy that text to the clipboard.")
        self.copy_buttons.setChecked(cfg.get("copy_buttons", True))
        f.addRow("Font:", self.font_family)
        f.addRow(self.show_original)
        f.addRow(self.show_partial)
        f.addRow(self.copy_buttons)
        v.addWidget(g)

        g = QGroupBox("Translation")
        f = QFormLayout(g)
        self.font_size = self._spin(8, 96, cfg["font_size"], " pt")
        self.text_color = ColorButton(cfg["text_color"])
        self.translation_bold = QCheckBox("Bold")
        self.translation_bold.setChecked(cfg["translation_bold"])
        f.addRow("Font size:", self._row(self.font_size, self.translation_bold))
        f.addRow("Color:", self.text_color)
        self.translation_label = self._combo(config.ORIGINAL_LABELS, cfg["translation_label"])
        self.translation_label_position = self._combo(config.LABEL_POSITIONS, cfg["translation_label_position"])
        self.translation_label_size = self._label_size(cfg.get("translation_label_size", 100))
        f.addRow("Language label:", self._row(self.translation_label, self.translation_label_position,
                                              self.translation_label_size))
        v.addWidget(g)

        g = QGroupBox("Original text")
        f = QFormLayout(g)
        self.original_font_size = self._spin(8, 96, cfg["original_font_size"], " pt")
        self.original_color = ColorButton(cfg["original_color"])
        self.original_bold = QCheckBox("Bold")
        self.original_bold.setChecked(cfg["original_bold"])
        f.addRow("Font size:", self._row(self.original_font_size, self.original_bold))
        f.addRow("Color:", self.original_color)
        self.original_label = self._combo(config.ORIGINAL_LABELS, cfg["original_label"])
        self.label_position = self._combo(config.LABEL_POSITIONS, cfg["original_label_position"])
        self.original_label_size = self._label_size(cfg.get("original_label_size", 100))
        f.addRow("Language label:", self._row(self.original_label, self.label_position,
                                              self.original_label_size))
        v.addWidget(g)

        self.label_separator = QCheckBox("Put a dot between the language label and the text (·)")
        self.label_separator.setChecked(cfg.get("label_separator", True))
        self.label_separator.setToolTip("So the language name is not read as the first word of the caption")
        v.addWidget(self.label_separator)

        g = QGroupBox("Spacing && background")
        f = QFormLayout(g)
        self.line_height = self._spin(80, 250, cfg["line_height"], " %")
        self.line_height.setSingleStep(5)
        self.entry_spacing = self._spin(0, 80, cfg["entry_spacing"], " px")
        self.original_gap = self._spin(0, 60, cfg["original_gap"], " px")
        self.bg_opacity = QSlider(Qt.Horizontal)
        self.bg_opacity.setRange(0, 255)
        self.bg_opacity.setMinimumWidth(220)
        self.bg_opacity.setValue(cfg["bg_opacity"])
        self.max_lines = self._spin(1, 8, cfg["max_lines"])
        self.clear_after = self._spin(0, 120, cfg["clear_after_sec"], " s")
        self.clear_after.setSpecialValueText("Never")
        f.addRow("Line height (within text):", self.line_height)
        f.addRow("Space between caption lines:", self.entry_spacing)
        f.addRow("Space between original and translation:", self.original_gap)
        f.addRow("Lines shown:", self.max_lines)
        opacity_value = QLabel()
        opacity_value.setMinimumWidth(52)

        def show_opacity(value):
            opacity_value.setText(f"{round(value / 255 * 100)} %")

        self.bg_opacity.valueChanged.connect(show_opacity)
        show_opacity(self.bg_opacity.value())
        f.addRow("Background opacity:", self._row(self.bg_opacity, opacity_value))
        f.addRow("Hide window after silence of:", self.clear_after)
        v.addWidget(g)
        return w
