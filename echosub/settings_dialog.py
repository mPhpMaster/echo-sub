# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
import re

import shiboken6
from PySide6.QtCore import QEvent, QObject, QSize, QStringListModel, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QColorDialog, QComboBox, QCompleter, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFontComboBox, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QSlider,
    QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from . import APP_NAME, audio, config, history, hotkeys, languages


def _sorted_languages():
    return sorted(languages.LANGUAGES, key=languages.name)


# Extra text an item can be found by (e.g. a language's Arabic name) without showing it
SEARCH_ALIAS_ROLE = Qt.UserRole + 1


class SearchableComboBox(QComboBox):
    """Dropdown you can type into: the list filters to items containing the typed text."""

    def __init__(self, parent=None):
        super().__init__(parent)
        make_searchable(self)


_ARABIC_DIACRITICS = re.compile("[\u064B-\u0652\u0670\u0640]")  # harakat, dagger alif, tatweel
_ARABIC_LETTERS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي", "ؤ": "و", "ئ": "ي"})


def normalize_search(text):
    """Case-, hamza- and diacritic-insensitive form, so "ايطال" matches "الإيطالية"."""
    return _ARABIC_DIACRITICS.sub("", text.casefold()).translate(_ARABIC_LETTERS)


def make_searchable(combo):
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.NoInsert)
    edit = combo.lineEdit()
    edit.setPlaceholderText("Type to search…")

    # Our own match list instead of QCompleter's filtering, which can't ignore hamza/diacritics
    matches = QStringListModel(edit)
    completer = QCompleter(matches, edit)
    completer.setCompletionMode(QCompleter.UnfilteredPopupCompletion)
    edit.setCompleter(completer)

    def update_matches(text):
        needle = normalize_search(text.strip())
        items = []
        for i in range(combo.count()):
            label = combo.itemText(i)
            haystack = normalize_search(f"{label} {combo.itemData(i, SEARCH_ALIAS_ROLE) or ''}")
            if needle in haystack:
                items.append(label)
        matches.setStringList(items)
        if matches.rowCount():
            completer.complete()
        else:
            completer.popup().hide()

    def choose(text):
        index = combo.findText(text, Qt.MatchExactly)
        if index >= 0:
            combo.setCurrentIndex(index)

    def restore_text():
        # Typed text that isn't an item -> fall back to the selected item
        if not shiboken6.isValid(edit) or not shiboken6.isValid(combo):
            return  # fired while the dialog is being destroyed
        if combo.findText(edit.text(), Qt.MatchExactly) < 0:
            edit.setText(combo.itemText(combo.currentIndex()))  # currentText() would echo the typed text

    edit.textEdited.connect(update_matches)
    completer.activated[str].connect(choose)
    edit.editingFinished.connect(restore_text)
    edit.installEventFilter(_SelectAllOnFocus(edit))


class _SelectAllOnFocus(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.FocusIn:
            QTimer.singleShot(0, obj.selectAll)  # typing replaces the current value right away
        return False


def position_icon(row, col):
    """A tiny screen with the caption box drawn where this preset puts it."""
    w, h = 28, 18
    pm = QPixmap(w, h)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QColor("#9E9E9E"))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(1, 1, w - 2, h - 2, 3, 3)
    bw, bh = 12, 4
    x = {"left": 4, "center": (w - bw) // 2, "right": w - bw - 4}[col]
    y = {"top": 4, "middle": (h - bh) // 2, "bottom": h - bh - 4}[row]
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#E0E0E0"))
    p.drawRoundedRect(x, y, bw, bh, 1.5, 1.5)
    p.end()
    return QIcon(pm)


class ColorButton(QPushButton):
    changed = Signal()

    def __init__(self, color, text=True):
        super().__init__()
        self.show_text = text
        self.setMinimumWidth(36)
        self.set_color(color)
        self.clicked.connect(self._pick)

    def set_color(self, color):
        self.color = color
        self.setText(color.upper() if self.show_text else "")
        fg = "#000" if QColor(color).lightness() > 128 else "#fff"
        self.setStyleSheet(f"background:{color}; color:{fg}; border:1px solid #666; padding:4px;")

    def _pick(self):
        c = QColorDialog.getColor(QColor(self.color), self)
        if c.isValid():
            self.set_color(c.name())
            self.changed.emit()


class SettingsDialog(QDialog):
    preview = Signal(dict)  # emitted on every change so the overlay can show it live

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.restore_requested = False
        self.setWindowTitle(f"{APP_NAME} Settings")
        # Above every other window, including the always-on-top caption box
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setMinimumWidth(560)
        root = QVBoxLayout(self)
        tabs = QTabWidget()
        root.addWidget(tabs)

        tabs.addTab(self._language_tab(cfg), "Language && Engine")
        tabs.addTab(self._text_tab(cfg), "Text && Colors")
        tabs.addTab(self._layout_tab(cfg), "Position && Alignment")
        tabs.addTab(self._speakers_tab(cfg), "Speakers")
        tabs.addTab(self._advanced_tab(cfg), "Advanced")

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel | QDialogButtonBox.RestoreDefaults)
        buttons.button(QDialogButtonBox.Save).setText("Save")
        buttons.button(QDialogButtonBox.Cancel).setText("Cancel")
        buttons.button(QDialogButtonBox.RestoreDefaults).setText("Restore defaults")
        buttons.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self._restore_defaults)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self._connect_preview()

    # ---- tabs --------------------------------------------------------------
    def _language_tab(self, cfg):
        w = QWidget()
        f = QFormLayout(w)
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
        f.addRow("Speech recognition model:", self.model)
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
        f.addRow("Font:", self.font_family)
        f.addRow(self.show_original)
        f.addRow(self.show_partial)
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
        self.bg_opacity.setValue(cfg["bg_opacity"])
        self.max_lines = self._spin(1, 8, cfg["max_lines"])
        self.clear_after = self._spin(0, 120, cfg["clear_after_sec"], " s")
        self.clear_after.setSpecialValueText("Never")
        f.addRow("Line height (within text):", self.line_height)
        f.addRow("Space between caption lines:", self.entry_spacing)
        f.addRow("Space between original and translation:", self.original_gap)
        f.addRow("Lines shown:", self.max_lines)
        f.addRow("Background opacity:", self.bg_opacity)
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
        self.box_width = self._spin(20, 100, cfg["box_width_pct"], " % of screen width")
        f.addRow("Box width:", self.box_width)
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

    def _advanced_tab(self, cfg):
        w = QWidget()
        f = QFormLayout(w)
        self.vad = QDoubleSpinBox()
        self.vad.setRange(0.1, 0.9)
        self.vad.setSingleStep(0.05)
        self.vad.setValue(cfg["vad_threshold"])
        self.silence = QDoubleSpinBox()
        self.silence.setRange(0.2, 3.0)
        self.silence.setSingleStep(0.1)
        self.silence.setSuffix(" s")
        self.silence.setValue(cfg["silence_sec"])
        self.max_seg = QDoubleSpinBox()
        self.max_seg.setRange(3.0, 28.0)
        self.max_seg.setSuffix(" s")
        self.max_seg.setValue(cfg["max_segment_sec"])
        f.addRow("Speech detection threshold (lower = more sensitive):", self.vad)
        f.addRow("Silence that ends a sentence:", self.silence)
        f.addRow("Maximum sentence length:", self.max_seg)

        self.save_transcripts = QCheckBox("Save every caption to a transcript file")
        self.save_transcripts.setChecked(cfg["save_transcripts"])
        open_folder = QPushButton("Open transcripts folder")
        open_folder.clicked.connect(history.open_transcripts_folder)
        f.addRow(self._row(self.save_transcripts, open_folder))

        keys = ", ".join(f"{hotkeys.label(k)} {what}" for k, what in
                         (("toggle_captions", "show/hide"), ("pause", "pause"), ("lock", "lock")))
        self.global_hotkeys = QCheckBox(f"Global hotkeys: {keys}")
        self.global_hotkeys.setChecked(cfg["global_hotkeys"])
        f.addRow(self.global_hotkeys)
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
        emit = lambda *_: self.preview.emit(self.values())
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
            "translator": self.translator.currentData(),
            "device": self.device.currentData(),
            "audio_device": self.audio_dev.currentData(),
            "font_family": self.font_family.currentFont().family(),
            "show_original": self.show_original.isChecked(),
            "show_partial": self.show_partial.isChecked(),
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
            "save_transcripts": self.save_transcripts.isChecked(),
            "global_hotkeys": self.global_hotkeys.isChecked(),
        }
