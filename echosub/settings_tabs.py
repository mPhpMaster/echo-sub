# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""The Advanced tab of the Settings window: recognition tuning, the catch-up buffer, transcripts,
update checks, voice commands and hotkeys.

Each group is a box, number fields keep the same narrow width as everywhere else, and every hint
sits on its own wrapped line — a long hint beside a field used to push the window wider than the
screen and hide the start of what was typed.
"""
import os
import tempfile

from PySide6.QtWidgets import (
    QCheckBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox, QLabel, QLineEdit, QPushButton, QSpinBox,
    QVBoxLayout, QWidget,
)

from . import history, hotkeys

NUMBER_WIDTH = 120  # every spin box in the window is this wide, so the rows line up


def number_field(widget, suffix="", tooltip=""):
    widget.setMaximumWidth(NUMBER_WIDTH)
    if suffix:
        widget.setSuffix(suffix)
    if tooltip:
        widget.setToolTip(tooltip)
    return widget


def hint(text):
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet("color: gray;")
    return label


class AdvancedTabMixin:
    """The Advanced tab, kept out of the main Settings file."""

    def _pick_backlog_folder(self):
        start = self.audio_backlog_dir.text().strip() or tempfile.gettempdir()
        folder = QFileDialog.getExistingDirectory(self, "Folder for the catch-up audio buffer", start)
        if folder:
            self._set_backlog_folder(os.path.normpath(folder))

    def _set_backlog_folder(self, path):
        self.audio_backlog_dir.setText(path)
        self.audio_backlog_dir.setToolTip(path or "The Windows temp folder is used")
        self.audio_backlog_dir.setCursorPosition(0)  # show where the path starts, not where it ends

    def _advanced_tab(self, cfg):
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(self._recognition_group(cfg))
        v.addWidget(self._catch_up_group(cfg))
        v.addWidget(self._transcripts_group(cfg))
        v.addWidget(self._hotkeys_group(cfg))
        v.addStretch(1)
        return w

    def _recognition_group(self, cfg):
        group = QGroupBox("Recognition")
        f = QFormLayout(group)
        self.vad = number_field(QDoubleSpinBox())
        self.vad.setRange(0.1, 0.9)
        self.vad.setSingleStep(0.05)
        self.vad.setValue(cfg["vad_threshold"])
        self.silence = number_field(QDoubleSpinBox(), " s")
        self.silence.setRange(0.2, 3.0)
        self.silence.setSingleStep(0.1)
        self.silence.setValue(cfg["silence_sec"])
        self.max_seg = number_field(QDoubleSpinBox(), " s")
        self.max_seg.setRange(3.0, 28.0)
        self.max_seg.setValue(cfg["max_segment_sec"])
        f.addRow("Speech detection threshold:", self.vad)
        f.addRow(hint("Lower hears quieter speech, but also more noise."))
        f.addRow("Silence that ends a sentence:", self.silence)
        f.addRow("Maximum sentence length:", self.max_seg)
        return group

    def _catch_up_group(self, cfg):
        group = QGroupBox("Catch-up audio buffer")
        f = QFormLayout(group)
        self.audio_backlog = number_field(
            QSpinBox(), " min",
            "Keeps delayed audio temporarily on disk so captions can catch up. It does not use extra AI "
            "and does not record your audio permanently.")
        self.audio_backlog.setRange(0, 30)
        self.audio_backlog.setSpecialValueText("Off")
        self.audio_backlog.setValue(round(cfg.get("audio_backlog_sec", 600) / 60))
        self.audio_backlog_dir = QLineEdit()
        self.audio_backlog_dir.setPlaceholderText("Windows temp folder")
        self.audio_backlog_dir.setMinimumWidth(220)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._pick_backlog_folder)
        default = QPushButton("Default")
        default.clicked.connect(lambda: self._set_backlog_folder(""))
        f.addRow("Keep at most:", self.audio_backlog)
        f.addRow("On this drive:", self._row(self.audio_backlog_dir, browse, default))
        f.addRow(hint("While recognition is behind, the audio still waiting is kept here and used in order, "
                      "then deleted. Put it on a fast drive; leave it empty for the Windows temp folder."))
        self._set_backlog_folder(cfg.get("audio_backlog_dir", ""))
        return group

    def _transcripts_group(self, cfg):
        group = QGroupBox("Transcripts and updates")
        f = QFormLayout(group)
        self.save_transcripts = QCheckBox("Save every caption to a transcript file")
        self.save_transcripts.setChecked(cfg["save_transcripts"])
        open_folder = QPushButton("Open transcripts folder")
        open_folder.clicked.connect(history.open_transcripts_folder)
        f.addRow(self._row(self.save_transcripts, open_folder))
        self.update_checks = QCheckBox("Check for a new EchoSub version once a day")
        self.update_checks.setChecked(cfg.get("update_checks", True))
        f.addRow(self.update_checks)
        f.addRow(hint("EchoSub only tells you about a new version and opens its download page. "
                      "It never downloads or installs anything by itself."))
        return group

    def _hotkeys_group(self, cfg):
        group = QGroupBox("Hotkeys")
        f = QFormLayout(group)
        keys = ", ".join(f"{hotkeys.label(k)} {what}" for k, what in
                         (("toggle_captions", "show/hide"), ("pause", "pause"), ("lock", "lock")))
        self.global_hotkeys = QCheckBox("Global hotkeys")
        self.global_hotkeys.setChecked(cfg["global_hotkeys"])
        f.addRow(self.global_hotkeys)
        f.addRow(hint(keys))
        return group
