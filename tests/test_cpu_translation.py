# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Translating on the processor: a quicker search, and a core left for speech recognition."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ctranslate2  # noqa: E402
import sentencepiece  # noqa: E402

from echosub import config, cuda_libs, translate  # noqa: E402


class FakeTranslator:
    made = []

    def __init__(self, path, device, compute_type, intra_threads):
        FakeTranslator.made.append({"device": device, "threads": intra_threads})


class TranslatorTest(unittest.TestCase):
    def setUp(self):
        saved = (ctranslate2.Translator, ctranslate2.get_cuda_device_count, sentencepiece.SentencePieceProcessor,
                 cuda_libs.available)
        self.addCleanup(lambda: (setattr(ctranslate2, "Translator", saved[0]),
                                 setattr(ctranslate2, "get_cuda_device_count", saved[1]),
                                 setattr(sentencepiece, "SentencePieceProcessor", saved[2]),
                                 setattr(cuda_libs, "available", saved[3])))
        ctranslate2.Translator = FakeTranslator
        sentencepiece.SentencePieceProcessor = lambda model_file: None
        FakeTranslator.made.clear()

    def make(self, device, cards=1, libs=True, fast=True):
        ctranslate2.get_cuda_device_count = lambda: cards
        cuda_libs.available = lambda: libs
        return translate.NLLBTranslator("model", device, fast)

    def test_on_the_processor_a_quicker_search(self):
        self.assertEqual(self.make("cpu").beam_size, 1)
        self.assertEqual(self.make("cpu", fast=False).beam_size, 2, "it can be switched off")

    def test_on_an_nvidia_card_nothing_changes(self):
        made = self.make("cuda")
        self.assertEqual((made.device, made.beam_size), ("cuda", 2))

    def test_without_nvidias_libraries_it_never_tries_the_card(self):
        made = self.make("cuda", libs=False)
        self.assertEqual(made.device, "cpu", "every sentence would fail on the card")

    def test_a_core_is_left_for_speech_recognition(self):
        self.make("cpu")
        self.assertLessEqual(FakeTranslator.made[-1]["threads"], max(1, (os.cpu_count() or 4) - 1))
        self.assertLessEqual(translate.cpu_threads(), 4)
        self.assertGreaterEqual(translate.cpu_threads(), 1)

    def test_on_by_default(self):
        self.assertTrue(config.DEFAULTS["fast_cpu_translation"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
