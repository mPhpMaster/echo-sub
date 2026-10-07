# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""The AI tab: which service answers "ask ...", with which model and key, and how much it is told.

Each service keeps its own model, address and key, so switching from Claude to LM Studio and back
loses nothing. A key typed here is encrypted for this Windows account before it is stored, and the
box stays empty afterwards: the key is never shown again, only replaced or forgotten.
"""
import collections
import threading

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox,
    QVBoxLayout, QWidget,
)

from . import ai_assistant, ai_providers, secrets_store
from .caption_widgets import AI_COLOR, AI_LABEL
from .settings_widgets import ColorButton

CLOUD_NOTE = (
    "⚠️ When you ask a question, the recent captions set above are sent to {title} along with it. "
    "Those captions can include other people's words from calls and videos, so only switch this on if "
    "that is all right with you and with them. Nothing is sent until you ask, and saying “no” during "
    "the countdown stops it.")
LOCAL_NOTE = ("LM Studio runs on this PC, so your captions and questions never leave it. Start LM Studio's "
              "local server and load a model first.")


class AiTabMixin:
    """Settings for the spoken "ask ..." command."""

    def _ai_tab(self, cfg):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        group = QGroupBox("Ask an AI about what was said")
        form = QFormLayout(group)

        self.ai_enabled = QCheckBox("Answer “ask …” with an AI (off until you switch it on)")
        self.ai_enabled.setChecked(cfg.get("ai_enabled", False))
        form.addRow(self.ai_enabled)
        how = QLabel('Say your wake word and then the word below, for example: "echo sub, ask what was the '
                     'price he said". The answer appears in the caption box, in its own colour, after "AI".')
        how.setWordWrap(True)
        how.setStyleSheet("color: gray;")
        form.addRow(how)

        self.ai_trigger = QLineEdit(cfg.get("ai_trigger", ai_assistant.DEFAULT_TRIGGER))
        self.ai_trigger.setPlaceholderText(ai_assistant.DEFAULT_TRIGGER)
        self.ai_trigger.setToolTip("The word you say after your wake word to ask a question. "
                                   "Several can be listed, separated by commas.")
        self.ai_trigger.setMaximumWidth(280)
        form.addRow("Word that asks:", self.ai_trigger)

        self.ai_color = ColorButton(cfg.get("ai_color", AI_COLOR))
        self.ai_label = QLineEdit(cfg.get("ai_label", AI_LABEL))
        self.ai_label.setPlaceholderText(AI_LABEL)
        self.ai_label.setToolTip("The word shown in front of every answer, so it is never mistaken for "
                                 "something somebody said")
        self.ai_label.setMaximumWidth(140)
        self.ai_font_size = QSpinBox()
        self.ai_font_size.setRange(0, 96)
        self.ai_font_size.setSuffix(" pt")
        self.ai_font_size.setSpecialValueText("same as captions")
        self.ai_font_size.setMaximumWidth(160)
        self.ai_font_size.setValue(int(cfg.get("ai_font_size", 0) or 0))
        look_row = QHBoxLayout()
        look_row.addWidget(QLabel("Word in front:"))
        look_row.addWidget(self.ai_label)
        look_row.addWidget(QLabel("Size:"))
        look_row.addWidget(self.ai_font_size)
        look_row.addWidget(QLabel("Colour:"))
        look_row.addWidget(self.ai_color)
        look_row.addStretch(1)
        form.addRow("Answers look:", look_row)

        self.ai_answer_seconds = QSpinBox()
        self.ai_answer_seconds.setRange(0, ai_assistant.ANSWER_SECONDS_MAX)
        self.ai_answer_seconds.setSuffix(" s")
        self.ai_answer_seconds.setSpecialValueText("long enough to read it")
        self.ai_answer_seconds.setToolTip("How long an answer stays in the caption box. 0 = by its length.")
        self.ai_answer_seconds.setMaximumWidth(200)
        self.ai_answer_seconds.setValue(int(cfg.get("ai_answer_seconds", 0) or 0))
        form.addRow("Answer stays for:", self.ai_answer_seconds)

        self.ai_provider = QComboBox()
        for key, spec in ai_providers.PROVIDERS.items():
            self.ai_provider.addItem(spec["title"], key)
        form.addRow("Service:", self.ai_provider)

        self.ai_model = QComboBox()
        self.ai_model.setEditable(True)
        self.ai_model.setMinimumWidth(260)
        load = QPushButton("Load models")
        load.setToolTip("Ask the service which models it has — this also checks the key and the address")
        load.clicked.connect(self._load_ai_models)
        model_row = QHBoxLayout()
        model_row.addWidget(self.ai_model, 1)
        model_row.addWidget(load)
        form.addRow("Model:", model_row)

        self.ai_base_url = QLineEdit()
        form.addRow("Address:", self.ai_base_url)

        self.ai_key = QLineEdit()
        self.ai_key.setEchoMode(QLineEdit.Password)
        forget = QPushButton("Forget key")
        forget.clicked.connect(self._forget_ai_key)
        self.ai_get_key = QPushButton("Get a key…")
        self.ai_get_key.clicked.connect(self._open_key_page)
        key_row = QHBoxLayout()
        key_row.addWidget(self.ai_key, 1)
        key_row.addWidget(self.ai_get_key)
        key_row.addWidget(forget)
        form.addRow("API key:", key_row)

        self.ai_status = QLabel("")
        self.ai_status.setWordWrap(True)
        form.addRow(self.ai_status)

        self.ai_context_lines = QSpinBox()
        self.ai_context_lines.setRange(0, ai_assistant.MAX_CONTEXT)
        self.ai_context_lines.setSuffix(" captions")
        self.ai_context_lines.setMaximumWidth(150)
        self.ai_context_lines.setValue(int(cfg.get("ai_context_lines", 20)))
        self.ai_context_who = QComboBox()
        self.ai_context_who.addItem("from everyone", "everyone")
        self.ai_context_who.addItem("only what I said", "me")
        self.ai_context_who.setCurrentIndex(max(0, self.ai_context_who.findData(cfg.get("ai_context_who"))))
        context_row = QHBoxLayout()
        context_row.addWidget(self.ai_context_lines)
        context_row.addWidget(self.ai_context_who)
        context_row.addStretch(1)
        form.addRow("Send along:", context_row)

        self.ai_privacy = QLabel()
        self.ai_privacy.setWordWrap(True)
        form.addRow(self.ai_privacy)
        layout.addWidget(group)
        layout.addWidget(self._ai_auto_group(cfg))
        layout.addStretch(1)

        self._ai_profiles = {k: dict(v) for k, v in (cfg.get("ai_profiles") or {}).items()}
        self._ai_shown = None
        self._ai_results = collections.deque()
        self._ai_timer = QTimer(widget)  # dies with the tab, so a late answer never reaches a closed window
        self._ai_timer.timeout.connect(self._drain_ai_results)
        self.ai_provider.currentIndexChanged.connect(lambda _i: self._show_ai_provider())
        self.ai_provider.setCurrentIndex(max(0, self.ai_provider.findData(cfg.get("ai_provider", "claude"))))
        self._show_ai_provider()
        return widget

    def _ai_auto_group(self, cfg):
        """Answering questions nobody asked EchoSub to answer — the same service, a separate switch."""
        group = QGroupBox("Answer questions on its own")
        form = QFormLayout(group)
        self.ai_auto_answer = QCheckBox("When someone asks a question, show an AI's answer without being asked")
        self.ai_auto_answer.setChecked(cfg.get("ai_auto_answer", False))
        form.addRow(self.ai_auto_answer)
        self.ai_auto_from = QComboBox()
        self.ai_auto_from.addItem("anyone", "everyone")
        self.ai_auto_from.addItem("other people, not me", "others")
        self.ai_auto_from.addItem("only me", "me")
        self.ai_auto_from.setCurrentIndex(max(0, self.ai_auto_from.findData(cfg.get("ai_auto_from"))))
        self.ai_auto_cooldown = QSpinBox()
        self.ai_auto_cooldown.setRange(5, 600)
        self.ai_auto_cooldown.setSuffix(" s")
        self.ai_auto_cooldown.setPrefix("at most one every ")
        self.ai_auto_cooldown.setMaximumWidth(220)
        self.ai_auto_cooldown.setValue(int(cfg.get("ai_auto_cooldown", ai_assistant.AUTO_COOLDOWN)))
        row = QHBoxLayout()
        row.addWidget(self.ai_auto_from)
        row.addWidget(self.ai_auto_cooldown)
        row.addStretch(1)
        form.addRow("Questions from:", row)
        self.ai_auto_solo = QCheckBox("Only when one person is talking — not while several are")
        self.ai_auto_solo.setToolTip("Looks at the last half minute. It tells voices apart with speaker "
                                     "detection (Language & Engine); without it, every other voice counts as one.")
        self.ai_auto_solo.setChecked(cfg.get("ai_auto_solo", True))
        form.addRow(self.ai_auto_solo)
        note = QLabel(
            "⚠️ Unlike “ask …”, this sends without you asking: every question it hears — from a call, "
            "a video or a game — goes to the service above with the recent captions, and with a paid service "
            "each one costs money. A question is a sentence ending in a question mark, at least three words long; "
            "nothing new is sent while an answer is still on its way. LM Studio keeps all of it on this PC and free.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #D4A03C;")
        form.addRow(note)
        self.ai_auto_answer.toggled.connect(self.ai_auto_from.setEnabled)
        for field in (self.ai_auto_from, self.ai_auto_cooldown, self.ai_auto_solo):
            self.ai_auto_answer.toggled.connect(field.setEnabled)
            field.setEnabled(self.ai_auto_answer.isChecked())
        return group

    # ---- one service at a time, each remembered -----------------------------
    def _keep_ai_fields(self):
        """Put what is in the boxes back into the shown service's profile."""
        if self._ai_shown is None:
            return
        saved = self._ai_profiles.setdefault(self._ai_shown, {})
        saved["model"] = self.ai_model.currentText().strip()
        saved["base_url"] = self.ai_base_url.text().strip()
        typed = self.ai_key.text().strip()
        if typed:
            saved["key"] = secrets_store.protect(typed)
            self.ai_key.clear()

    def _show_ai_provider(self):
        self._keep_ai_fields()
        provider = self.ai_provider.currentData()
        spec = ai_providers.PROVIDERS[provider]
        saved = self._ai_profiles.get(provider, {})
        self.ai_model.clear()
        self.ai_model.setEditText(saved.get("model") or spec["model"])
        self.ai_base_url.setText(saved.get("base_url") or spec["base_url"])
        self.ai_base_url.setEnabled(spec["kind"] != "anthropic")
        has_key = bool(saved.get("key"))
        self.ai_key.setEnabled(not spec["local"])
        self.ai_key.setPlaceholderText("not needed" if spec["local"]
                                       else "saved — type to replace" if has_key else "paste your API key")
        self.ai_get_key.setText("Get LM Studio…" if spec["local"] else "Get a key…")
        self.ai_get_key.setToolTip(f"Opens {spec['key_url']} in your browser")
        note = LOCAL_NOTE if spec["local"] else CLOUD_NOTE.format(title=spec["title"])
        self.ai_privacy.setText(note)
        self.ai_privacy.setStyleSheet("color: gray;" if spec["local"] else "color: #D4A03C;")
        self.ai_status.setText("")
        self._ai_shown = provider

    def _open_key_page(self):
        """Open the chosen service's API-key page — or LM Studio's site — in the user's own browser."""
        url = ai_providers.PROVIDERS[self.ai_provider.currentData()]["key_url"]
        QDesktopServices.openUrl(QUrl(url))
        return url

    def _forget_ai_key(self):
        self.ai_key.clear()
        self._ai_profiles.setdefault(self.ai_provider.currentData(), {}).pop("key", None)
        self._show_ai_provider()
        self.ai_status.setText("Key forgotten.")

    # ---- checking the service, without freezing the window ------------------
    def _load_ai_models(self):
        self._keep_ai_fields()
        provider = self.ai_provider.currentData()
        chosen = ai_assistant.profile({"ai_profiles": self._ai_profiles}, provider)
        self.ai_status.setText("Asking the service for its models…")

        def work():
            try:
                models = ai_providers.list_models(provider, chosen["key"], chosen["base_url"])
                self._ai_results.append(("ok", models))
            except ai_providers.AiError as e:
                self._ai_results.append(("error", str(e)))
            except Exception as e:  # a settings window must survive a bad answer
                self._ai_results.append(("error", f"Could not load the models: {e}"))

        self._ai_timer.start(150)
        threading.Thread(target=work, name="ai-models", daemon=True).start()

    def _drain_ai_results(self):
        while self._ai_results:
            kind, value = self._ai_results.popleft()
            self._ai_timer.stop()
            if kind == "error":
                self.ai_status.setText("⚠️ " + value)
                continue
            current = self.ai_model.currentText()
            self.ai_model.clear()
            self.ai_model.addItems(value)
            self.ai_model.setEditText(current if current in value or not value else value[0])
            self.ai_status.setText(f"✔ Connected — {len(value)} models available.")

    def ai_values(self):
        self._keep_ai_fields()
        return {
            "ai_enabled": self.ai_enabled.isChecked(),
            "ai_provider": self.ai_provider.currentData(),
            "ai_profiles": self._ai_profiles,
            "ai_context_lines": self.ai_context_lines.value(),
            "ai_context_who": self.ai_context_who.currentData(),
            "ai_trigger": self.ai_trigger.text().strip() or ai_assistant.DEFAULT_TRIGGER,
            "ai_color": self.ai_color.color,
            "ai_label": self.ai_label.text().strip() or AI_LABEL,
            "ai_font_size": self.ai_font_size.value(),
            "ai_auto_answer": self.ai_auto_answer.isChecked(),
            "ai_auto_from": self.ai_auto_from.currentData(),
            "ai_auto_cooldown": self.ai_auto_cooldown.value(),
            "ai_auto_solo": self.ai_auto_solo.isChecked(),
            "ai_answer_seconds": self.ai_answer_seconds.value(),
        }
