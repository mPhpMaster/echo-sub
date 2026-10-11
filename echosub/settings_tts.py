# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""The Read aloud tab: speaking finished captions with a Windows voice."""
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from . import tts

SAMPLE = {"ar": "هذا مثال على الصوت الذي سيقرأ الترجمة.", "en": "This is how the captions will sound."}


class SpeechTabMixin:
    """Settings for reading captions aloud, kept out of the main Settings file."""

    def _speech_tab(self, cfg):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        group = QGroupBox("Read the captions aloud")
        form = QFormLayout(group)
        self.tts_enabled = QCheckBox("Read each finished caption aloud with a Windows voice")
        self.tts_enabled.setChecked(cfg.get("tts_enabled", False))
        form.addRow(self.tts_enabled)
        note = QLabel("It speaks on this PC, offline. While it speaks, EchoSub ignores what the PC plays, so it "
                      "never captions its own voice — your microphone still counts.")
        note.setWordWrap(True)
        note.setStyleSheet("color: gray;")
        form.addRow(note)

        self.tts_what = QComboBox()
        self.tts_what.addItem("the translation", "translation")
        self.tts_what.addItem("the original words", "original")
        self.tts_what.setCurrentIndex(max(0, self.tts_what.findData(cfg.get("tts_what", "translation"))))
        self.tts_who = QComboBox()
        self.tts_who.addItem("other people, not me", "others")
        self.tts_who.addItem("everyone, me too", "everyone")
        self.tts_who.setCurrentIndex(max(0, self.tts_who.findData(cfg.get("tts_who", "others"))))
        what_row = QHBoxLayout()
        what_row.addWidget(self.tts_what)
        what_row.addWidget(QLabel("of"))
        what_row.addWidget(self.tts_who)
        what_row.addStretch(1)
        form.addRow("Read:", what_row)

        self.tts_voice = QComboBox()
        self.tts_voice.addItem("Automatic: a voice in the caption's language", "")
        self._tts_voices = tts.list_voices()
        for voice in self._tts_voices:
            self.tts_voice.addItem(voice["name"], voice["name"])
        self.tts_voice.setCurrentIndex(max(0, self.tts_voice.findData(cfg.get("tts_voice", ""))))
        form.addRow("Voice:", self.tts_voice)
        if not self._tts_voices:
            missing = QLabel("No Windows voices were found. Add one in Windows Settings → Time & language → Speech.")
            missing.setWordWrap(True)
            missing.setStyleSheet("color: #D4A03C;")
            form.addRow(missing)

        self.tts_rate = QSpinBox()
        self.tts_rate.setRange(-10, 10)
        self.tts_rate.setPrefix("speed ")
        self.tts_rate.setValue(int(cfg.get("tts_rate", 0)))
        self.tts_volume = QSpinBox()
        self.tts_volume.setRange(0, 100)
        self.tts_volume.setPrefix("volume ")
        self.tts_volume.setSuffix(" %")
        self.tts_volume.setValue(int(cfg.get("tts_volume", 100)))
        try_it = QPushButton("Try it")
        try_it.clicked.connect(self._try_voice)
        sound_row = QHBoxLayout()
        for item in (self.tts_rate, self.tts_volume, try_it):
            sound_row.addWidget(item)
        sound_row.addStretch(1)
        form.addRow("Sound:", sound_row)

        fields = (self.tts_what, self.tts_who, self.tts_voice, self.tts_rate, self.tts_volume)
        for field in fields:
            self.tts_enabled.toggled.connect(field.setEnabled)
            field.setEnabled(self.tts_enabled.isChecked())
        layout.addWidget(group)
        layout.addStretch(1)
        return widget

    def _try_voice(self):
        values = self.tts_values()
        lang = self.target.currentData() if hasattr(self, "target") else "en"
        if self.tts_voice.currentData():
            chosen = next((v for v in self._tts_voices if v["name"] == self.tts_voice.currentData()), None)
            lang = next((code for code, number in tts.PRIMARY_LANGUAGE.items()
                         if chosen and number in chosen["languages"]), lang)
        if getattr(self, "_tts_sample", None) is None:
            self._tts_sample = tts.Speaker(lambda: values)
        self._tts_sample.settings = lambda: values
        self._tts_sample.say(SAMPLE.get(lang, SAMPLE["en"]), lang)

    def tts_values(self):
        return {"tts_enabled": self.tts_enabled.isChecked(), "tts_what": self.tts_what.currentData(),
                "tts_who": self.tts_who.currentData(), "tts_voice": self.tts_voice.currentData(),
                "tts_rate": self.tts_rate.value(), "tts_volume": self.tts_volume.value()}
