# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Captions for a live stream: a local page for OBS, off unless switched on."""
import json
import os
import sys
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ECHOSUB_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from echosub import config, stream_overlay as so  # noqa: E402

app = QApplication.instance() or QApplication([])
CFG = {"stream_lines": 2, "stream_font_size": 40, "stream_hide_after": 8, "stream_show_original": True}


class FeedTest(unittest.TestCase):
    def test_the_newest_captions_with_their_translation(self):
        feed = so.CaptionFeed()
        for n in range(4):
            feed.add(n, f"original {n}", None, "#FFF", when=100.0)
        feed.translate(3, "translated 3")
        lines = json.loads(feed.as_json(2, now=103.0))["lines"]
        self.assertEqual([line["text"] for line in lines], ["original 2", "translated 3"])
        self.assertEqual(lines[0]["age"], 3.0)


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.feed = so.CaptionFeed()
        self.server = so.StreamServer(self.feed, lambda: CFG, 0)
        self.addCleanup(self.server.stop)

    def get(self, path):
        with urllib.request.urlopen(self.server.url + path, timeout=5) as reply:
            return reply.read().decode("utf-8")

    def test_the_page_and_the_captions(self):
        self.feed.add(1, "good evening", "مساء الخير", "#FFD966")
        self.assertIn("captions.json", self.get(""))
        self.assertEqual(json.loads(self.get("captions.json"))["lines"][0]["text"], "مساء الخير")

    def test_only_this_pc_can_reach_it(self):
        self.assertEqual(self.server.httpd.server_address[0], "127.0.0.1")

    def test_nothing_else_is_served(self):
        for path in ("settings.json", "../", "favicon.ico"):
            with self.subTest(path=path), self.assertRaises(urllib.error.HTTPError):
                self.get(path)


class FakeTray:
    def __init__(self):
        self.messages = []

    def showMessage(self, title, text, icon=None, timeout=0):
        self.messages.append(text)


class FakeApp(so.StreamMixin):
    def __init__(self, **cfg):
        self.cfg = dict(config.DEFAULTS, **cfg)
        self.tray = FakeTray()


class AppTest(unittest.TestCase):
    def test_off_by_default_and_then_nothing_runs(self):
        self.assertFalse(config.DEFAULTS["stream_enabled"])
        app_ = FakeApp()
        app_.apply_stream_settings()
        self.assertIsNone(getattr(app_, "_stream_server", None))
        app_.stream_final(1, "a", "b", 0, "system")  # must not fail with nothing running

    def test_switched_on_it_serves_and_off_it_stops(self):
        app_ = FakeApp(stream_enabled=True, stream_port=0)
        app_.apply_stream_settings()
        self.addCleanup(app_.stop_stream)
        app_.stream_final(1, "hello", None, 1, "system")
        app_.stream_translation(1, "مرحبا")
        with urllib.request.urlopen(app_._stream_server.url + "captions.json", timeout=5) as reply:
            line = json.loads(reply.read())["lines"][0]
        self.assertEqual(line["text"], "مرحبا")
        self.assertEqual(line["color"], config.DEFAULTS["speaker_colors"][1], "each speaker keeps their colour")
        app_.cfg["stream_enabled"] = False
        app_.apply_stream_settings()
        self.assertIsNone(app_._stream_server)

    def test_a_port_in_use_is_explained(self):
        other = so.StreamServer(so.CaptionFeed(), lambda: CFG, 0)
        self.addCleanup(other.stop)
        app_ = FakeApp(stream_enabled=True, stream_port=other.port)
        app_.apply_stream_settings()
        self.assertTrue(any("port" in m for m in app_.tray.messages))


class SettingsTest(unittest.TestCase):
    def test_the_tab_keeps_the_choices_and_shows_the_address(self):
        from echosub.settings_dialog import SettingsDialog

        dialog = SettingsDialog(dict(config.DEFAULTS, stream_enabled=True, stream_port=9001, stream_lines=3))
        self.addCleanup(dialog.close)
        values = dialog.values()
        self.assertEqual((values["stream_enabled"], values["stream_port"], values["stream_lines"]), (True, 9001, 3))
        self.assertEqual(dialog.stream_address.text(), "http://127.0.0.1:9001/")


if __name__ == "__main__":
    unittest.main(verbosity=2)
