# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Closing EchoSub by voice: "echo sub, exit"."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ECHOSUB_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data"))

from echosub import voice_commands  # noqa: E402
from echosub.help_window import rows  # noqa: E402
from test_voice_command_ui import FakeApp  # noqa: E402


def key(text, **options):
    found = voice_commands.find(text, **options)
    return found and found["key"]


class MatchTest(unittest.TestCase):
    def test_the_ways_to_say_it(self):
        for said in ("echo sub exit", "echo sub quit.", "echo sub close yourself", "echo sub quit echo sub",
                     "echo sub close the app", "بي سي اخرج", "ايكو صب اقفل البرنامج", "ايكو صب سكر نفسك"):
            with self.subTest(said=said):
                self.assertEqual(key(said), "exit_app")

    def test_closing_another_program_is_not_closing_echosub(self):
        self.assertEqual(key("echo sub close chrome"), "close_chrome")

    def test_exit_with_something_else_after_it_is_not_taken_for_it(self):
        self.assertIsNone(key("echo sub exit the game now"))

    def test_without_the_wake_word_the_pcs_sound_cannot_close_it(self):
        self.assertIsNone(key("exit"))
        self.assertIsNone(key("the exit is on the left"))


class AppTest(unittest.TestCase):
    def app(self, **overrides):
        app_ = FakeApp(voice_commands=True, **overrides).use_fake_runner()
        app_.quits = 0

        def quit_():
            app_.quits += 1

        app_._quit = quit_
        return app_

    def test_it_closes_the_app(self):
        app_ = self.app()
        app_._handle_voice_command("echo sub exit")
        self.assertEqual(app_.quits, 1)

    def test_from_your_microphone_the_word_alone_is_enough(self):
        app_ = self.app()
        app_._handle_voice_command("exit", source="mic")
        self.assertEqual(app_.quits, 1)

    def test_it_waits_for_the_countdown_and_no_keeps_it_open(self):
        app_ = self.app(voice_command_delay=3)
        app_._handle_voice_command("echo sub exit")
        self.assertEqual(app_.quits, 0, "it must not close before the countdown")
        app_._handle_voice_command("no")
        app_._notice.fire_now()  # the countdown ends here, so nothing is left running after the test
        self.assertEqual(app_.quits, 0)

    def test_the_help_window_lists_it(self):
        self.assertTrue(any("Close EchoSub" in does for _say, does, *_ in rows(dict(voice_commands=True))))


if __name__ == "__main__":
    unittest.main(verbosity=2)
