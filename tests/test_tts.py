# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Reading captions aloud: which captions, in which voice, and never captioning its own voice."""
import math
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ECHOSUB_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from echosub import config, tts  # noqa: E402

app = QApplication.instance() or QApplication([])
VOICES = [{"name": "Microsoft David", "languages": {0x09}, "token": "david"},
          {"name": "Microsoft Naayf", "languages": {0x01}, "token": "naayf"}]


class VoiceTest(unittest.TestCase):
    def test_a_voices_language_is_read_from_windows(self):
        self.assertEqual(tts.language_of("401;9"), {0x01, 0x09})
        self.assertEqual(tts.language_of("409"), {0x09})
        self.assertEqual(tts.language_of(""), set())

    def test_the_voice_for_each_language(self):
        self.assertEqual(tts.pick_voice(VOICES, "ar")["name"], "Microsoft Naayf")
        self.assertEqual(tts.pick_voice(VOICES, "en")["name"], "Microsoft David")
        self.assertIsNone(tts.pick_voice(VOICES, "fr"))

    def test_a_chosen_voice_wins(self):
        self.assertEqual(tts.pick_voice(VOICES, "ar", "Microsoft David")["name"], "Microsoft David")


class FakeSapi:
    def __init__(self):
        self.spoken = []
        self.Voice = self.Rate = self.Volume = None

    def Speak(self, text, flags):
        self.spoken.append((text, self.Voice, self.Rate, self.Volume))


class SpeakerTest(unittest.TestCase):
    def test_it_speaks_in_the_right_voice_and_says_when(self):
        sapi, states = FakeSapi(), []
        speaker = tts.Speaker(lambda: {"tts_rate": 3, "tts_volume": 70}, states.append)
        speaker._speak(sapi, VOICES, "مرحبا", "ar")
        self.assertEqual(sapi.spoken, [("مرحبا", "naayf", 3, 70)])
        self.assertEqual(states, [True, False], "the engine is told before and after")

    def test_a_language_without_a_voice_is_reported_once(self):
        sapi, missing = FakeSapi(), []
        speaker = tts.Speaker(dict, on_missing_voice=missing.append)
        speaker._speak(sapi, VOICES, "bonjour", "fr")
        speaker._speak(sapi, VOICES, "salut", "fr")
        self.assertEqual((sapi.spoken, missing), ([], ["fr"]))

    def test_when_captions_come_too_fast_the_oldest_are_skipped(self):
        speaker = tts.Speaker(dict)
        speaker._thread = object()  # no thread: only the queue is being looked at
        for n in range(5):
            speaker.say(f"caption {n}", "en")
        self.assertEqual([text for text, _ in speaker._waiting], ["caption 3", "caption 4"])


class FakeTray:
    def __init__(self):
        self.messages = []

    def showMessage(self, title, text, icon=None, timeout=0):
        self.messages.append(text)


class FakeSpeaker:
    def __init__(self):
        self.said = []

    def say(self, text, lang):
        self.said.append((text, lang))


class FakeApp(tts.SpeechMixin):
    def __init__(self, **cfg):
        self.cfg = dict(config.DEFAULTS, target_lang="ar", **cfg)
        self.tray = FakeTray()
        self._tts = FakeSpeaker()
        self.engine = type("Engine", (), {"mute_system_until": 0.0})()


class AppTest(unittest.TestCase):
    def test_off_by_default(self):
        self.assertFalse(config.DEFAULTS["tts_enabled"])
        app_ = FakeApp()
        app_.speak_final(1, "hello", "مرحبا", "en", "system")
        self.assertEqual(app_._tts.said, [])

    def test_the_translation_is_read_when_it_arrives(self):
        app_ = FakeApp(tts_enabled=True)
        app_.speak_final(1, "hello", None, "en", "system")
        self.assertEqual(app_._tts.said, [], "nothing to read until the translation is there")
        app_.speak_translation(1, "مرحبا")
        app_.speak_translation(1, "مرحبا")  # a second arrival is not read twice
        self.assertEqual(app_._tts.said, [("مرحبا", "ar")])

    def test_a_caption_already_in_the_language_is_read_at_once(self):
        app_ = FakeApp(tts_enabled=True)
        app_.speak_final(1, "مرحبا", "مرحبا", "ar", "system")
        self.assertEqual(app_._tts.said, [("مرحبا", "ar")])

    def test_or_the_original_words(self):
        app_ = FakeApp(tts_enabled=True, tts_what="original")
        app_.speak_final(1, "hello", None, "en", "system")
        self.assertEqual(app_._tts.said, [("hello", "en")])

    def test_your_own_words_are_not_read_back_unless_asked(self):
        app_ = FakeApp(tts_enabled=True)
        app_.speak_final(1, "hello", "hello", "en", "mic")
        self.assertEqual(app_._tts.said, [])
        app_.cfg["tts_who"] = "everyone"
        app_.speak_final(2, "hello", "hello", "en", "mic")
        self.assertEqual(len(app_._tts.said), 1)

    def test_the_pcs_sound_is_ignored_while_it_speaks(self):
        app_ = FakeApp()
        app_._tts_speaking(True)
        self.assertTrue(math.isinf(app_.engine.mute_system_until))
        app_._tts_speaking(False)
        self.assertGreater(app_.engine.mute_system_until, time.monotonic())
        self.assertLess(app_.engine.mute_system_until, time.monotonic() + 2, "and a moment after, for the echo")

    def test_a_missing_voice_is_explained(self):
        app_ = FakeApp(tts_enabled=True)
        app_._tts_missing_voice("fr")
        app_.speak_final(1, "x", "x", "fr", "system")
        self.assertTrue(any("Speech" in m for m in app_.tray.messages))


class SettingsTest(unittest.TestCase):
    def test_the_tab_keeps_the_choices(self):
        from echosub.settings_dialog import SettingsDialog

        dialog = SettingsDialog(dict(config.DEFAULTS, tts_enabled=True, tts_what="original", tts_who="everyone",
                                     tts_rate=-2, tts_volume=40))
        self.addCleanup(dialog.close)
        values = dialog.values()
        self.assertEqual([values[k] for k in ("tts_enabled", "tts_what", "tts_who", "tts_rate", "tts_volume")],
                         [True, "original", "everyone", -2, 40])


if __name__ == "__main__":
    unittest.main(verbosity=2)
