# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""The any-brand graphics-card engine: reading its answers, and falling back when it cannot run."""
import io
import os
import sys
import unittest
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from echosub import asr_vulkan, downloads  # noqa: E402


def answer(segments, probs=None):
    reply = {"text": " ".join(s["text"] for s in segments), "segments": segments}
    if probs is not None:
        reply["language_probabilities"] = probs
    return reply


def segment(text, no_speech=0.01, logprob=-0.2):
    return {"text": text, "no_speech_prob": no_speech, "avg_logprob": logprob}


class ReadAnswerTest(unittest.TestCase):
    def test_text_and_the_detected_language(self):
        text, lang, prob, ranked = asr_vulkan.read_answer(
            answer([segment(" Hello there,"), segment(" how are you today?")], {"en": 0.93, "de": 0.04}), None, 3.0)
        self.assertEqual(text, "Hello there, how are you today?")
        self.assertEqual((lang, prob), ("en", 0.93))
        self.assertEqual(ranked[0], ("en", 0.93))

    def test_a_longer_clip_uses_the_language_the_transcription_settled_on(self):
        reply = answer([segment("مساء الخير جميعا المباراة تبدأ الساعة التاسعة")])
        reply["language"] = "arabic"
        _text, lang, prob, _ = asr_vulkan.read_answer(reply, None, 6.0)
        self.assertEqual((lang, prob), ("ar", 1.0))

    def test_a_language_you_chose_is_kept(self):
        _text, lang, prob, _ = asr_vulkan.read_answer(answer([segment("مرحبا بك")]), "ar", 2.0)
        self.assertEqual((lang, prob), ("ar", 1.0))

    def test_probable_silence_is_dropped(self):
        text, *_ = asr_vulkan.read_answer(answer([segment("Thank you.", no_speech=0.9, logprob=-1.0),
                                                  segment("real words here")], {"en": 0.9}), None, 3.0)
        self.assertEqual(text, "real words here")

    def test_a_loop_of_the_same_words_is_dropped(self):
        looped = "la " * 60
        text, *_ = asr_vulkan.read_answer(answer([segment(looped)], {"en": 0.9}), None, 10.0)
        self.assertEqual(text, "")

    def test_a_short_unsure_clip_is_dropped(self):
        text, *_ = asr_vulkan.read_answer(answer([segment("maybe words")], {"en": 0.3}), None, 0.8)
        self.assertEqual(text, "")


class AudioTest(unittest.TestCase):
    def test_audio_goes_as_16_bit_mono_16k_wav(self):
        data = asr_vulkan.wav_bytes(np.sin(np.linspace(0, 100, 16000)).astype(np.float32) * 2)  # clipped
        with wave.open(io.BytesIO(data)) as wav:
            self.assertEqual((wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes()),
                             (1, 2, 16000, 16000))


class ModelFileTest(unittest.TestCase):
    def test_every_speech_model_has_a_graphics_card_file(self):
        from echosub import config

        for name in config.WHISPER_MODELS:
            self.assertIn(name, asr_vulkan.GGML_FILES)

    def test_an_unknown_model_is_refused(self):
        with self.assertRaises(downloads.DownloadFailed):
            downloads.ModelDownloader(models_dir=os.devnull).whisper_ggml("huge-v9")


class FallbackTest(unittest.TestCase):
    """If the graphics-card engine cannot start, captions carry on with the processor."""

    def setUp(self):
        from echosub import asr

        self.statuses = []
        real_vulkan, real_cpu = asr_vulkan.VulkanTranscriber, asr.Transcriber
        self.addCleanup(lambda: setattr(asr_vulkan, "VulkanTranscriber", real_vulkan))
        self.addCleanup(lambda: setattr(asr, "Transcriber", real_cpu))
        asr.Transcriber = lambda path, device: ("processor", path, device)

    class Downloader:
        def whisper_ggml(self, name):
            return f"ggml:{name}"

        def whisper(self, name):
            return f"ct2:{name}"

    def test_a_failure_to_start_falls_back_to_the_processor(self):
        def broken(path):
            raise asr_vulkan.VulkanUnavailable("no engine")

        asr_vulkan.VulkanTranscriber = broken
        engine = asr_vulkan.load(self.Downloader(), "small", self.statuses.append)
        self.assertEqual(engine, ("processor", "ct2:small", "cpu"))
        self.assertIn("processor", self.statuses[-1])

    def test_a_canceled_download_is_not_swallowed(self):
        class Canceling(self.Downloader):
            def whisper_ggml(self, name):
                raise downloads.DownloadCanceled()

        with self.assertRaises(downloads.DownloadCanceled):
            asr_vulkan.load(Canceling(), "small")

    def test_it_says_so_when_no_card_answered(self):
        class NoCard:
            gpu_name = None

            def __init__(self, path):
                pass

        asr_vulkan.VulkanTranscriber = NoCard
        asr_vulkan.load(self.Downloader(), "small", self.statuses.append)
        self.assertIn("processor", self.statuses[-1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
