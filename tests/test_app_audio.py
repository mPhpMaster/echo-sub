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

from echosub import app_audio, app_windows, audio, config  # noqa: E402

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
        self.assertEqual(capture.waiting_for, ("Discord.exe", ""))
        self.assertIn("not running", self.statuses[-1])
        self.assertFalse(app_audio.should_switch(capture, cfg), "still not running: stay")
        app_audio.find_root_pid = lambda name: 1234
        self.assertTrue(app_audio.should_switch(capture, cfg), "it started: go back to it")

    def test_nothing_chosen_changes_nothing(self):
        capture = FakeLoopback()
        self.assertIsNone(app_audio.should_switch(capture, dict(config.DEFAULTS)))
        self.assertEqual(config.DEFAULTS["audio_app"], "", "off by default: everything the PC plays")
        self.assertIn("audio_app", config.ENGINE_KEYS)
        self.assertIn("audio_window", config.ENGINE_KEYS)
        self.assertEqual(config.DEFAULTS["audio_window"], "")

    def test_a_window_that_is_not_open_means_the_whole_pc_until_it_opens(self):
        found = {"pid": None}
        real = app_windows.find_pid
        self.addCleanup(lambda: setattr(app_windows, "find_pid", real))
        app_windows.find_pid = lambda title, exe="", saved_pid=0: found["pid"]
        cfg = dict(config.DEFAULTS, audio_app="vlc.exe", audio_window="Song - VLC", audio_window_pid=55)
        real_loopback = audio.LoopbackCapture
        audio.LoopbackCapture = FakeLoopback
        capture = app_audio.make_capture(cfg, self.statuses.append)
        audio.LoopbackCapture = real_loopback
        self.assertIsInstance(capture, FakeLoopback)
        self.assertIn("is not open", self.statuses[-1])
        self.assertIn("Song - VLC", self.statuses[-1])
        self.assertFalse(app_audio.should_switch(capture, cfg))
        found["pid"] = 77
        self.assertTrue(app_audio.should_switch(capture, cfg), "the window opened: go back to it")
        self.assertIsNone(app_audio.should_switch(capture, dict(cfg, audio_window="Other")),
                          "another choice: the settings change reopens the sound anyway")


class WindowTest(unittest.TestCase):
    WINDOWS = [app_windows.Window("Song A - VLC media player", 30, "vlc.exe"),
               app_windows.Window("Movie - VLC media player", 31, "vlc.exe"),
               app_windows.Window("Song A - Notes", 40, "notepad.exe")]

    def find(self, title, exe="", saved=0, running=None):
        running = running or {}
        return app_windows.find_pid(title, exe, saved, windows=self.WINDOWS, exe_of=lambda pid: running.get(pid, ""))

    def test_the_same_title_first(self):
        self.assertEqual(self.find("Movie - VLC media player", "vlc.exe"), 31)

    def test_part_of_the_title(self):
        self.assertEqual(self.find("movie", "VLC.exe"), 31)

    def test_only_that_program(self):
        self.assertEqual(self.find("Song A", "notepad.exe"), 40)
        self.assertIsNone(self.find("Song A", "spotify.exe"))

    def test_the_title_changed_but_the_program_is_still_running(self):
        self.assertEqual(self.find("Song B - VLC media player", "vlc.exe", 30, {30: "vlc.exe"}), 30)
        self.assertIsNone(self.find("Song B - VLC media player", "vlc.exe", 30), "it closed")
        self.assertIsNone(self.find("Song B", "vlc.exe", 30, {30: "chrome.exe"}), "its number went to another program")

    def test_nothing_chosen(self):
        self.assertIsNone(self.find(""))

    def test_the_real_windows_can_be_listed(self):
        for w in app_windows.open_windows():
            self.assertTrue(w.title)
            self.assertNotEqual(w.pid, os.getpid())

    def test_the_program_copy_behind_a_window(self):
        import psutil

        top = psutil.Process(app_windows.instance_root(os.getpid()))
        self.assertEqual(top.name(), psutil.Process().name(), "the same program")
        self.assertNotEqual((top.parent().name() if top.parent() else ""), top.name(), "its own top copy")
        self.assertEqual(app_windows.instance_root(999999999), 999999999, "gone: left as it is")


class SettingsTest(unittest.TestCase):
    def test_the_field(self):
        from echosub.settings_audio_app import EVERYTHING, app_field

        real = app_audio.programs_with_sound
        app_audio.programs_with_sound = lambda: ["Discord.exe", "chrome.exe"]
        self.addCleanup(lambda: setattr(app_audio, "programs_with_sound", real))
        field = app_field(dict(config.DEFAULTS, audio_app="Spotify.exe"))
        self.assertEqual(field.values()["audio_app"], "Spotify.exe", "a program not playing now is still kept")
        field.field.setCurrentIndex(field.field.findText(EVERYTHING))
        self.assertEqual(field.values(), {"audio_app": "", "audio_window": "", "audio_window_pid": 0})
        field.field.setEditText("Game.exe")
        self.assertEqual(field.values()["audio_app"], "Game.exe", "a typed file name")

    def test_a_window(self):
        from echosub import settings_audio_app as ui

        saved = app_audio.programs_with_sound, app_windows.open_windows, app_windows.window_in_front
        self.addCleanup(lambda: (setattr(app_audio, "programs_with_sound", saved[0]),
                                 setattr(app_windows, "open_windows", saved[1]),
                                 setattr(app_windows, "window_in_front", saved[2])))
        app_audio.programs_with_sound = lambda: ["vlc.exe"]
        app_windows.open_windows = lambda: [app_windows.Window("Movie - VLC", 31, "vlc.exe")]
        field = ui.app_field(dict(config.DEFAULTS, audio_app="vlc.exe", audio_window="Movie - VLC",
                                  audio_window_pid=12))
        self.assertEqual(field.values(), {"audio_app": "vlc.exe", "audio_window": "Movie - VLC",
                                          "audio_window_pid": 31}, "the same window, open now under a new number")
        field = ui.app_field(dict(config.DEFAULTS, audio_app="game.exe", audio_window="Closed game",
                                  audio_window_pid=5))
        self.assertEqual(field.values()["audio_window"], "Closed game", "a window not open now is still kept")
        self.assertIn("Window: Closed game", field.field.currentText())
        app_windows.window_in_front = lambda: app_windows.Window("Movie - VLC", 31, "vlc.exe")
        field._start_pick()
        self.assertFalse(field.pick.isEnabled())
        for _ in range(ui.PICK_SECONDS):
            field._tick()
        self.assertTrue(field.pick.isEnabled())
        self.assertEqual(field.values()["audio_window"], "Movie - VLC", "picked the window in front")
        self.assertEqual(field.values()["audio_window_pid"], 31)
        self.assertTrue(ui.window_text("x" * 100, "a.exe").endswith("… — a.exe"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
