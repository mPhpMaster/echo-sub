# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""On-screen answers: your own text, shown in the caption box, sent nowhere."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ECHOSUB_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from echosub import config, screen_replies, voice_commands  # noqa: E402
from echosub.overlay import CaptionOverlay  # noqa: E402
from echosub.settings_dialog import SettingsDialog  # noqa: E402

app = QApplication.instance() or QApplication([])
PAIRS = [{"phrase": "who are you", "reply": "EchoSub, captioning this PC."},
         {"phrase": "من انت", "reply": "أنا إيكو سب."}]


class MatchingTest(unittest.TestCase):
    def test_a_chosen_phrase_after_the_wake_word_gives_your_answer(self):
        found = voice_commands.find("maya who are you", ("maya",), reply_pairs=PAIRS)
        self.assertEqual(found["action"], "reply")
        self.assertEqual(found["target"], "EchoSub, captioning this PC.")

    def test_it_works_in_arabic_too(self):
        found = voice_commands.find("مايا من انت", ("مايا",), reply_pairs=PAIRS)
        self.assertEqual(found["target"], "أنا إيكو سب.")

    def test_the_wake_word_is_still_required(self):
        self.assertIsNone(voice_commands.find("who are you", ("maya",), reply_pairs=PAIRS))

    def test_no_pairs_means_no_answers(self):
        self.assertIsNone(voice_commands.find("maya who are you", ("maya",), reply_pairs=()))

    def test_a_real_command_still_wins_over_an_answer(self):
        pairs = PAIRS + [{"phrase": "open calculator", "reply": "not this"}]
        found = voice_commands.find("maya open calculator", ("maya",), reply_pairs=pairs)
        self.assertEqual(found["action"], "reply", "the phrase the user wrote comes first, by design")
        self.assertEqual(found["target"], "not this")


class PairsTest(unittest.TestCase):
    def test_empty_and_broken_rows_are_dropped(self):
        pairs = screen_replies.valid_pairs([
            {"phrase": "", "reply": "x"}, {"phrase": "y", "reply": ""}, "not a dict", None,
            {"phrase": " hello ", "reply": " there "}, {"phrase": "HELLO", "reply": "again"}])
        self.assertEqual(pairs, [{"phrase": "hello", "reply": "there"}], "duplicates or blanks got through")

    def test_long_text_is_cut_and_the_list_is_capped(self):
        many = [{"phrase": f"phrase {i}", "reply": "x" * 500} for i in range(50)]
        pairs = screen_replies.valid_pairs(many)
        self.assertEqual(len(pairs), screen_replies.MAX_PAIRS)
        self.assertLessEqual(len(pairs[0]["reply"]), screen_replies.MAX_REPLY_CHARS)

    def test_an_answer_only_ever_carries_text(self):
        command = screen_replies.reply_command({"phrase": "hi", "reply": "hello"})
        self.assertEqual(command["action"], "reply")
        self.assertEqual(command["target"], "hello")
        self.assertNotIn("launch", command)


class RunnerTest(unittest.TestCase):
    def test_the_runner_hands_the_text_back_and_does_nothing_else(self):
        launched, pressed, media = [], [], []
        runner = voice_commands.CommandRunner(launcher=launched.append, key_presser=pressed.append,
                                              media_controller=media.append)
        message = runner.run(screen_replies.reply_command({"phrase": "hi", "reply": "hello there"}), now=0)
        self.assertEqual(message, "hello there")
        self.assertEqual((launched, pressed, media), ([], [], []))

    def test_a_forged_answer_without_text_is_refused(self):
        runner = voice_commands.CommandRunner()
        self.assertIsNone(runner.run({"key": "reply:x", "action": "reply", "target": None, "label": "x"}, now=0))


class CaptionBoxTest(unittest.TestCase):
    def test_an_answer_looks_different_from_what_people_said(self):
        cfg = dict(config.DEFAULTS, caption_animation="none")
        overlay = CaptionOverlay(cfg, lambda p: None, lambda g: None, lambda: None)
        overlay.show()
        self.addCleanup(overlay.close)
        overlay.add_final(1, "someone talking", "ترجمة", "en", 0, "system")
        overlay.add_final(2, "EchoSub answering", "EchoSub answering", "en", None, "reply")
        app.processEvents()
        colours = {line.translated._color.name().upper() for line in overlay.lines}
        from echosub.caption_widgets import REPLY_COLOR

        self.assertIn(REPLY_COLOR.upper(), colours, colours)
        badge = overlay.lines[-1].translated._badge
        self.assertIsNotNone(badge)
        self.assertIn("EchoSub", badge.text)

    def test_an_answer_can_be_taken_off_the_screen_again(self):
        cfg = dict(config.DEFAULTS, caption_animation="none")
        overlay = CaptionOverlay(cfg, lambda p: None, lambda g: None, lambda: None)
        overlay.show()
        self.addCleanup(overlay.close)
        overlay.add_final(7, "gone in a moment", "gone in a moment", "en", None, "reply")
        app.processEvents()
        self.assertEqual(len(overlay.entries), 1)
        overlay.remove_caption(7)
        self.assertEqual(overlay.entries, [])


class SettingsTest(unittest.TestCase):
    def test_it_is_off_until_switched_on(self):
        self.assertFalse(config.DEFAULTS["screen_replies"])
        self.assertFalse(SettingsDialog(dict(config.DEFAULTS)).values()["screen_replies"])

    def test_the_pairs_round_trip(self):
        cfg = dict(config.DEFAULTS, screen_replies=True, screen_reply_pairs=PAIRS, screen_reply_seconds=12)
        values = SettingsDialog(cfg).values()
        self.assertTrue(values["screen_replies"])
        self.assertEqual(values["screen_reply_pairs"], PAIRS)
        self.assertEqual(values["screen_reply_seconds"], 12)

    def test_the_table_follows_the_checkbox(self):
        dialog = SettingsDialog(dict(config.DEFAULTS, screen_replies=False))
        self.assertFalse(dialog.screen_reply_table.isEnabled())
        dialog.screen_replies.setChecked(True)
        self.assertTrue(dialog.screen_reply_table.isEnabled())


if __name__ == "__main__":
    unittest.main(verbosity=2)
