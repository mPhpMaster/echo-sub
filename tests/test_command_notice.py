# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""The pause before a command runs: what was heard is shown, and one click calls it off."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # the shared FakeApp harness
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ECHOSUB_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data"))

from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from echosub import config, voice_commands  # noqa: E402
from echosub.command_notice import CommandNotice  # noqa: E402

from test_voice_command_ui import FakeApp  # noqa: E402

app = QApplication.instance() or QApplication([])


class NoticeTest(unittest.TestCase):
    def notice(self):
        notice = CommandNotice()
        self.addCleanup(notice.close)
        return notice

    def test_it_says_what_it_heard_and_runs_after_the_countdown(self):
        ran = []
        notice = self.notice()
        notice.start("Calculator opened", 3, lambda: ran.append(1), now=0)
        self.assertTrue(notice.pending())
        self.assertIn("Calculator opened", notice._text())
        self.assertEqual(ran, [], "it must not run before the time is up")
        self.assertTrue(notice.fire_now())
        self.assertEqual(ran, [1])

    def test_a_click_calls_it_off(self):
        ran = []
        notice = self.notice()
        notice.start("Calculator opened", 3, lambda: ran.append(1))
        press = QMouseEvent(QEvent.MouseButtonPress, QPointF(5, 5), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        notice.mousePressEvent(press)
        self.assertFalse(notice.pending())
        self.assertFalse(notice.fire_now(), "a cancelled command must never run")
        self.assertEqual(ran, [])

    def test_the_countdown_runs_down(self):
        notice = self.notice()
        notice.start("x", 3, lambda: None, now=100)
        self.assertAlmostEqual(notice.remaining(now=101), 2.0, places=3)
        self.assertEqual(notice.remaining(now=200), 0.0)

    def test_cancelling_nothing_is_harmless(self):
        self.assertFalse(self.notice().cancel())

    def test_a_new_command_replaces_the_one_waiting(self):
        ran = []
        notice = self.notice()
        notice.start("first", 3, lambda: ran.append("first"))
        notice.start("second", 3, lambda: ran.append("second"))
        notice.fire_now()
        self.assertEqual(ran, ["second"], "the older command should not also run")


class AppTest(unittest.TestCase):
    def app(self, **overrides):
        overrides.setdefault("voice_command_delay", 3)
        return FakeApp(voice_commands=True, **overrides).use_fake_runner()

    def test_a_command_waits_instead_of_running_straight_away(self):
        app_ = self.app()
        self.assertIsNotNone(app_._handle_voice_command("echo sub open calculator"))
        self.assertEqual(app_.launched, [], "it ran before anybody could cancel it")
        app_._notice.fire_now()
        self.assertEqual(app_.launched, [voice_commands.APPS["calculator"]])

    def test_cancelling_stops_it_for_good(self):
        app_ = self.app()
        app_._handle_voice_command("echo sub open calculator")
        self.assertTrue(app_.cancel_pending_command())
        app_._notice.fire_now()
        self.assertEqual(app_.launched, [])

    def test_zero_seconds_means_run_at_once(self):
        app_ = self.app(voice_command_delay=0)
        app_._handle_voice_command("echo sub open calculator")
        self.assertEqual(app_.launched, [voice_commands.APPS["calculator"]])

    def test_an_answer_on_screen_does_not_wait(self):
        pairs = [{"phrase": "who are you", "reply": "EchoSub."}]
        app_ = self.app(screen_replies=True, screen_reply_pairs=pairs)
        app_._handle_voice_command("who are you")
        self.assertEqual(app_.overlay.shown, [("EchoSub.", "reply")], "text on screen has nothing to undo")

    def test_the_default_is_a_three_second_pause(self):
        self.assertEqual(config.DEFAULTS["voice_command_delay"], 3)


class MicrophoneTest(unittest.TestCase):
    """Your own microphone does not need the wake word; the countdown is what protects you."""

    def app(self, **overrides):
        return FakeApp(voice_commands=True, voice_command_delay=0, **overrides).use_fake_runner()

    def test_no_wake_word_is_needed_from_your_microphone(self):
        app_ = self.app()
        self.assertIsNotNone(app_._handle_voice_command("open calculator", source="mic"))
        self.assertEqual(app_.launched, [voice_commands.APPS["calculator"]])

    def test_the_pc_sound_still_needs_it(self):
        app_ = self.app()
        self.assertIsNone(app_._handle_voice_command("open calculator", source="system"))
        self.assertEqual(app_.launched, [], "a video saying this must not open anything")

    def test_you_can_ask_for_the_wake_word_on_the_microphone_too(self):
        app_ = self.app(mic_wake_word=True)
        self.assertIsNone(app_._handle_voice_command("open calculator", source="mic"))
        self.assertIsNotNone(app_._handle_voice_command("echo sub open calculator", source="mic"))

    def test_ordinary_talking_is_not_taken_as_a_command(self):
        app_ = self.app()
        for said in ("I was thinking we could open the calculator later on and check",
                     "yesterday he closed the notepad without saving anything at all"):
            with self.subTest(said=said):
                self.assertIsNone(app_._handle_voice_command(said, source="mic"))
        self.assertEqual(app_.launched, [])

    def test_nothing_is_reported_as_misheard_for_every_sentence(self):
        app_ = self.app()
        app_._handle_voice_command("just talking about my day", source="mic")
        self.assertEqual(app_.tray.messages, [], "that would pop up on every sentence you say")

    def test_the_microphone_can_still_be_told_not_to_obey(self):
        app_ = self.app(mic_commands=False)
        self.assertIsNone(app_._handle_voice_command("open calculator", source="mic"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
