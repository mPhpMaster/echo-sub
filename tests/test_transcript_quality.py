# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Tests for hallucination gates that must stay inexpensive on a weak PC."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from echosub.transcript_quality import (  # noqa: E402
    is_hallucination, is_implausibly_fast, is_unreliable_live_text,
)


class TranscriptQualityTest(unittest.TestCase):
    def test_rejects_known_silence_and_music_hallucinations(self):
        self.assertTrue(is_hallucination("Thank you for watching."))
        self.assertTrue(is_hallucination("شكراً للمشاهدة"))
        self.assertTrue(is_hallucination("…"))

    def test_rejects_exact_repeating_loops_but_keeps_normal_speech(self):
        self.assertTrue(is_hallucination("hello hello hello hello hello hello"))
        self.assertFalse(is_hallucination("the customer asks for the order before noon"))

    def test_rejects_text_that_is_impossible_for_the_audio_duration(self):
        self.assertTrue(is_implausibly_fast("x" * 70, 1.0))
        self.assertFalse(is_implausibly_fast("A short normal sentence.", 2.0))


class LiveTextTrustTest(unittest.TestCase):
    """Live text is a guess at half a sentence, so it is judged more strictly than a caption."""

    def test_normal_live_text_is_kept(self):
        self.assertFalse(is_unreliable_live_text("we are going to talk about", 2.0, 0.98))

    def test_an_unsure_language_guess_is_rejected(self):
        self.assertTrue(is_unreliable_live_text("we are going to talk about", 2.0, 0.3))

    def test_known_hallucinations_and_empty_guesses_are_rejected(self):
        self.assertTrue(is_unreliable_live_text("Thanks for watching!", 2.0, 0.99))
        self.assertTrue(is_unreliable_live_text(" ", 2.0, 0.99))
        self.assertTrue(is_unreliable_live_text("hi hi hi hi hi hi", 2.0, 0.99))

    def test_it_is_stricter_than_the_caption_gate(self):
        text, seconds = "x" * 56, 2.0  # 28 characters per second
        self.assertFalse(is_implausibly_fast(text, seconds), "the caption gate should still allow this")
        self.assertTrue(is_unreliable_live_text(text, seconds, 0.99))

    def test_a_missing_language_score_does_not_reject_the_text(self):
        self.assertFalse(is_unreliable_live_text("a normal live guess", 2.0, None))
