# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Wiring the spoken commands into the tray app.

Only finished captions are considered — never live text, which is a guess — and only while the
feature is switched on and the engine is not paused. The list of commands lives in
`voice_commands.py`; this file only connects it to the app's own buttons.
"""
import itertools
import logging
import time

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QSystemTrayIcon

from PySide6.QtCore import QTimer

from . import APP_NAME, screen_replies, voice_commands

log = logging.getLogger("echosub")

UNKNOWN_COMMAND_COOLDOWN_SEC = 5  # one "not a command" message at a time, not one per caption


class VoiceCommandMixin:
    """Adds 'Voice commands' to the tray menu and acts on commands heard in captions."""

    _unknown_command_at = 0.0
    _reply_ids = itertools.count(20_000_000)  # far from the engine's caption numbers

    def _make_voice_command_action(self, menu):
        self.act_voice = QAction("Voice commands", menu, checkable=True,
                                 checked=self.cfg.get("voice_commands", False))
        self.act_voice.setToolTip(f'Say "{self._wake_word()}" and then, for example, "open calculator".')
        self.act_voice.toggled.connect(self._set_voice_commands)
        return self.act_voice

    def _wake_word(self):
        """The first wake word, for messages and tooltips."""
        return self._wake_words()[0]

    def _wake_words(self):
        """Every wake word the user set. Several can be listed, separated by commas, so the same
        name can be written the way each language spells it ("mama, ماما")."""
        setting = str(self.cfg.get("voice_command_wake") or "")
        words = tuple(word.strip() for word in setting.replace("،", ",").split(",") if word.strip())
        if not words:
            return voice_commands.DEFAULT_WAKE_WORDS
        return words + tuple(w for w in voice_commands.DEFAULT_WAKE_WORDS if w not in words)

    def _set_voice_commands(self, enabled):
        if enabled != self.cfg.get("voice_commands", False):
            self.cfg["voice_commands"] = enabled
            self._save()
        if enabled:
            self.tray.showMessage(APP_NAME, f'Voice commands are on. Say "{self._wake_word()}" and then '
                                            f'"open calculator", "close calculator" or "pause captions".',
                                  QSystemTrayIcon.Information, 5000)

    def _handle_voice_command(self, text, source="system"):
        """Called for every finished caption; returns the command that ran, if any."""
        if not text or getattr(self, "_paused", False):
            return None
        if source == "mic" and not self.cfg.get("mic_commands", True):
            return None  # the user asked for their own voice to be captioned, not obeyed
        pairs = self._reply_pairs()
        if not self.cfg.get("voice_commands", False):
            # An on-screen answer writes your own line in your own caption box and can do nothing
            # else, so it stands on its own switch and does not wait for the command one.
            return self._only_an_answer(text, pairs)
        command, heard = voice_commands.find_detail(
            text,
            self._wake_words(),
            self.cfg.get("voice_custom_commands", []),
            self.cfg.get("voice_key_presses", False),
            pairs,
        )
        if command is None:
            self._report_unknown_command(heard)
            return None
        if command["action"] == "help":
            self.tray.showMessage(APP_NAME, voice_commands.help_text(self.cfg.get("voice_custom_commands", [])),
                                  QSystemTrayIcon.Information, 8000)
            return command
        if self._voice_runner is None:
            self._voice_runner = voice_commands.CommandRunner(app_action=self._run_app_command)
        try:
            message = self._voice_runner.run(command)
        except Exception as e:
            log.exception("Voice command failed")
            self.tray.showMessage(APP_NAME, f"Could not run that command: {e}", QSystemTrayIcon.Warning, 4000)
            return None
        if command.get("action") == "reply":
            self._show_screen_reply(command["target"])
            return command
        if message:
            self.tray.showMessage(APP_NAME, message, QSystemTrayIcon.Information, 2500)
        return command

    def _only_an_answer(self, text, pairs):
        """With spoken commands switched off, one of your own phrases may still be answered."""
        if not pairs:
            return None
        reply = screen_replies.find_reply(voice_commands.normalize(text), pairs, voice_commands.position_of)
        if reply is None:
            return None
        command = screen_replies.reply_command(reply)
        if self._voice_runner is None:
            self._voice_runner = voice_commands.CommandRunner(app_action=self._run_app_command)
        if self._voice_runner.run(command) is None:
            return None  # the same phrase again a moment later
        self._show_screen_reply(command["target"])
        return command

    def _reply_pairs(self):
        """The phrase/answer pairs, only while the feature is on."""
        if not self.cfg.get("screen_replies", False):
            return ()
        return screen_replies.valid_pairs(self.cfg.get("screen_reply_pairs", []))

    def _show_screen_reply(self, text):
        """Write one of your prepared answers in the caption box, and take it away again."""
        answer_id = next(self._reply_ids)
        self.overlay.add_final(answer_id, text, text, self.cfg.get("target_lang", "en"), None, "reply")
        seconds = max(2, min(60, int(self.cfg.get("screen_reply_seconds", screen_replies.DEFAULT_SECONDS))))
        QTimer.singleShot(seconds * 1000, lambda: self.overlay.remove_caption(answer_id))

    def _report_unknown_command(self, heard):
        """Say so when the wake word was heard but the rest was not a command."""
        if not heard:
            return
        now = time.monotonic()
        if now - self._unknown_command_at < UNKNOWN_COMMAND_COOLDOWN_SEC:
            return
        self._unknown_command_at = now
        self.tray.showMessage(APP_NAME, f'Not a command: "{heard}"\nTry "open calculator" or "pause captions".',
                              QSystemTrayIcon.Information, 4000)

    def _run_app_command(self, target):
        """EchoSub's own controls, through the same actions as the menu entries."""
        actions = {
            "toggle": lambda: self.act_pause.setChecked(not self.act_pause.isChecked()),
            "pause": lambda: self.act_pause.setChecked(True),
            "resume": lambda: self.act_pause.setChecked(False),
            "hide": lambda: self.act_show.setChecked(False),
            "show": lambda: self.act_show.setChecked(True),
            "clear": self.overlay.clear,
        }
        action = actions.get(target)
        if action is None:
            log.warning("Refused an unknown app command: %r", target)
            return False
        action()
        return True
