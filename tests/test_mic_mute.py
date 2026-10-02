# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Muting your own microphone by voice: only your voice may, and it can always undo itself."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # the shared FakeApp harness
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ECHOSUB_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from echosub import voice_commands  # noqa: E402

from test_voice_command_ui import FakeApp  # noqa: E402

app = QApplication.instance() or QApplication([])  # the countdown notice is a real widget


class MatchingTest(unittest.TestCase):
    def test_the_usual_ways_of_saying_it(self):
        for said in ("echo sub mute my microphone", "echo sub microphone off", "echo sub stop the mic",
                     "echo sub unmute my mic", "echo sub اكتم المايك",
                     "echo sub وقف المايك"):
            with self.subTest(said=said):
                command = voice_commands.find(said)
                self.assertIsNotNone(command, said)
                self.assertEqual(command["key"], "toggle_mic", said)

    def test_merely_mentioning_a_microphone_does_not_switch_it(self):
        for said in ("echo sub my microphone is a blue one", "echo sub where is the mic"):
            with self.subTest(said=said):
                self.assertIsNone(voice_commands.find(said), said)

    def test_it_is_marked_as_yours_alone(self):
        self.assertTrue(voice_commands.command("toggle_mic")["mic_only"])


class AppTest(unittest.TestCase):
    def app(self, **overrides):
        overrides.setdefault("voice_command_delay", 0)
        return FakeApp(voice_commands=True, **overrides).use_fake_runner()

    @staticmethod
    def let_a_moment_pass(app_):
        """Step past the few seconds that stop one sentence being obeyed twice over."""
        key, _when = app_._voice_runner._last
        app_._voice_runner._last = (key, 0.0)

    def test_your_voice_mutes_and_then_brings_it_back(self):
        app_ = self.app()
        self.assertFalse(app_.mic_muted())
        app_._handle_voice_command("echo sub mute my microphone", source="mic")
        self.assertTrue(app_.mic_muted())
        self.let_a_moment_pass(app_)
        app_._handle_voice_command("echo sub mute my microphone", source="mic")
        self.assertFalse(app_.mic_muted(), "the same phrase must bring it back")

    def test_saying_it_twice_at_once_only_counts_once(self):
        """The same sentence heard twice in a breath is an echo, not two decisions."""
        app_ = self.app()
        app_._handle_voice_command("echo sub mute my microphone", source="mic")
        app_._handle_voice_command("echo sub mute my microphone", source="mic")
        self.assertTrue(app_.mic_muted(), "a repeat within a few seconds must not undo it")

    def test_the_pcs_own_sound_cannot_touch_your_microphone(self):
        app_ = self.app()
        self.assertIsNone(app_._handle_voice_command("echo sub mute my microphone", source="system"))
        self.assertFalse(app_.mic_muted(), "a video or a call must not mute you")

    def test_a_muted_microphone_can_still_unmute_itself(self):
        app_ = self.app()
        app_.set_mic_muted(True)
        self.assertIsNotNone(app_._handle_voice_command("echo sub mute my microphone", source="mic"))
        self.assertFalse(app_.mic_muted())

    def test_a_muted_microphone_may_do_nothing_else(self):
        app_ = self.app()
        app_.set_mic_muted(True)
        self.assertIsNone(app_._handle_voice_command("echo sub open calculator", source="mic"))
        self.assertEqual(app_.launched, [])

    def test_the_pcs_own_sound_still_works_while_you_are_muted(self):
        app_ = self.app()
        app_.set_mic_muted(True)
        self.assertIsNotNone(app_._handle_voice_command("echo sub open calculator", source="system"))
        self.assertEqual(app_.launched, [voice_commands.APPS["calculator"]])

    def test_it_waits_out_the_countdown_like_any_other_command(self):
        app_ = self.app(voice_command_delay=3)
        app_._handle_voice_command("echo sub mute my microphone", source="mic")
        self.assertFalse(app_.mic_muted(), "nothing should happen before the countdown ends")
        app_._notice.fire_now()
        self.assertTrue(app_.mic_muted())


if __name__ == "__main__":
    unittest.main(verbosity=2)
