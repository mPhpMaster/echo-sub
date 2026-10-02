# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Typing what was said: off by default, shown before it happens, and never pressing Enter itself."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # the shared FakeApp harness
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ECHOSUB_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from echosub import config, voice_commands, voice_typing  # noqa: E402

from test_voice_command_ui import FakeApp  # noqa: E402

app = QApplication.instance() or QApplication([])  # the countdown notice is a real widget

WAKE = ("alexa",)


def typed(said, **options):
    options.setdefault("allow_typing", True)
    return voice_commands.find(said, WAKE, **options)


class TextTest(unittest.TestCase):
    def test_what_follows_is_typed_exactly_as_it_was_said(self):
        found = typed("alexa type Hello there, World!")
        self.assertEqual((found["action"], found["target"]), ("type_text", "Hello there, World!"))

    def test_capitals_and_punctuation_survive(self):
        self.assertEqual(typed("alexa type GG WP :)")["target"], "GG WP :)")

    def test_it_works_in_arabic(self):
        found = typed("alexa اكتب مرحبا بكم")
        self.assertEqual(found["target"], "مرحبا بكم")

    def test_a_command_after_type_is_text_not_a_command(self):
        found = typed("alexa type open the calculator")
        self.assertEqual((found["action"], found["target"]), ("type_text", "open the calculator"))

    def test_type_with_nothing_after_it_types_nothing(self):
        self.assertIsNone(typed("alexa type"))


class SafetyTest(unittest.TestCase):
    def test_it_is_off_until_switched_on(self):
        self.assertFalse(config.DEFAULTS["voice_typing"])
        self.assertIsNone(voice_commands.find("alexa type hello", WAKE), "must need the switch")

    def test_the_pcs_own_sound_still_needs_the_wake_word(self):
        self.assertIsNone(voice_commands.find("type hello there", WAKE, allow_typing=True),
                          "a video saying this must not type on your PC")

    def test_a_new_line_can_never_be_typed(self):
        for raw in ("hello\nworld", "hello\r\nworld", "hello\tworld", "hello\x00world"):
            with self.subTest(raw=raw):
                clean = voice_typing.safe_text(raw)
                self.assertNotIn("\n", clean)
                self.assertNotIn("\r", clean)
                self.assertNotIn("\t", clean)
                self.assertNotIn("\x00", clean)

    def test_very_long_speech_is_capped(self):
        self.assertLessEqual(len(voice_typing.safe_text("word " * 500)), voice_typing.MAX_TYPE_CHARS)

    def test_enter_is_its_own_command(self):
        found = typed("alexa press enter")
        self.assertEqual(found["action"], "press_enter")
        self.assertIsNone(voice_commands.find("alexa press enter", WAKE), "also needs the switch")

    def test_typed_text_never_carries_enter_with_it(self):
        found = typed("alexa type send this and press enter")
        self.assertEqual(found["action"], "type_text", "the whole sentence is text, not two commands")
        self.assertEqual(found["target"], "send this and press enter")


class RunnerTest(unittest.TestCase):
    def test_the_runner_types_and_does_nothing_else(self):
        keys, launched, entered = [], [], []
        runner = voice_commands.CommandRunner(typist=keys.append, launcher=launched.append,
                                              enter_presser=lambda: entered.append(1))
        runner.run(typed("alexa type hello there"), now=0)
        self.assertEqual((keys, launched, entered), (["hello there"], [], []))

    def test_pressing_enter_types_nothing(self):
        keys, entered = [], []
        runner = voice_commands.CommandRunner(typist=keys.append, enter_presser=lambda: entered.append(1))
        runner.run(typed("alexa press enter"), now=0)
        self.assertEqual((keys, entered), ([], [1]))

    def test_a_forged_line_with_a_new_line_in_it_is_refused(self):
        runner = voice_commands.CommandRunner(typist=lambda text: None)
        forged = {"key": "type_text", "action": "type_text", "target": "rm -rf /\n", "label": "x"}
        self.assertIsNone(runner.run(forged, now=0))

    def test_a_forged_empty_line_is_refused(self):
        runner = voice_commands.CommandRunner(typist=lambda text: None)
        self.assertIsNone(runner.run({"key": "type_text", "action": "type_text",
                                      "target": "", "label": "x"}, now=0))


class AppTest(unittest.TestCase):
    def app(self, **overrides):
        overrides.setdefault("voice_command_delay", 3)
        return FakeApp(voice_commands=True, voice_typing=True, **overrides)

    def runner_for(self, app_, keys):
        app_._voice_runner = voice_commands.CommandRunner(app_action=app_._run_app_command, typist=keys.append)
        return app_

    def test_nothing_is_typed_until_the_countdown_ends(self):
        keys = []
        app_ = self.runner_for(self.app(), keys)
        self.assertIsNotNone(app_._handle_voice_command("echo sub type hello there"))
        self.assertEqual(keys, [], "it typed before anyone could stop it")
        app_._notice.fire_now()
        self.assertEqual(keys, ["hello there"])

    def test_the_text_is_shown_in_the_notice_first(self):
        app_ = self.runner_for(self.app(), [])
        app_._handle_voice_command("echo sub type hello there")
        self.assertIn("hello there", app_._notice._text())

    def test_cancelling_types_nothing(self):
        keys = []
        app_ = self.runner_for(self.app(), keys)
        app_._handle_voice_command("echo sub type hello there")
        self.assertTrue(app_.cancel_pending_command())
        app_._notice.fire_now()
        self.assertEqual(keys, [])

    def test_your_microphone_can_type_without_the_wake_word(self):
        keys = []
        app_ = self.runner_for(self.app(voice_command_delay=0), keys)
        app_._handle_voice_command("type hello there", source="mic")
        self.assertEqual(keys, ["hello there"])

    def test_the_pcs_sound_cannot_type_without_the_wake_word(self):
        keys = []
        app_ = self.runner_for(self.app(voice_command_delay=0), keys)
        self.assertIsNone(app_._handle_voice_command("type hello there", source="system"))
        self.assertEqual(keys, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
