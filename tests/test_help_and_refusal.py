# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Saying "no" stops a command, and "help" opens the list of what can be said."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # the shared FakeApp harness
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ECHOSUB_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from echosub import config, help_window, voice_commands  # noqa: E402

from test_voice_command_ui import FakeApp  # noqa: E402

app = QApplication.instance() or QApplication([])


class RefusalWordsTest(unittest.TestCase):
    def test_the_usual_ways_of_saying_no(self):
        for said in ("no", "No.", "nope", "cancel", "cancel that", "stop", "wait",
                     "لا", "لا لا", "الغي", "بطل", "нет", "hayır", "不要"):
            with self.subTest(said=said):
                self.assertTrue(voice_commands.is_cancel(said), said)

    def test_a_sentence_that_merely_contains_no_is_not_a_refusal(self):
        for said in ("there is no reason", "I know nothing about it", "we had no idea",
                     "هذا كلام عادي", ""):
            with self.subTest(said=said):
                self.assertFalse(voice_commands.is_cancel(said), said)


class RefusalTest(unittest.TestCase):
    def app(self, **overrides):
        overrides.setdefault("voice_command_delay", 3)
        return FakeApp(voice_commands=True, **overrides).use_fake_runner()

    def test_saying_no_stops_the_command(self):
        app_ = self.app()
        app_._handle_voice_command("echo sub open calculator")
        self.assertTrue(app_._notice.pending())
        self.assertTrue(app_.heard_a_refusal("no"))
        self.assertFalse(app_._notice.pending())
        app_._notice.fire_now()
        self.assertEqual(app_.launched, [], "a command called off must never run")

    def test_it_needs_no_wake_word_and_takes_any_sound(self):
        app_ = self.app()
        app_._handle_voice_command("echo sub open calculator")
        self.assertIsNone(app_._handle_voice_command("لا", source="system"))
        app_._notice.fire_now()
        self.assertEqual(app_.launched, [])

    def test_saying_no_with_nothing_waiting_does_nothing(self):
        app_ = self.app()
        self.assertFalse(app_.heard_a_refusal("no"))
        self.assertEqual(app_.tray.messages, [])

    def test_ordinary_talk_does_not_stop_a_command(self):
        app_ = self.app()
        app_._handle_voice_command("echo sub open calculator")
        self.assertFalse(app_.heard_a_refusal("there is no reason to worry"))
        self.assertTrue(app_._notice.pending(), "that sentence should not have cancelled anything")


class HelpWindowTest(unittest.TestCase):
    def window(self, **overrides):
        cfg = dict(config.DEFAULTS, voice_commands=True, voice_command_wake="mama", **overrides)
        window = help_window.HelpWindow(cfg)
        self.addCleanup(window.close)
        return window

    def test_every_row_uses_your_own_wake_word(self):
        rows = self.window().rows
        self.assertTrue(len(rows) > 10)
        self.assertTrue(all(say.startswith("mama") for say, _does, _on in rows if say != "no"))

    def test_the_apps_it_really_knows_are_listed(self):
        said = " ".join(does for _say, does, _on in self.window().rows)
        for app_name in ("calculator", "notepad"):
            self.assertIn(app_name, said)

    def test_a_switched_off_command_is_listed_but_marked_off(self):
        rows = self.window(voice_typing=False, voice_key_presses=False).rows
        off = {say for say, _does, enabled in rows if not enabled}
        self.assertTrue(any("type" in say for say in off), off)
        self.assertTrue(any("press" in say for say in off), off)

    def test_switching_them_on_marks_them_on(self):
        rows = self.window(voice_typing=True, voice_key_presses=True).rows
        self.assertTrue(all(enabled for _say, _does, enabled in rows))

    def test_your_own_commands_are_listed(self):
        rows = self.window(voice_custom_commands=[{"phrase": "movie mode", "run": "notepad.exe"}]).rows
        self.assertTrue(any("movie mode" in say for say, _does, _on in rows))

    def test_the_translation_column_is_hidden_for_english(self):
        self.assertTrue(self.window(target_lang="en").table.isColumnHidden(2))

    def test_and_shown_for_another_language(self):
        window = self.window(target_lang="ar")
        self.assertFalse(window.table.isColumnHidden(2))
        self.assertEqual(window.table.horizontalHeaderItem(2).text(), "Arabic")

    def test_a_translator_that_fails_leaves_the_window_standing(self):
        class Broken:
            def translate(self, text, src, tgt):
                raise OSError("the translator is busy")

        cfg = dict(config.DEFAULTS, voice_commands=True, target_lang="ar")
        window = help_window.HelpWindow(cfg, translator=Broken())
        self.addCleanup(window.close)
        window._translate_all(Broken(), "ar")  # would raise if a failure were not handled
        window._drain()
        self.assertEqual(window.table.item(0, 2).text(), "")

    def test_closing_the_window_stops_the_translating(self):
        slow = []

        class Slow:
            def translate(self, text, src, tgt):
                slow.append(text)
                return "x"

        cfg = dict(config.DEFAULTS, voice_commands=True, target_lang="ar")
        window = help_window.HelpWindow(cfg, translator=Slow())
        window.close()
        self.assertTrue(window._stop.is_set(), "the worker must be told to stop")
        self.assertFalse(window._timer.isActive(), "nothing should still be polling a closed window")


if __name__ == "__main__":
    unittest.main(verbosity=2)
