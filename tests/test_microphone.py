# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Captioning the microphone beside what the PC plays: its own colour, label and commands."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ECHOSUB_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from echosub import config, engine  # noqa: E402
from echosub.engine_sources import MICROPHONE, SYSTEM  # noqa: E402
from echosub.overlay import CaptionOverlay  # noqa: E402
from echosub.settings_dialog import SettingsDialog  # noqa: E402

app = QApplication.instance() or QApplication([])
SR = engine.SR


def make_engine(**overrides):
    cfg = dict(config.DEFAULTS, translator="none", speaker_detection=True, arabic_diacritics="off")
    cfg.update(overrides)
    events = {"final": [], "partial": []}
    e = engine.CaptionEngine(
        cfg,
        on_partial=lambda text, tr, lang, source=SYSTEM: events["partial"].append((text, source)),
        on_final=lambda sid, text, tr, lang, spk, source=SYSTEM: events["final"].append((text, spk, source)),
        on_status=lambda text: None, on_error=lambda text: None)
    e.speakers = None
    e._transcribe = lambda seg, language, final, prompt=None: ("hello from a voice", "en", 0.95, None)
    return e, events


class SourceTaggingTest(unittest.TestCase):
    def test_a_caption_says_which_source_it_came_from(self):
        e, events = make_engine()
        e._finalize(np.zeros(SR, dtype=np.float32), [{"start": 0, "end": SR}], 0, SYSTEM)
        e._finalize(np.zeros(SR, dtype=np.float32), [{"start": 0, "end": SR}], 0, MICROPHONE)
        self.assertEqual([source for *_, source in events["final"]], [SYSTEM, MICROPHONE])

    def test_the_microphone_is_not_run_through_speaker_detection(self):
        """It is the person at this PC: there is nobody to tell apart, and it saves the work."""
        e, events = make_engine()
        calls = []
        e._speaker_runs = lambda seg, regions: calls.append(regions) or [(0, len(seg), 3)]
        e._finalize(np.zeros(SR, dtype=np.float32), [{"start": 0, "end": SR}], 0, MICROPHONE)
        self.assertEqual(calls, [], "speaker detection ran on the microphone")
        self.assertEqual(events["final"][0][1], None, "the microphone was given a speaker number")

    def test_live_text_keeps_its_source(self):
        e, events = make_engine()
        e._partial(np.zeros(SR, dtype=np.float32), MICROPHONE)
        self.assertEqual(events["partial"], [("hello from a voice", MICROPHONE)])


class CaptureTest(unittest.TestCase):
    def test_the_microphone_is_only_opened_when_it_is_switched_on(self):
        opened = []
        e, _ = make_engine(mic_enabled=False)
        e._open_microphone()
        self.assertIsNone(e._mic_capture)

        e, _ = make_engine(mic_enabled=True, mic_device="Microphone (test)")
        from echosub import audio

        real = audio.LoopbackCapture
        audio.LoopbackCapture = lambda device, seconds, folder, kind="loopback": opened.append(
            (device, kind)) or type("Cap", (), {"start": lambda self: None, "device_name": device})()
        try:
            e._open_microphone()
        finally:
            audio.LoopbackCapture = real
        self.assertEqual(opened, [("Microphone (test)", "input")])

    def test_a_microphone_that_cannot_be_opened_does_not_stop_the_captions(self):
        from echosub import audio

        e, _ = make_engine(mic_enabled=True)
        messages = []
        e.on_status = messages.append
        real = audio.LoopbackCapture
        audio.LoopbackCapture = lambda *a, **k: (_ for _ in ()).throw(OSError("no microphone"))
        try:
            e._open_microphone()
        finally:
            audio.LoopbackCapture = real
        self.assertIsNone(e._mic_capture)
        self.assertTrue(any("microphone" in m.lower() for m in messages), messages)


class CaptionBoxTest(unittest.TestCase):
    def _overlay(self, **overrides):
        cfg = dict(config.DEFAULTS, caption_animation="none", mic_color="#8AD7FF", mic_label="You")
        cfg.update(overrides)
        overlay = CaptionOverlay(cfg, lambda p: None, lambda g: None, lambda: None)
        overlay.show()
        self.addCleanup(overlay.close)
        return overlay, cfg

    def test_the_microphone_caption_is_in_its_own_colour(self):
        overlay, cfg = self._overlay()
        overlay.add_final(1, "what the PC played", "ترجمة", "en", 0, SYSTEM)
        overlay.add_final(2, "what I said", "ترجمة", "en", None, MICROPHONE)
        app.processEvents()
        colours = [line.translated._color.name().upper() for line in overlay.lines]
        self.assertIn(cfg["mic_color"].upper(), colours, colours)

    def test_the_label_says_who_is_talking(self):
        overlay, _ = self._overlay(mic_label="Mohammad")
        overlay.add_final(1, "what I said", "ترجمة", "en", None, MICROPHONE)
        app.processEvents()
        badge = overlay.lines[0].original._badge
        self.assertIsNotNone(badge, "the microphone caption has no label")
        self.assertIn("Mohammad", badge.text)
        self.assertTrue(badge.prominent)

    def test_the_label_sits_where_the_settings_put_it(self):
        """It used to be forced above the words; it now follows the label position like any other."""
        for where in ("before", "after", "above"):
            with self.subTest(where=where):
                overlay, _ = self._overlay(mic_label="Mohammad", original_label_position=where)
                overlay.add_final(1, "what I said", "ترجمة", "en", None, MICROPHONE)
                app.processEvents()
                self.assertEqual(overlay.lines[0].original._badge.position, where)

    def test_microphone_and_system_captions_are_not_merged_into_one_line(self):
        overlay, _ = self._overlay()
        overlay.add_final(1, "the video says something", "ترجمة", "en", 0, SYSTEM)
        overlay.add_final(2, "and I answer it", "ترجمة", "en", 0, MICROPHONE)
        app.processEvents()
        self.assertEqual(len(overlay.entries), 2, "the two voices ended up on one line")


class SettingsTest(unittest.TestCase):
    def test_the_microphone_is_off_until_it_is_switched_on(self):
        self.assertFalse(config.DEFAULTS["mic_enabled"])
        self.assertFalse(SettingsDialog(dict(config.DEFAULTS)).values()["mic_enabled"])

    def test_the_settings_round_trip(self):
        cfg = dict(config.DEFAULTS, mic_enabled=True, mic_label="Me", mic_color="#FF00FF", mic_commands=False)
        values = SettingsDialog(cfg).values()
        self.assertTrue(values["mic_enabled"])
        self.assertEqual(values["mic_label"], "Me")
        self.assertEqual(values["mic_color"].upper(), "#FF00FF")
        self.assertFalse(values["mic_commands"])

    def test_changing_the_microphone_restarts_the_engine(self):
        self.assertIn("mic_enabled", config.ENGINE_KEYS)
        self.assertIn("mic_device", config.ENGINE_KEYS)

    def test_the_controls_follow_the_checkbox(self):
        dialog = SettingsDialog(dict(config.DEFAULTS, mic_enabled=False))
        self.assertFalse(dialog.mic_device.isEnabled())
        dialog.mic_enabled.setChecked(True)
        self.assertTrue(dialog.mic_device.isEnabled())


if __name__ == "__main__":
    unittest.main(verbosity=2)
