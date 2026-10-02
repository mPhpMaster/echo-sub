# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Ways of asking that used to be missed, taken from a real session log."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ECHOSUB_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data"))

from echosub import voice_commands  # noqa: E402

WAKE = ("alexa",)
SAVED = [{"phrase": "music", "run": "D:\\song.mp3"}]
PLACES = [{"name": "music", "path": "D:\\Music"}]


def found(said, **options):
    options.setdefault("custom_commands", SAVED)
    return voice_commands.find(said, WAKE, **options)


class CustomPhraseTest(unittest.TestCase):
    def test_a_starting_word_before_your_phrase_is_allowed(self):
        for said in ("alexa music", "alexa run music", "alexa open music", "alexa play music",
                     "alexa start music"):
            with self.subTest(said=said):
                command = found(said)
                self.assertIsNotNone(command, said)
                self.assertEqual(command["action"], "run", said)

    def test_closing_is_not_a_request_to_start_it_again(self):
        for said in ("alexa close music", "alexa close the music"):
            with self.subTest(said=said):
                command = found(said)
                self.assertNotEqual(getattr(command, "get", lambda _k: None)("action"), "run", said)

    def test_going_to_a_place_still_goes_there(self):
        command = found("alexa go to music", folders=PLACES)
        self.assertEqual(command["action"], "open_folder")

    def test_a_sentence_around_your_phrase_is_not_your_command(self):
        for said in ("alexa the music is too loud", "alexa i like music a lot"):
            with self.subTest(said=said):
                command = found(said)
                self.assertTrue(command is None or command["action"] != "run", said)

    def test_a_longer_word_is_not_your_phrase(self):
        self.assertIsNone(found("alexa musical"), "a phrase must match whole words")


class AppNameAloneTest(unittest.TestCase):
    def test_the_name_on_its_own_opens_it(self):
        for said, key in (("alexa paint", "open_paint"), ("alexa calculator", "open_calculator"),
                          ("alexa notepad", "open_notepad")):
            with self.subTest(said=said):
                self.assertEqual(found(said)["key"], key)

    def test_talking_about_an_app_does_not_open_it(self):
        for said in ("alexa paint is a good program", "alexa i used notepad yesterday",
                     "alexa the calculator was wrong"):
            with self.subTest(said=said):
                self.assertIsNone(found(said), said)

    def test_open_and_close_still_win_over_the_bare_name(self):
        self.assertEqual(found("alexa close paint")["key"], "close_paint")
        self.assertEqual(found("alexa open paint")["key"], "open_paint")


if __name__ == "__main__":
    unittest.main(verbosity=2)
