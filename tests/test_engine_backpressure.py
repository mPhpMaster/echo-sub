# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""What the engine does when it can't keep up: live text, backlogs and light mode.

These tests use stand-in models, so they need no GPU, no downloads and no sound card.
Run them with:  .venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""
import os
import queue
import sys
import threading
import time
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ECHOSUB_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data"))

from echosub import config, engine  # noqa: E402

SR = engine.SR


class SlowTranslator:
    """Stands in for a translator that is slower than the speaker."""

    streaming = True

    def __init__(self, delay=0.3):
        self.delay = delay
        self.calls = []

    def translate(self, text, src, tgt):
        self.calls.append(text)
        time.sleep(self.delay)
        return "[" + tgt + "] " + text


def make_engine(**cfg_overrides):
    """An engine with no real models, ready for its internals to be driven directly."""
    cfg = dict(config.DEFAULTS, target_lang="ar", source_lang="auto", translator="nllb-600m",
               speaker_detection=False, arabic_diacritics="off", audio_device="test")
    cfg.update(cfg_overrides)
    events = {"partial": [], "final": [], "translation": [], "status": [], "error": []}
    e = engine.CaptionEngine(
        cfg,
        on_partial=lambda text, translated, lang: events["partial"].append((text, translated, lang)),
        on_final=lambda sid, text, tr, lang, spk: events["final"].append((sid, text, tr)),
        on_translation=lambda sid, text: events["translation"].append((sid, text)),
        on_status=lambda text: events["status"].append(text),
        on_error=lambda text: events["error"].append(text))
    e.speakers = None
    return e, events


def run_worker(e, seconds=2.0, until=None):
    """Runs the translation thread for a while (or until `until()` is true)."""
    thread = threading.Thread(target=e._translation_worker, daemon=True)
    thread.start()
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline and not (until and until()):
        time.sleep(0.02)
    e._stop.set()
    thread.join(timeout=2)
    e._stop.clear()


class LiveTextTest(unittest.TestCase):
    """Live ("partial") text must never make the recognition loop wait for the translator."""

    def setUp(self):
        self.e, self.events = make_engine()
        self.e.translator = SlowTranslator(0.4)
        self.e._transcribe = lambda seg, language, final, prompt=None: ("hello there", "en", 0.9, None)

    def test_partial_returns_without_waiting_for_the_translation(self):
        started = time.monotonic()
        self.e._partial(np.zeros(SR, dtype=np.float32))
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 0.1, "the recognition loop waited for the translator")
        self.assertEqual(self.events["partial"], [("hello there", None, "en")])
        self.assertEqual(self.e.translator.calls, [], "translation must not run on the recognition thread")

    def test_the_translation_arrives_later_on_the_translation_thread(self):
        self.e._partial(np.zeros(SR, dtype=np.float32))
        run_worker(self.e, 2.0, until=lambda: len(self.events["partial"]) > 1)
        self.assertEqual(self.events["partial"][-1], ("hello there", "[ar] hello there", "en"))

    def test_only_the_newest_live_text_is_translated(self):
        for text in ("one", "one two", "one two three"):
            self.e._transcribe = lambda seg, language, final, prompt=None, t=text: (t, "en", 0.9, None)
            self.e._partial(np.zeros(SR, dtype=np.float32))
        run_worker(self.e, 2.0, until=lambda: any(p[1] for p in self.events["partial"]))
        self.assertEqual(self.e.translator.calls, ["one two three"], "stale live text was translated")

    def test_a_finished_caption_cancels_the_live_translation(self):
        self.e._partial(np.zeros(SR, dtype=np.float32))
        self.e._finalize(np.zeros(SR, dtype=np.float32), [{"start": 0, "end": SR}], 0)
        run_worker(self.e, 1.0)
        self.assertTrue(all(translated is None for _, translated, _ in self.events["partial"]),
                        "a translation of outdated live text was shown after the caption")

    def test_pausing_cancels_the_live_translation(self):
        self.e._partial(np.zeros(SR, dtype=np.float32))
        self.e._clear_pending_partial()
        run_worker(self.e, 0.8)
        self.assertEqual(self.e.translator.calls, [])


class TranslationBacklogTest(unittest.TestCase):
    """A translator slower than the speaker must not push captions minutes behind."""

    def test_queue_is_bounded_and_the_oldest_captions_keep_their_original_text(self):
        e, events = make_engine()
        e.translator = SlowTranslator(5.0)
        for i in range(1, 16):
            e._queue_translation(i, f"sentence {i}", "en")
            self.assertLessEqual(e._translations.qsize(), engine.MAX_PENDING_TRANSLATIONS)
        shown = [sid for sid, _ in events["translation"]]
        self.assertEqual(shown, sorted(shown), "captions lost their order")
        self.assertEqual(events["translation"][0], (1, "sentence 1"),
                         "the oldest caption should be shown in its original language")
        self.assertEqual(len(shown), 15 - engine.MAX_PENDING_TRANSLATIONS)
        self.assertTrue(any("behind" in s for s in events["status"]), "the user was not told")

    def test_nothing_is_dropped_when_the_translator_keeps_up(self):
        e, events = make_engine()
        e.translator = SlowTranslator(0.0)
        for i in range(1, 6):
            e._queue_translation(i, f"sentence {i}", "en")
        run_worker(e, 2.0, until=lambda: len(events["translation"]) == 5)
        self.assertEqual([sid for sid, _ in events["translation"]], [1, 2, 3, 4, 5])
        self.assertTrue(all(text.startswith("[ar]") for _, text in events["translation"]))


class FakeCapture:
    """Feeds noise to the engine loop: all at once, or chunk by chunk like a real sound card."""

    def __init__(self, seconds, chunk=0.05, live=False):
        self.queue = queue.Queue()
        self.device_name = "test"
        self.last_audio_time = time.monotonic()
        self.chunk = chunk
        self.stop = threading.Event()
        step = int(SR * chunk)
        rng = np.random.default_rng(1)
        self.block = rng.normal(0, 0.05, step).astype(np.float32)
        if live:
            threading.Thread(target=self._feed, daemon=True).start()
        else:
            for _ in range(int(seconds / chunk)):
                self.queue.put(self.block)

    def _feed(self):
        while not self.stop.is_set():
            self.queue.put(self.block)
            self.last_audio_time = time.monotonic()
            time.sleep(self.chunk / 2)  # twice as fast as real time, to push the loop harder

    def take(self):
        chunks = []
        while True:
            try:
                chunks.append(self.queue.get_nowait())
            except queue.Empty:
                return chunks

    def is_healthy(self):
        return True


class CaptureQueueTest(unittest.TestCase):
    """The sound card keeps sending audio even when the engine is stuck; it must not pile up."""

    def _capture(self):
        from echosub import audio

        cap = audio.LoopbackCapture.__new__(audio.LoopbackCapture)
        cap.queue = queue.Queue()
        cap.last_audio_time = 0.0
        cap.dropped_sec = 0.0
        cap._queued_sec = 0.0
        cap._last_drop_log = 0.0
        cap._channels = 1
        cap._resampler = type("Passthrough", (), {"resample_chunk": staticmethod(lambda pcm: pcm)})()
        return cap, audio

    def test_old_audio_is_dropped_once_the_limit_is_reached(self):
        cap, audio = self._capture()
        block = np.zeros(int(SR * 0.05), dtype=np.int16).tobytes()
        for _ in range(int(120 / 0.05)):  # two minutes of audio that nobody reads
            cap._callback(block, 0, None, None)
        self.assertLessEqual(cap._queued_sec, audio.MAX_QUEUED_SEC + 0.1)
        self.assertGreater(cap.dropped_sec, 50)
        self.assertLessEqual(cap.queue.qsize() * 0.05, audio.MAX_QUEUED_SEC + 0.1)

    def test_nothing_is_dropped_when_the_engine_reads_the_audio(self):
        cap, _ = self._capture()
        block = np.zeros(int(SR * 0.05), dtype=np.int16).tobytes()
        for i in range(400):
            cap._callback(block, 0, None, None)
            if i % 10 == 0:
                cap.take()
        cap.take()
        self.assertEqual(cap.dropped_sec, 0.0)
        self.assertAlmostEqual(cap._queued_sec, 0.0, places=6)


class RecognitionBacklogTest(unittest.TestCase):
    """When recognition is slower than the speaker, audio must not pile up for ever."""

    def _engine_with_slow_recognition(self, seconds_of_audio, asr_delay):
        e, events = make_engine(max_segment_sec=5.0, silence_sec=0.8, show_partial=False)
        e._capture = FakeCapture(seconds_of_audio)
        e._vad = lambda buf: [{"start": 0, "end": len(buf)}]  # "everything is speech"

        def transcribe(seg, language, final, prompt=None):
            time.sleep(asr_delay)
            return (f"segment of {len(seg) / SR:.1f} s", "en", 0.9, None)

        e._transcribe = transcribe
        return e, events

    def test_audio_is_skipped_instead_of_falling_further_behind(self):
        e, events = self._engine_with_slow_recognition(90, 0.5)
        thread = threading.Thread(target=e._loop, daemon=True)
        thread.start()
        time.sleep(6)
        e._stop.set()
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive(), "the recognition loop did not stop")
        ids = [sid for sid, *_ in events["final"]]
        self.assertEqual(ids, sorted(ids), "captions came out in the wrong order")
        self.assertTrue(events["final"], "no captions at all")
        lengths = [float(text.split()[2]) for _, text, _ in events["final"]]
        limit = max(20.0, 2 * e.cfg["max_segment_sec"]) + 1
        self.assertTrue(all(length <= limit for length in lengths),
                        f"a caption covered more audio than the backlog limit: {lengths}")
        self.assertTrue(any("behind" in s for s in events["status"]), "the user was not told")

    def test_speech_regions_still_match_the_audio_after_skipping(self):
        """After old audio is dropped, the engine must not cut captions with the old positions."""
        e, events = self._engine_with_slow_recognition(120, 0.4)
        e._vad = lambda buf: [{"start": 0, "end": len(buf)}]
        real_finalize = e._finalize
        problems = []

        def finalize(seg, speech, offset):
            if len(seg) == 0 or any(region["end"] - offset > len(seg) for region in speech):
                problems.append((len(seg), speech, offset))
            return real_finalize(seg, speech, offset)

        e._finalize = finalize
        thread = threading.Thread(target=e._loop, daemon=True)
        thread.start()
        time.sleep(5)
        e._stop.set()
        thread.join(timeout=5)
        self.assertEqual(problems, [], "a caption was cut using speech positions of audio that was dropped")
        self.assertTrue(events["final"], "no captions at all")

    def test_speech_detection_is_not_rerun_for_every_chunk(self):
        e, events = make_engine(max_segment_sec=30.0, silence_sec=30.0, show_partial=False)
        e._capture = FakeCapture(60, live=True)
        calls = []
        e._vad = lambda buf: (calls.append(time.monotonic()), [{"start": 0, "end": len(buf) // 2}])[1]
        e._transcribe = lambda seg, language, final, prompt=None: ("text", "en", 0.9, None)
        thread = threading.Thread(target=e._loop, daemon=True)
        started = time.monotonic()
        thread.start()
        time.sleep(2)
        e._stop.set()
        e._capture.stop.set()
        thread.join(timeout=5)
        elapsed = time.monotonic() - started
        allowed = elapsed / engine.VAD_INTERVAL_SEC + 2
        self.assertLessEqual(len(calls), allowed,
                             f"speech detection ran {len(calls)} times in {elapsed:.1f} s")
        self.assertGreater(len(calls), 1, "speech detection did not run at all")


class LightModeTest(unittest.TestCase):
    def test_a_heavy_model_is_swapped_for_a_fast_one(self):
        e, _ = make_engine(whisper_model="large-v3-turbo", light_mode=True)
        self.assertEqual(e.whisper_model(), engine.LIGHT_WHISPER_MODEL)
        self.assertFalse(e._live_text_enabled())

    def test_the_users_own_settings_come_back_when_it_is_off(self):
        e, _ = make_engine(whisper_model="large-v3-turbo", light_mode=False, show_partial=True)
        self.assertEqual(e.whisper_model(), "large-v3-turbo")
        self.assertTrue(e._live_text_enabled())

    def test_a_model_that_is_already_small_is_kept(self):
        e, _ = make_engine(whisper_model="base", light_mode=True)
        self.assertEqual(e.whisper_model(), "base")

    def test_light_mode_reloads_the_engine(self):
        self.assertIn("light_mode", config.ENGINE_KEYS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
