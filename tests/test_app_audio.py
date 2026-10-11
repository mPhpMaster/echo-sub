# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Listening to one program only, and falling back to the whole PC when it is not running."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ECHOSUB_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from echosub import app_audio, audio, config  # noqa: E402

app = QApplication.instance() or QApplication([])


class FakeProc:
    def __init__(self, pid, name, ppid):
        self.info = {"pid": pid, "name": name, "ppid": ppid}


class RootTest(unittest.TestCase):
    def setUp(self):
        real = app_audio.psutil.process_iter
        self.addCleanup(lambda: setattr(app_audio.psutil, "process_iter", real))
        app_audio.psutil.process_iter = lambda attrs=None: [
            FakeProc(10, "explorer.exe", 1), FakeProc(20, "Discord.exe", 10), FakeProc(21, "Discord.exe", 20),
            FakeProc(22, "Discord.exe", 20)]

    def test_the_top_process_so_its_helpers_count_too(self):
        self.assertEqual(app_audio.find_root_pid("discord.exe"), 20)

    def test_not_running(self):
        self.assertIsNone(app_audio.find_root_pid("Spotify.exe"))
        self.assertIsNone(app_audio.find_root_pid(""))


class FakeLoopback:
    started = 0

    def __init__(self, *args, **kw):
        self.using_fallback = False

    def start(self):
        FakeLoopback.started += 1


class FallbackTest(unittest.TestCase):
    def setUp(self):
        self.statuses = []
        saved = (audio.LoopbackCapture, app_audio.available, app_audio.find_root_pid, app_audio.AppCapture.start)
        self.addCleanup(lambda: (setattr(audio, "LoopbackCapture", saved[0]), setattr(app_audio, "available", saved[1]),
                                 setattr(app_audio, "find_root_pid", saved[2]),
                                 setattr(app_audio.AppCapture, "start", saved[3])))
        app_audio.available = lambda: True

    def test_a_program_that_is_not_running_means_the_whole_pc_for_now(self):
        app_audio.find_root_pid = lambda name: None
        cfg = dict(config.DEFAULTS, audio_app="Discord.exe")
        real_loopback = audio.LoopbackCapture
        audio.LoopbackCapture = FakeLoopback
        capture = app_audio.make_capture(cfg, self.statuses.append)
        audio.LoopbackCapture = real_loopback
        self.assertIsInstance(capture, FakeLoopback)
        self.assertEqual(capture.waiting_for_app, "Discord.exe")
        self.assertIn("not running", self.statuses[-1])
        self.assertFalse(app_audio.should_switch(capture, cfg), "still not running: stay")
        app_audio.find_root_pid = lambda name: 1234
        self.assertTrue(app_audio.should_switch(capture, cfg), "it started: go back to it")

    def test_nothing_chosen_changes_nothing(self):
        capture = FakeLoopback()
        self.assertIsNone(app_audio.should_switch(capture, dict(config.DEFAULTS)))
        self.assertEqual(config.DEFAULTS["audio_app"], "", "off by default: everything the PC plays")
        self.assertIn("audio_app", config.ENGINE_KEYS)


class SettingsTest(unittest.TestCase):
    def test_the_field(self):
        from echosub.settings_audio_app import EVERYTHING, app_field, app_value

        real = app_audio.programs_with_sound
        app_audio.programs_with_sound = lambda: ["Discord.exe", "chrome.exe"]
        self.addCleanup(lambda: setattr(app_audio, "programs_with_sound", real))
        field = app_field(dict(config.DEFAULTS, audio_app="Spotify.exe"))
        self.assertEqual(app_value(field), "Spotify.exe", "a program not playing now is still kept")
        field.setCurrentIndex(field.findText(EVERYTHING))
        self.assertEqual(app_value(field), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
