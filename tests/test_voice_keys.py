# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Pressing keys by name: the Windows key, combinations, and nothing that is not a key."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ECHOSUB_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data"))

from echosub import config, voice_commands, voice_keys  # noqa: E402

WIN, CTRL, SHIFT, ALT = 0x5B, 0x11, 0x10, 0x12


def found(said):
    return voice_commands.find(said, ("alexa",), allow_key_presses=True)


class ResolveTest(unittest.TestCase):
    def test_the_windows_key_on_its_own(self):
        self.assertEqual(voice_keys.resolve(["windows"]), (((), WIN),))
        self.assertEqual(voice_keys.resolve(["start"]), (((), WIN),))

    def test_a_combination_holds_the_modifier(self):
        self.assertEqual(voice_keys.resolve(["windows", "and", "r"]), (((WIN,), ord("R")),))
        self.assertEqual(voice_keys.resolve(["ctrl", "shift", "escape"]), (((CTRL, SHIFT), 0x1B),))
        self.assertEqual(voice_keys.resolve(["alt", "f4"]), (((ALT,), 0x73),))

    def test_plain_keys_are_pressed_one_after_another(self):
        self.assertEqual(voice_keys.resolve(["a", "b"]), (((), ord("A")), ((), ord("B"))))

    def test_joining_words_are_ignored(self):
        for joiner in ("and", "plus", "+", "و"):
            with self.subTest(joiner=joiner):
                self.assertEqual(voice_keys.resolve(["ctrl", joiner, "s"]), (((CTRL,), ord("S")),))

    def test_arabic_key_names(self):
        self.assertEqual(voice_keys.resolve(["ويندوز"]), (((), WIN),))
        self.assertEqual(voice_keys.resolve(["كنترول", "s"]),
                         (((CTRL,), ord("S")),))

    def test_a_word_that_is_not_a_key_resolves_to_nothing(self):
        for words in (["banana"], ["the", "red", "button"], [], ["ctrl", "banana"], ["a", "ctrl", "b"]):
            with self.subTest(words=words):
                self.assertIsNone(voice_keys.resolve(words), words)

    def test_too_many_keys_are_refused(self):
        self.assertIsNone(voice_keys.resolve(["ctrl", "shift", "alt", "windows", "a"]))

    def test_how_it_is_written_on_screen(self):
        self.assertEqual(voice_keys.label(["windows", "and", "r"]), "Windows + R")
        self.assertEqual(voice_keys.label(["ctrl", "shift", "escape"]), "Ctrl + Shift + Escape")
        self.assertEqual(voice_keys.label(["a", "b"]), "A B")


class SpokenTest(unittest.TestCase):
    def test_press_windows_is_understood(self):
        command = found("alexa press windows")
        self.assertEqual((command["action"], command["target"]), ("press_keys", ("windows",)))
        self.assertIn("Windows", command["label"])

    def test_press_start_is_the_same_key(self):
        self.assertEqual(voice_keys.resolve(found("alexa press start")["target"]), (((), WIN),))

    def test_press_windows_and_r(self):
        command = found("alexa press windows and r")
        self.assertEqual(voice_keys.resolve(command["target"]), (((WIN,), ord("R")),))
        self.assertEqual(command["label"], "Pressed Windows + R")

    def test_arabic_is_understood(self):
        command = found("alexa اضغط ويندوز")
        self.assertEqual(voice_keys.resolve(command["target"]), (((), WIN),))

    def test_it_is_off_until_switched_on(self):
        self.assertFalse(config.DEFAULTS["voice_key_presses"])
        self.assertIsNone(voice_commands.find("alexa press windows", ("alexa",)))

    def test_the_wake_word_is_still_needed(self):
        self.assertIsNone(voice_commands.find("press windows and r", ("alexa",), allow_key_presses=True))

    def test_ordinary_talk_about_pressing_does_nothing(self):
        for said in ("alexa press the button for me", "alexa press on", "alexa press banana"):
            with self.subTest(said=said):
                self.assertIsNone(found(said), said)


class RunnerTest(unittest.TestCase):
    def test_the_runner_passes_the_words_to_the_key_presser(self):
        pressed, launched = [], []
        runner = voice_commands.CommandRunner(key_presser=pressed.append, launcher=launched.append)
        command = found("alexa press windows and r")
        self.assertEqual(runner.run(command, now=0), "Pressed Windows + R")
        self.assertEqual((pressed, launched), ([("windows", "and", "r")], []))

    def test_a_forged_press_of_something_that_is_not_a_key_is_refused(self):
        runner = voice_commands.CommandRunner(key_presser=lambda keys: None)
        forged = {"key": "press:x", "action": "press_keys", "target": ("banana",), "label": "x"}
        self.assertIsNone(runner.run(forged, now=0))


class ReleaseTest(unittest.TestCase):
    """A modifier must never be left held down, even when the key press itself fails."""

    def setUp(self):
        self.sent = []
        self._real = voice_keys._send
        voice_keys._send = lambda code, up: self.sent.append((code, up))
        self.addCleanup(lambda: setattr(voice_keys, "_send", self._real))

    def test_the_modifier_goes_down_and_comes_back_up(self):
        voice_keys.press(["windows", "r"])
        self.assertEqual(self.sent, [(WIN, False), (ord("R"), False), (ord("R"), True), (WIN, True)])

    def test_the_modifier_is_released_even_if_the_key_fails(self):
        def explode(code, up):
            self.sent.append((code, up))
            if code == ord("R") and not up:
                raise OSError("the key press failed")

        voice_keys._send = explode
        with self.assertRaises(OSError):
            voice_keys.press(["windows", "r"])
        self.assertIn((WIN, True), self.sent, "the Windows key would have stayed stuck down")


if __name__ == "__main__":
    unittest.main(verbosity=2)
