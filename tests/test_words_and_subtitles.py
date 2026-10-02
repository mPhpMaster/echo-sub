# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Your own spellings, the words you watch for, and saving captions as subtitles."""
import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ECHOSUB_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from echosub import config, subtitles, transcript_fixes  # noqa: E402
from echosub.settings_dialog import SettingsDialog  # noqa: E402

app = QApplication.instance() or QApplication([])
FIXES = [{"heard": "mega bonk", "write": "Megabonk"}, {"heard": "sensei", "write": "Sensei"}]


class FixesTest(unittest.TestCase):
    def test_a_name_is_spelled_the_way_you_asked(self):
        self.assertEqual(transcript_fixes.apply_fixes("i played mega bonk", FIXES), "i played Megabonk")

    def test_case_does_not_matter_when_it_is_heard(self):
        for said in ("MEGA BONK", "Mega Bonk", "mega  bonk"):
            with self.subTest(said=said):
                self.assertEqual(transcript_fixes.apply_fixes(said, FIXES), "Megabonk")

    def test_it_only_swaps_whole_words(self):
        self.assertEqual(transcript_fixes.apply_fixes("megabonkers stay", FIXES), "megabonkers stay")

    def test_arabic_works_too(self):
        fixes = [{"heard": "\u0645\u064a\u062c\u0627 \u0628\u0648\u0646\u0643", "write": "Megabonk"}]
        said = "\u0644\u0639\u0628\u062a \u0645\u064a\u062c\u0627 \u0628\u0648\u0646\u0643"
        self.assertEqual(transcript_fixes.apply_fixes(said, fixes), "\u0644\u0639\u0628\u062a Megabonk")

    def test_a_longer_phrase_wins_over_a_shorter_one(self):
        fixes = [{"heard": "bonk", "write": "WRONG"}, {"heard": "mega bonk", "write": "Megabonk"}]
        self.assertEqual(transcript_fixes.apply_fixes("mega bonk", fixes), "Megabonk")

    def test_broken_rows_are_dropped(self):
        kept = transcript_fixes.valid_fixes(
            [{"heard": "", "write": "x"}, {"heard": "y", "write": ""}, "junk", None,
             {"heard": " a ", "write": " b "}, {"heard": "A", "write": "c"}])
        self.assertEqual(kept, [{"heard": "a", "write": "b"}])

    def test_nothing_in_nothing_out(self):
        self.assertEqual(transcript_fixes.apply_fixes("", FIXES), "")
        self.assertIsNone(transcript_fixes.apply_fixes(None, FIXES))

    def test_a_replacement_with_a_backslash_is_not_read_as_an_escape(self):
        fixes = [{"heard": "path", "write": "C:\\Users"}]
        self.assertEqual(transcript_fixes.apply_fixes("the path here", fixes), "the C:\\Users here")


class AlertTest(unittest.TestCase):
    def test_a_watched_word_is_reported(self):
        self.assertEqual(transcript_fixes.alerts_in("did someone say Sensei", ["sensei", "boss"]), ["sensei"])

    def test_the_caption_is_never_changed(self):
        text = "did someone say Sensei"
        transcript_fixes.alerts_in(text, ["sensei"])
        self.assertEqual(text, "did someone say Sensei")

    def test_a_word_inside_a_longer_one_is_not_a_match(self):
        self.assertEqual(transcript_fixes.alerts_in("senseis everywhere", ["sensei"]), [])

    def test_nothing_watched_means_nothing_reported(self):
        self.assertEqual(transcript_fixes.alerts_in("anything at all", []), [])

    def test_the_list_is_capped(self):
        self.assertLessEqual(len(transcript_fixes.valid_alerts([f"w{i}" for i in range(99)])),
                             transcript_fixes.MAX_ALERTS)


class SubtitleTest(unittest.TestCase):
    def records(self, *offsets):
        start = datetime.datetime(2026, 1, 1, 12, 0, 0)
        return [{"time": start + datetime.timedelta(seconds=s), "original": f"line {i}",
                 "translated": f"\u0633\u0637\u0631 {i}"} for i, s in enumerate(offsets)]

    def test_it_looks_like_a_subtitle_file(self):
        text = subtitles.to_srt(self.records(0, 2.5))
        self.assertTrue(text.startswith("1\n00:00:00,000 --> 00:00:02,500\n"), text[:60])
        self.assertIn("line 0", text)
        self.assertIn("\u0633\u0637\u0631 0", text)

    def test_a_long_gap_does_not_stretch_a_line_across_it(self):
        start, end, _r = subtitles.spans(self.records(0, 600))[0]
        self.assertEqual(end - start, subtitles.MAX_SECONDS)

    def test_a_very_short_gap_is_still_readable(self):
        start, end, _r = subtitles.spans(self.records(0, 0.1))[0]
        self.assertGreaterEqual(end - start, subtitles.MIN_SECONDS)

    def test_one_language_at_a_time(self):
        records = self.records(0)
        self.assertIn("line 0", subtitles.to_srt(records, "original"))
        self.assertNotIn("\u0633\u0637\u0631 0", subtitles.to_srt(records, "original"))
        self.assertIn("\u0633\u0637\u0631 0", subtitles.to_srt(records, "translation"))
        self.assertNotIn("line 0", subtitles.to_srt(records, "translation"))

    def test_an_untranslated_line_is_not_written_twice(self):
        records = [{"time": datetime.datetime(2026, 1, 1), "original": "same", "translated": "same"}]
        self.assertEqual(subtitles.to_srt(records).count("same"), 1)

    def test_no_captions_make_an_empty_file_not_a_crash(self):
        self.assertEqual(subtitles.to_srt([]), "")
        self.assertEqual(subtitles.spans([]), [])

    def test_empty_captions_are_skipped(self):
        records = [{"time": datetime.datetime(2026, 1, 1), "original": "", "translated": ""}]
        self.assertEqual(subtitles.to_srt(records), "")


class SettingsTest(unittest.TestCase):
    def test_the_words_tab_round_trips(self):
        cfg = dict(config.DEFAULTS, transcript_fixes=FIXES, alert_words=["Sensei"], alert_sound=True)
        values = SettingsDialog(cfg).values()
        self.assertEqual(values["transcript_fixes"], FIXES)
        self.assertEqual(values["alert_words"], ["Sensei"])
        self.assertTrue(values["alert_sound"])

    def test_they_are_empty_until_you_fill_them(self):
        self.assertEqual(config.DEFAULTS["transcript_fixes"], [])
        self.assertEqual(config.DEFAULTS["alert_words"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
