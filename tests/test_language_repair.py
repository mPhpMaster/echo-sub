# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""English that Whisper labelled as another language: keep the words, correct the label.

Every line below was taken from a real session log, where it was thrown away.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ECHOSUB_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data"))

from echosub import languages  # noqa: E402

# (text, the language Whisper claimed) — real English, lost before this change
LOST_ENGLISH = [
    ("Good game.", "hi"),
    ("but you can't do it", "ar"),
    ("now that's the 3rd one", "ar"),
    ("God can't even understand this", "hi"),
    ("Yeah I'm talking about shit", "ko"),
    ("but it ended up more but it's sad", "ar"),
    # Half English, half another language, as bilingual speech really comes out. The English half
    # is worth showing, so these are kept rather than thrown away whole.
    ("我 feelin good", "zh"),
    ("ياني open laundry", "hi"),
]

# Speech in another language written in Latin letters: guessing English would be worse than silence
NOT_ENGLISH = [
    ("Shingad Jhatra bhai.", "hi"),
    ("Vizag Paisak", "hi"),
    ("Shabu lindu lothi aap", "hi"),
    ("Raiya hai huyentapra.", "hi"),
    ("bhajda", "ml"),
    ("Saimnik.", "hi"),
]

# Text in an unexpected alphabet of its own: there is no telling what it was meant to be
STILL_DROPPED = [
    ("विस्वार वार कोनन", "ml"),
    ("आमी तो माए बालो", "bn"),
    ("E a привет!", "pt"),
]


class RepairTest(unittest.TestCase):
    def test_lost_english_is_now_kept_as_english(self):
        for text, claimed in LOST_ENGLISH:
            with self.subTest(text=text):
                self.assertFalse(languages.fits_script(text, claimed), "the guard should still object")
                self.assertEqual(languages.repaired_language(text, claimed), "en", text)

    def test_other_languages_in_latin_letters_are_not_called_english(self):
        for text, claimed in NOT_ENGLISH:
            with self.subTest(text=text):
                self.assertIsNone(languages.repaired_language(text, claimed), text)

    def test_text_in_another_alphabet_is_still_dropped(self):
        for text, claimed in STILL_DROPPED:
            with self.subTest(text=text):
                self.assertIsNone(languages.repaired_language(text, claimed), text)

    def test_a_label_that_already_fits_is_left_alone(self):
        self.assertIsNone(languages.repaired_language("this is plain english", "en"))
        self.assertIsNone(languages.repaired_language("هذا كلام "
                                                      "عربي", "ar"))

    def test_nothing_to_repair_in_nothing(self):
        self.assertIsNone(languages.repaired_language("", "hi"))


class EnglishWordsTest(unittest.TestCase):
    def test_everyday_sentences_are_recognized(self):
        for text in ("what are you doing", "I think that is the one", "yeah well we should go now",
                     "Good game.", "it was not very good"):
            self.assertTrue(languages.looks_like_english(text), text)

    def test_names_and_other_languages_are_not(self):
        for text in ("Shingad Jhatra bhai", "Vizag Paisak", "bhajda", "", "   ", "12345",
                     "Kaise ho aap bhai"):
            self.assertFalse(languages.looks_like_english(text), text)

    def test_one_word_counts_when_it_is_a_common_one(self):
        self.assertTrue(languages.looks_like_english("yes"))
        self.assertFalse(languages.looks_like_english("Saimnik"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
