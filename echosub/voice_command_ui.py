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

from . import APP_NAME, reminders, screen_replies, voice_commands
from .command_notice import CommandNotice
from .help_window import HelpWindow
from .missed_window import MissedPhrases, MissedWindow

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

    def heard_a_refusal(self, text):
        """"No" while a command is counting down calls it off. True when that just happened.

        No wake word, and any sound will do: a command that does not run cannot do harm, so this
        is deliberately the easiest thing in the app to trigger. It is also checked on live text,
        so saying "no" stops the countdown without waiting for the sentence to finish.
        """
        notice = getattr(self, "_notice", None)
        if notice is None or not notice.pending() or not text:
            return False
        if not voice_commands.is_cancel(text):
            return False
        notice.cancel()
        self.tray.showMessage(APP_NAME, "Command cancelled", QSystemTrayIcon.Information, 2000)
        log.info("A command was called off by voice")
        return True

    def _handle_voice_command(self, text, source="system"):
        """Called for every finished caption; returns the command that ran, if any."""
        if not text or getattr(self, "_paused", False):
            return None
        if self.heard_a_refusal(text):
            return None
        if source == "mic" and not self.cfg.get("mic_commands", True):
            return None  # the user asked for their own voice to be captioned, not obeyed
        pairs = self._reply_pairs()
        if not self.cfg.get("voice_commands", False):
            # An on-screen answer writes your own line in your own caption box and can do nothing
            # else, so it stands on its own switch and does not wait for the command one.
            return self._only_an_answer(text, pairs)
        # Your own microphone does not wait for the wake word, unless you ask it to.
        needs_wake = source != "mic" or self.cfg.get("mic_wake_word", False)
        command, heard = voice_commands.find_detail(
            text,
            self._wake_words(),
            self.cfg.get("voice_custom_commands", []),
            self.cfg.get("voice_key_presses", False),
            pairs,
            self.cfg.get("voice_go_folders", []),
            needs_wake,
            self.cfg.get("voice_typing", False),
        )
        if command is None:
            self._report_unknown_command(heard)
            return None
        if command.get("mic_only") and source != "mic":
            return None  # your microphone alone may switch your microphone
        if source == "mic" and self.mic_muted() and command["key"] != "toggle_mic":
            return None  # muted: the only thing left that your voice may do is unmute itself
        if command["action"] == "help":
            self.open_help_window()
            return command
        return self._start_command(command)

    def _start_command(self, command):
        """Say on screen what was understood, and carry it out unless the notice is clicked first."""
        seconds = max(0, min(30, int(self.cfg.get("voice_command_delay", 3) or 0)))
        if seconds <= 0 or command.get("action") == "reply":
            return self._run_command(command)  # an answer only writes text; there is nothing to undo
        notice = self._command_notice()
        if notice is None:
            return self._run_command(command)
        notice.start(command.get("label") or command["key"], seconds, lambda: self._run_command(command))
        return command

    def _command_notice(self):
        if getattr(self, "_notice", None) is None:
            try:
                self._notice = CommandNotice()
            except Exception:  # a headless run, or no screen to put it on
                log.exception("Could not show the command notice")
                return None
        return self._notice

    def cancel_pending_command(self):
        """Drop a command that is counting down. Clicking the notice does this too."""
        notice = getattr(self, "_notice", None)
        return bool(notice is not None and notice.cancel())

    def _run_command(self, command):
        """Actually carry out a command, once nobody has cancelled it."""
        if self._voice_runner is None:
            self._voice_runner = voice_commands.CommandRunner(app_action=self._run_app_command)
        try:
            message = self._voice_runner.run(command)
        except Exception as e:
            log.exception("Voice command failed")
            self.tray.showMessage(APP_NAME, f"Could not run that command: {e}", QSystemTrayIcon.Warning, 4000)
            return None
        if command.get("action") == "reminder":
            self._keep_reminder(command)
            return command
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
            self.missed_phrases().add(heard)  # counted even when it is too soon to show a notice
            return
        self._unknown_command_at = now
        self._unknown_phrase = heard
        self.missed_phrases().add(heard)
        self.tray.showMessage(APP_NAME, f'Not a command: "{heard}"\nClick here to make it one.',
                              QSystemTrayIcon.Information, 5000)

    def _notice_clicked(self):
        """Clicking the "not a command" notice offers to turn what was heard into a command.

        The phrase is used once: a later click, with nothing newly misheard, opens nothing.
        """
        phrase = getattr(self, "_unknown_phrase", "")
        self._unknown_phrase = ""
        if phrase:
            self._open_settings(phrase)

    def _keep_reminder(self, command):
        """Write the reminder down, so it survives EchoSub being closed and opened again."""
        kept = list(self.cfg.get("reminders", [])) + [{"when": command["target"],
                                                       "what": command.get("what", "")}]
        self.cfg["reminders"] = reminders.valid(kept)
        self._save()

    def check_reminders(self, now=None):
        """Show any reminder that has come round, and forget it. Returns how many were shown."""
        ready, waiting = reminders.due(self.cfg.get("reminders", []), now)
        if not ready:
            return 0
        self.cfg["reminders"] = waiting
        self._save()
        for entry in ready:
            what = entry["what"] or "Reminder"
            self.tray.showMessage(APP_NAME, "⏰ " + what, QSystemTrayIcon.Information, 15000)
            self._show_screen_reply("⏰ " + what)
        return len(ready)

    def missed_phrases(self):
        if getattr(self, "_missed", None) is None:
            self._missed = MissedPhrases()
        return self._missed

    def open_missed_window(self, *_args):
        """What was heard after the wake word but not understood, and how often."""
        existing = getattr(self, "_missed_window", None)
        if existing is not None and existing.isVisible():
            existing.raise_()
            existing.activateWindow()
            return existing
        self._missed_window = MissedWindow(self.missed_phrases(), self.cfg, self._open_settings)
        self._missed_window.finished.connect(lambda _r: setattr(self, "_missed_window", None))
        self._missed_window.show()
        self._missed_window.raise_()
        self._missed_window.activateWindow()
        return self._missed_window

    def open_help_window(self):
        """Show everything that can be said, in English and in the language being translated into."""
        existing = getattr(self, "_help_window", None)
        if existing is not None and existing.isVisible():
            existing.raise_()
            existing.activateWindow()
            return existing
        translator = getattr(self.engine, "translator", None) if getattr(self, "engine", None) else None
        self._help_window = HelpWindow(self.cfg, translator)
        self._help_window.finished.connect(lambda _result: setattr(self, "_help_window", None))
        self._help_window.show()
        self._help_window.raise_()
        self._help_window.activateWindow()
        return self._help_window

    def mic_muted(self):
        return bool(getattr(self, "_mic_muted", False))

    def set_mic_muted(self, muted):
        """Stop showing and obeying your own microphone, or start again.

        The microphone keeps being listened to while muted, because otherwise nothing could hear
        you ask for it back. Nothing it says is shown, written down, or acted on, apart from that
        one phrase. To stop listening to it altogether, switch the microphone off in the settings.
        """
        self._mic_muted = bool(muted)
        if getattr(self, "act_mic_mute", None) is not None and self.act_mic_mute.isChecked() != self._mic_muted:
            self.act_mic_mute.setChecked(self._mic_muted)
        self.overlay.set_partial("", None, self.cfg.get("target_lang", "en"), "mic")
        self.tray.showMessage(APP_NAME,
                              "Your microphone is muted — say it again to bring it back"
                              if self._mic_muted else "Your microphone is back",
                              QSystemTrayIcon.Information, 2500)

    def _run_app_command(self, target):
        """EchoSub's own controls, through the same actions as the menu entries."""
        actions = {
            "toggle": lambda: self.act_pause.setChecked(not self.act_pause.isChecked()),
            "mic": lambda: self.set_mic_muted(not self.mic_muted()),
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
