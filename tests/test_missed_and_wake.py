# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""What was heard but not understood, and warning about a wake word that invites it."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # the shared FakeApp harness
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ECHOSUB_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from echosub import config, missed_window, voice_commands  # noqa: E402

from test_voice_command_ui import FakeApp  # noqa: E402

app = QApplication.instance() or QApplication([])


class WakeWordTest(unittest.TestCase):
    def test_a_word_from_everyday_speech_is_called_out(self):
        for wake in ("PC", "computer", "okay", "بيسي", "music"):
            with self.subTest(wake=wake):
                self.assertIsNotNone(voice_commands.wake_word_warning(wake), wake)

    def test_other_assistants_and_what_people_call_each_other_are_called_out(self):
        for wake in ("alexa", "hey google", "siri", "daddy", "bro", "حبيبي"):
            with self.subTest(wake=wake):
                self.assertIsNotNone(voice_commands.wake_word_warning(wake), wake)

    def test_several_bad_words_read_as_several(self):
        self.assertIn("turn up in ordinary speech", voice_commands.wake_word_warning("PC,بيسي,alexa,daddy"))
        self.assertIn("turns up in ordinary speech", voice_commands.wake_word_warning("PC"))

    def test_a_short_word_is_called_out(self):
        self.assertIn("short", voice_commands.wake_word_warning("da"))

    def test_a_sound_wake_word_says_nothing(self):
        for wake in ("echo sub", "maya", "jarvis", "إيكو صب"):
            with self.subTest(wake=wake):
                self.assertIsNone(voice_commands.wake_word_warning(wake), wake)

    def test_one_bad_word_in_a_list_is_enough_to_warn(self):
        warning = voice_commands.wake_word_warning("echo sub, PC")
        self.assertIsNotNone(warning)
        self.assertIn("PC", warning)

    def test_the_settings_show_it_as_you_type(self):
        from echosub.settings_dialog import SettingsDialog

        dialog = SettingsDialog(dict(config.DEFAULTS))
        self.addCleanup(dialog.close)
        dialog.voice_wake.setText("echo sub")
        self.assertFalse(dialog.wake_warning.isVisible() and dialog.wake_warning.text())
        dialog.voice_wake.setText("PC")
        self.assertIn("PC", dialog.wake_warning.text())


class MissedPhrasesTest(unittest.TestCase):
    def test_it_counts_repeats_and_puts_the_commonest_first(self):
        missed = missed_window.MissedPhrases()
        for phrase in ("run music", "paint", "run music", "run music", "paint"):
            missed.add(phrase)
        self.assertEqual(missed.rows(), [("run music", 3), ("paint", 2)])
        self.assertEqual(missed.total(), 5)

    def test_blank_phrases_are_ignored(self):
        missed = missed_window.MissedPhrases()
        for phrase in ("", "   ", None):
            missed.add(phrase)
        self.assertEqual(missed.rows(), [])

    def test_it_does_not_grow_without_end(self):
        missed = missed_window.MissedPhrases(limit=5)
        for index in range(50):
            missed.add(f"phrase {index}")
        self.assertLessEqual(len(missed.rows()), 5)

    def test_forgetting_empties_it(self):
        missed = missed_window.MissedPhrases()
        missed.add("something")
        missed.clear()
        self.assertEqual(missed.rows(), [])


class AppTest(unittest.TestCase):
    def test_every_miss_is_remembered_even_when_no_notice_is_shown(self):
        app_ = FakeApp(voice_commands=True, voice_command_wake="alexa").use_fake_runner()
        for _ in range(4):  # the notice has a cooldown; the record must not
            app_._handle_voice_command("alexa do something strange")
        self.assertEqual(app_.missed_phrases().rows(), [("do something strange", 4)])
        self.assertEqual(len(app_.tray.messages), 1, "only one notice, but four counted")

    def test_the_window_lists_them_and_can_hand_one_over(self):
        app_ = FakeApp(voice_commands=True, voice_command_wake="alexa").use_fake_runner()
        app_._handle_voice_command("alexa run music")
        handed = []
        window = missed_window.MissedWindow(app_.missed_phrases(), app_.cfg, handed.append)
        self.addCleanup(window.close)
        self.assertEqual(window.selected_phrase(), "run music")
        window._make_one()
        self.assertEqual(handed, ["run music"], "the phrase should reach the settings")

    def test_forgetting_clears_the_table_too(self):
        missed = missed_window.MissedPhrases()
        missed.add("something")
        window = missed_window.MissedWindow(missed, dict(config.DEFAULTS))
        self.addCleanup(window.close)
        window._forget()
        self.assertEqual(window.table.rowCount(), 0)
        self.assertFalse(window.make.isEnabled())


if __name__ == "__main__":
    unittest.main(verbosity=2)
