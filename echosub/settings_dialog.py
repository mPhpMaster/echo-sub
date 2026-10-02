# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFontComboBox, QFormLayout,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QSlider, QSpinBox, QTabWidget,
    QVBoxLayout, QWidget,
)

from . import APP_NAME, audio, config, languages
from .settings_microphone import MicrophoneGroupMixin
from .settings_tabs import NUMBER_WIDTH, AdvancedTabMixin
from .settings_transcript import TranscriptFixesMixin
from .settings_voice_commands import VoiceCommandsTabMixin
from .settings_widgets import (
    SEARCH_ALIAS_ROLE, ColorButton, SearchableComboBox, _scrollable, _sorted_languages, fit_to_screen,
    make_searchable, move_onto_screen, position_icon,
)
from .overlay import SCALE_MAX, SCALE_MIN, SCALE_STEP


class SettingsDialog(VoiceCommandsTabMixin, AdvancedTabMixin, MicrophoneGroupMixin,
                     TranscriptFixesMixin, QDialog):
    preview = Signal(dict)  # emitted on every change so the overlay can show it live

    def __init__(self, cfg, parent=None, add_phrase=None):
        super().__init__(parent)
        self.cfg = cfg
        self.restore_requested = False
        self.setWindowTitle(f"{APP_NAME} Settings")
        # Above every other window, including the always-on-top caption box
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        root = QVBoxLayout(self)
        tabs = QTabWidget()
        root.addWidget(tabs)

        # Each tab scrolls, so on a small screen (or with large Windows text scaling) the window
        # still fits and the Save button at the bottom stays visible.
        tabs.addTab(_scrollable(self._language_tab(cfg)), "Language && Engine")
        tabs.addTab(_scrollable(self._text_tab(cfg)), "Text && Colors")
        tabs.addTab(_scrollable(self._layout_tab(cfg)), "Position && Alignment")
        tabs.addTab(_scrollable(self._speakers_tab(cfg)), "Speakers")
        tabs.addTab(_scrollable(self._words_tab(cfg)), "Words")
        tabs.addTab(_scrollable(self._commands_tab(cfg)), "Commands")
        tabs.addTab(_scrollable(self._advanced_tab(cfg)), "Advanced")

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel | QDialogButtonBox.RestoreDefaults)
        buttons.button(QDialogButtonBox.Save).setText("Save")
        buttons.button(QDialogButtonBox.Cancel).setText("Cancel")
        buttons.button(QDialogButtonBox.RestoreDefaults).setText("Restore defaults")
        buttons.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self._restore_defaults)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        if add_phrase:
            # Opened from the "not a command" notice: start a row for what EchoSub actually heard,
            # on the tab that holds it, so the phrase only needs an action chosen for it.
            self._add_voice_custom_command(add_phrase)
            for index in range(tabs.count()):
                if "Command" in tabs.tabText(index):
                    tabs.setCurrentIndex(index)
        self._connect_preview()
        fit_to_screen(self, 640, 760)

    def showEvent(self, event):
        super().showEvent(event)
        move_onto_screen(self)

    # ---- tabs --------------------------------------------------------------
    def _language_tab(self, cfg):
        w = QWidget()
        outer = QVBoxLayout(w)
        form = QWidget()
        f = QFormLayout(form)
        f.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(form)
        self.target = SearchableComboBox()
        self.source = SearchableComboBox()
        self.source.addItem("Auto-detect (any language)", "auto")
        for code in _sorted_languages():
            for combo in (self.target, self.source):
                combo.addItem(languages.name(code), code)
                combo.setItemData(combo.count() - 1, languages.arabic_name(code), SEARCH_ALIAS_ROLE)
        self._select(self.target, cfg["target_lang"])
        self._select(self.source, cfg["source_lang"])
        f.addRow("Show captions in:", self.target)
        f.addRow("Spoken language:", self.source)

        self.model = SearchableComboBox()
        for k, v in config.WHISPER_MODELS.items():
            self.model.addItem(v, k)
        self._select(self.model, cfg["whisper_model"])
        self.translator = SearchableComboBox()
        for k, v in config.TRANSLATORS.items():
            self.translator.addItem(v, k)
        self._select(self.translator, cfg["translator"])
        self.device = SearchableComboBox()
        self.device.addItem("GPU (CUDA) — faster", "cuda")
        self.device.addItem("CPU", "cpu")
        self._select(self.device, cfg["device"])
        self.audio_dev = SearchableComboBox()
        self.audio_dev.addItem("Default output device (follows speaker changes)", "default")
        try:
            for _, name in audio.list_loopback_devices():
                self.audio_dev.addItem(name.replace(" [Loopback]", ""), name)
        except Exception:
            pass
        self._select(self.audio_dev, cfg["audio_device"])
        self.light_model = SearchableComboBox()
        for key in ("small", "base"):
            self.light_model.addItem(config.WHISPER_MODELS[key], key)
        self._select(self.light_model, cfg.get("light_model", "small"))
        self.light_model.setToolTip("Base is two to six times faster than Small and just as accurate on clear "
                                    "speech; Small holds up better in heavy noise.")
        self.light_mode = QCheckBox("Light mode: faster captions on a busy PC")
        self.light_mode.setToolTip("Uses the Small speech model instead of a large one and turns live "
                                   "text off, so captions appear sooner while a game or another program "
                                   "is using the graphics card. Your own settings are kept and come back "
                                   "when you turn this off.")
        self.light_mode.setChecked(cfg.get("light_mode", False))
        f.addRow("Speech recognition model:", self.model)
        f.addRow(self.light_mode)
        f.addRow("Light mode uses:", self.light_model)
        self.light_mode.toggled.connect(self.light_model.setEnabled)
        self.light_model.setEnabled(self.light_mode.isChecked())
        f.addRow("Translation engine:", self.translator)
        f.addRow("Run on:", self.device)
        f.addRow("Audio source:", self.audio_dev)
        self.translate_same = QCheckBox("Translate even when speech is already in the caption language")
        self.translate_same.setToolTip("Rewrites dialect or casual speech into the standard language, "
                                       "e.g. Egyptian or Gulf Arabic into Modern Standard Arabic.")
        self.translate_same.setChecked(cfg["translate_same_language"])
        f.addRow(self.translate_same)
        self.arabic_diacritics = self._combo(config.ARABIC_DIACRITICS, cfg["arabic_diacritics"])
        self.arabic_diacritics.setToolTip("Adds harakat (fatha, damma, kasra, shadda, sukun, tanween) to Arabic "
                                          "captions. The first use downloads a 70 MB model.")
        f.addRow("Arabic diacritics (تشكيل):", self.arabic_diacritics)
        outer.addWidget(self._microphone_group(cfg))
        outer.addStretch(1)
        return w

    def _words_tab(self, cfg):
        """Spellings EchoSub should use, and words it should tell you about."""
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(self._transcript_fixes_group(cfg))
        layout.addWidget(self._alert_words_group(cfg))
        layout.addStretch(1)
        return w

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
        f.addRow("Language label:", self._row(self.translation_label, self.translation_label_position))
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
        f.addRow("Language label:", self._row(self.original_label, self.label_position))
        v.addWidget(g)

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

    def _layout_tab(self, cfg):
        w = QWidget()
        v = QVBoxLayout(w)

        g = QGroupBox("Text alignment")
        f = QFormLayout(g)
        self.text_align = self._combo(config.TEXT_ALIGNMENTS, cfg["text_align"])
        f.addRow("Align caption text:", self.text_align)
        v.addWidget(g)

        g = QGroupBox("Caption box on screen")
        f = QFormLayout(g)
        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(4)
        self.position_group = QButtonGroup(self)
        for r, row in enumerate(config.BOX_ROWS):
            for c, col in enumerate(config.BOX_COLUMNS):
                b = QPushButton()
                b.setIcon(position_icon(row, col))
                b.setIconSize(QSize(28, 18))
                b.setCheckable(True)
                b.setFixedSize(48, 34)
                b.setToolTip(f"{row.capitalize()} {col}")
                b.setProperty("position", f"{row}-{col}")
                self.position_group.addButton(b)
                grid.addWidget(b, r, c)
        custom = QPushButton("Custom\n(drag the box)")
        custom.setCheckable(True)
        custom.setMinimumHeight(104)
        custom.setProperty("position", "custom")
        self.position_group.addButton(custom)
        grid.addWidget(custom, 0, 3, 3, 1)
        grid.setColumnStretch(4, 1)
        for b in self.position_group.buttons():
            b.setChecked(b.property("position") == cfg["box_position"])
        f.addRow("Position:", grid_widget)

        self.box_screen = SearchableComboBox()
        primary = QGuiApplication.primaryScreen()
        self.box_screen.addItem(f"Primary screen ({primary.name()})", "")
        for screen in QGuiApplication.screens():
            geo = screen.geometry()
            self.box_screen.addItem(f"{screen.name()} ({geo.width()} x {geo.height()})", screen.name())
        self._select(self.box_screen, cfg["box_screen"])
        f.addRow("Screen:", self.box_screen)
        self.box_margin = self._spin(0, 400, cfg["box_margin"], " px")
        f.addRow("Distance from screen edge:", self.box_margin)
        self.box_width = self._spin(20, 100, cfg["box_width_pct"], " %")
        f.addRow("Box width (of the screen):", self.box_width)
        self.box_autosize = QCheckBox("Autosize: shrink and grow the box to fit its text")
        self.box_autosize.setToolTip("The box is only as wide as its longest line and as tall as its lines. "
                                     "The box width above (or the dragged width for Custom) becomes the maximum.")
        self.box_autosize.setChecked(cfg["box_autosize"])
        f.addRow(self.box_autosize)
        hint = QLabel("Presets keep the box attached to that edge or corner, and it grows away from the edge "
                      "as text is added. Dragging the box by hand switches to Custom.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        f.addRow(hint)
        v.addWidget(g)

        g = QGroupBox("Box style")
        f = QFormLayout(g)
        self.box_scale = self._spin(SCALE_MIN, SCALE_MAX, cfg.get("box_scale", 100), " %")
        self.box_scale.setSingleStep(SCALE_STEP)
        self.box_scale.setToolTip("Makes the whole box bigger or smaller: text, labels, spacing, padding, "
                                  "corners and width.\nShortcut: hold Shift and turn the mouse wheel over the box.")
        reset_scale = QPushButton("100%")
        reset_scale.setFixedWidth(52)
        reset_scale.setToolTip("Back to the normal size")
        reset_scale.clicked.connect(lambda: self.box_scale.setValue(100))
        f.addRow("Size (zoom):", self._row(self.box_scale, reset_scale,
                                           QLabel("or hold Shift + mouse wheel over the box")))
        self.box_radius = self._spin(0, 80, cfg["box_radius"], " px")
        self.box_radius.setSpecialValueText("Square corners")
        f.addRow("Corner radius:", self.box_radius)
        self.box_padding_x = self._spin(0, 120, cfg["box_padding_x"], " px")
        self.box_padding_y = self._spin(0, 120, cfg["box_padding_y"], " px")
        f.addRow("Padding:", self._row(QLabel("left/right"), self.box_padding_x,
                                       QLabel("top/bottom"), self.box_padding_y))
        v.addWidget(g)

        g = QGroupBox("Animation")
        f = QFormLayout(g)
        self.caption_animation = self._combo(config.CAPTION_ANIMATIONS, cfg["caption_animation"])
        f.addRow("When captions change:", self.caption_animation)
        self.caption_animation_ms = self._spin(80, 1500, cfg["caption_animation_ms"], " ms")
        self.caption_animation_ms.setSingleStep(50)
        f.addRow("Animation duration:", self.caption_animation_ms)
        self.caption_animation.currentIndexChanged.connect(
            lambda *_: self.caption_animation_ms.setEnabled(self.caption_animation.currentData() != "none"))
        self.caption_animation_ms.setEnabled(cfg["caption_animation"] != "none")
        v.addWidget(g)
        v.addStretch(1)

        self.position_group.buttonToggled.connect(lambda *_: self._update_position_controls())
        self._update_position_controls()
        return w

    def _box_position(self):
        checked = self.position_group.checkedButton()
        return checked.property("position") if checked else "custom"

    def sync_placement(self, cfg):
        """Called when the user drags or resizes the caption box while this dialog is open."""
        for b in self.position_group.buttons():
            if b.property("position") == cfg["box_position"]:
                b.setChecked(True)
        self._select(self.box_screen, cfg["box_screen"])
        self.box_width.setValue(cfg["box_width_pct"])
        self.box_scale.setValue(cfg.get("box_scale", 100))

    def _update_position_controls(self):
        preset = self._box_position() != "custom"
        self.box_margin.setEnabled(preset)
        self.box_width.setEnabled(preset)
        self.box_autosize.setText("Autosize: shrink and grow the box to fit its text"
                                  + (" (up to the box width)" if preset else " (up to the dragged width)"))

    def _speakers_tab(self, cfg):
        w = QWidget()
        f = QFormLayout(w)
        self.speaker_detection = QCheckBox("Detect speakers: new line and a different color for each person")
        self.speaker_detection.setChecked(cfg["speaker_detection"])
        f.addRow(self.speaker_detection)
        self.speaker_target = SearchableComboBox()
        for k, label in config.SPEAKER_COLOR_TARGETS.items():
            self.speaker_target.addItem(label, k)
        self._select(self.speaker_target, cfg["speaker_color_target"])
        f.addRow("Apply speaker color to:", self.speaker_target)

        palette = QWidget()
        grid = QHBoxLayout(palette)
        grid.setContentsMargins(0, 0, 0, 0)
        self.speaker_buttons = []
        for i, color in enumerate(cfg["speaker_colors"]):
            col = QVBoxLayout()
            b = ColorButton(color, text=False)
            b.setFixedSize(40, 28)
            lbl = QLabel(str(i + 1))
            lbl.setAlignment(Qt.AlignCenter)
            col.addWidget(b)
            col.addWidget(lbl)
            grid.addLayout(col)
            self.speaker_buttons.append(b)
        f.addRow("Speaker colors:", palette)

        self.speaker_threshold = QDoubleSpinBox()
        self.speaker_threshold.setMaximumWidth(NUMBER_WIDTH)
        self.speaker_threshold.setRange(0.3, 0.85)
        self.speaker_threshold.setSingleStep(0.05)
        self.speaker_threshold.setValue(cfg["speaker_threshold"])
        f.addRow("Matching strictness:", self.speaker_threshold)
        hint = QLabel("Raise it if two people end up sharing one color; "
                      "lower it if the same person gets more than one color.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        f.addRow(hint)
        return w

    def _restore_defaults(self):
        answer = QMessageBox.question(
            self, "Restore defaults",
            "Reset all settings to their defaults? The caption window keeps its position.")
        if answer == QMessageBox.Yes:
            self.restore_requested = True
            self.accept()

    # ---- helpers -----------------------------------------------------------
    def _combo(self, options, value):
        combo = SearchableComboBox()
        for key, label in options.items():
            combo.addItem(label, key)
        self._select(combo, value)
        return combo

    @staticmethod
    def _spin(lo, hi, value, suffix=""):
        s = QSpinBox()
        s.setRange(lo, hi)
        s.setValue(value)
        if suffix:
            s.setSuffix(suffix)
        s.setMaximumWidth(NUMBER_WIDTH)
        return s

    @staticmethod
    def _row(*widgets):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        for x in widgets:
            h.addWidget(x)
        h.addStretch(1)
        return w

    @staticmethod
    def _select(combo, value):
        i = combo.findData(value)
        if i >= 0:
            combo.setCurrentIndex(i)

    def _connect_preview(self):
        def emit(*_):
            self.preview.emit(self.values())

        for child in self.findChildren(QWidget):
            if isinstance(child, ColorButton):
                child.changed.connect(emit)
            elif isinstance(child, (QSpinBox, QDoubleSpinBox, QSlider)):
                child.valueChanged.connect(emit)
            elif isinstance(child, QCheckBox):
                child.toggled.connect(emit)
            elif isinstance(child, QPushButton) and child.property("position") is not None:
                child.toggled.connect(emit)
            elif isinstance(child, QFontComboBox):
                child.currentFontChanged.connect(emit)
            elif isinstance(child, QComboBox):
                child.currentIndexChanged.connect(emit)

    def values(self):
        return {
            "target_lang": self.target.currentData(),
            "source_lang": self.source.currentData(),
            "whisper_model": self.model.currentData(),
            "light_mode": self.light_mode.isChecked(),
            "light_model": self.light_model.currentData(),
            **self._microphone_values(),
            "translator": self.translator.currentData(),
            "device": self.device.currentData(),
            "audio_device": self.audio_dev.currentData(),
            "font_family": self.font_family.currentFont().family(),
            "show_original": self.show_original.isChecked(),
            "show_partial": self.show_partial.isChecked(),
            "copy_buttons": self.copy_buttons.isChecked(),
            "font_size": self.font_size.value(),
            "text_color": self.text_color.color,
            "translation_bold": self.translation_bold.isChecked(),
            "translation_label": self.translation_label.currentData(),
            "translation_label_position": self.translation_label_position.currentData(),
            "translate_same_language": self.translate_same.isChecked(),
            "arabic_diacritics": self.arabic_diacritics.currentData(),
            "original_font_size": self.original_font_size.value(),
            "original_color": self.original_color.color,
            "original_bold": self.original_bold.isChecked(),
            "original_label": self.original_label.currentData(),
            "original_label_position": self.label_position.currentData(),
            "text_align": self.text_align.currentData(),
            "box_position": self._box_position(),
            "box_screen": self.box_screen.currentData(),
            "box_margin": self.box_margin.value(),
            "box_width_pct": self.box_width.value(),
            "box_autosize": self.box_autosize.isChecked(),
            "box_radius": self.box_radius.value(),
            "box_padding_x": self.box_padding_x.value(),
            "box_padding_y": self.box_padding_y.value(),
            "box_scale": self.box_scale.value(),
            "caption_animation": self.caption_animation.currentData(),
            "caption_animation_ms": self.caption_animation_ms.value(),
            "line_height": self.line_height.value(),
            "entry_spacing": self.entry_spacing.value(),
            "original_gap": self.original_gap.value(),
            "max_lines": self.max_lines.value(),
            "bg_opacity": self.bg_opacity.value(),
            "clear_after_sec": self.clear_after.value(),
            "speaker_detection": self.speaker_detection.isChecked(),
            "speaker_color_target": self.speaker_target.currentData(),
            "speaker_colors": [b.color for b in self.speaker_buttons],
            "speaker_threshold": round(self.speaker_threshold.value(), 2),
            "vad_threshold": round(self.vad.value(), 2),
            "silence_sec": round(self.silence.value(), 2),
            "max_segment_sec": round(self.max_seg.value(), 1),
            "audio_backlog_sec": self.audio_backlog.value() * 60,
            "audio_backlog_dir": self.audio_backlog_dir.text().strip(),
            "save_transcripts": self.save_transcripts.isChecked(),
            "update_checks": self.update_checks.isChecked(),
            **self.voice_command_values(),
            **self.transcript_fix_values(),
            "global_hotkeys": self.global_hotkeys.isChecked(),
        }
