# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""EchoSub's own CPU, memory, graphics-card and disk use, and where it is shown."""
import os
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ECHOSUB_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data"))

from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget  # noqa: E402

from echosub import config, usage, usage_app, usage_ui  # noqa: E402

app = QApplication.instance() or QApplication([])
SAMPLE = usage.Sample(cpu=12.4, ram=1.4 * 2**30, gpu=35.0, vram=1.9 * 2**30, disk=0.2 * 2**20)


class SummaryTest(unittest.TestCase):
    def test_one_short_line(self):
        self.assertEqual(usage.summary(SAMPLE), "CPU 12% · RAM 1.4 GB · GPU 35% · VRAM 1.9 GB · Disk 205 KB/s")

    def test_without_graphics_counters_the_card_is_left_out(self):
        text = usage.summary(SAMPLE._replace(gpu=None, vram=None))
        self.assertNotIn("GPU", text)
        self.assertIn("CPU 12%", text)

    def test_nothing_measured_yet(self):
        self.assertEqual(usage.summary(None), "")


class TrayTextTest(unittest.TestCase):
    def test_state_figures_then_detail(self):
        self.assertEqual(usage_app.tray_text("EchoSub — Listening", "CPU 1%", "Ready"),
                         "EchoSub — Listening\nCPU 1%\nReady")

    def test_a_long_detail_gives_way_to_the_figures(self):
        figures = usage.summary(SAMPLE)
        text = usage_app.tray_text("EchoSub — Listening", figures, "x" * 100)
        self.assertLessEqual(len(text), usage_app.TOOLTIP_MAX)
        self.assertIn(figures, text)


class SamplerTest(unittest.TestCase):
    def test_this_process_is_measured(self):
        sampler = usage.Sampler(gpu=type("NoGpu", (), {"read": lambda self, pids: (None, None)})())
        sampler.sample()
        stop = time.monotonic() + 0.6

        def busy():
            while time.monotonic() < stop:
                pass

        worker = threading.Thread(target=busy)
        worker.start()
        worker.join()
        sample = sampler.sample()
        self.assertGreater(sample.cpu, 0)
        self.assertGreater(sample.ram, 10 * 2**20)
        self.assertIsNone(sample.gpu)

    def test_the_graphics_counters_answer_on_windows(self):
        counters = usage.GpuCounters()
        if not counters.ok:
            self.skipTest("this Windows has no graphics-card counters")
        gpu, vram = counters.read([os.getpid()])
        counters.close()
        self.assertGreaterEqual(gpu, 0)
        self.assertGreaterEqual(vram, 0)


class WindowTest(unittest.TestCase):
    def test_bars_and_figures(self):
        window = usage_ui.UsageWindow(on_top=True)
        self.addCleanup(window.close)
        window.total_ram, window.total_vram = 16 * 2**30, 6 * 2**30
        window.show_sample(SAMPLE)
        self.assertEqual(window.bars["cpu"].value(), 12)
        self.assertEqual(window.values["vram"].text(), "1.9 GB of 6.0 GB")
        self.assertEqual(window.bars["ram"].value(), 9)

    def test_staying_on_top_is_a_choice(self):
        seen = []
        window = usage_ui.UsageWindow(on_top=True)
        self.addCleanup(window.close)
        window.on_top_changed.connect(seen.append)
        window.on_top.setChecked(False)
        self.assertEqual(seen, [False])


class FakeTray:
    def __init__(self):
        self.tip = ""

    def setToolTip(self, text):
        self.tip = text


class FakeOverlay:
    def __init__(self):
        self.widget = QWidget()
        self.content_layout = QVBoxLayout(self.widget)
        self.refreshed = 0

    def isVisible(self):
        return True

    def refresh(self):
        self.refreshed += 1


class FakeApp(usage_app.UsageMixin):
    def __init__(self, **cfg):
        self.cfg = dict(config.DEFAULTS, **cfg)
        self.tray = FakeTray()
        self.overlay = FakeOverlay()
        self.saved = 0

    def _save(self):
        self.saved += 1


class AppTest(unittest.TestCase):
    def setUp(self):
        monitor = usage.shared()
        real = monitor.latest
        monitor.latest = SAMPLE
        self.addCleanup(lambda: setattr(monitor, "latest", real))

    def app(self, **cfg):
        app_ = FakeApp(**cfg)
        app_.init_usage()
        app_._usage_timer.stop()
        self.addCleanup(lambda: app_.set_usage_window(False))
        return app_

    def test_pointing_at_the_tray_icon_shows_the_figures(self):
        app_ = self.app()
        app_._usage_tick()
        self.assertIn("CPU 12%", app_.tray.tip)

    def test_the_caption_box_line_only_when_asked_for(self):
        app_ = self.app()
        app_._usage_tick()
        self.assertTrue(app_._usage_line.isHidden())
        app_.cfg["usage_line"] = True
        app_._usage_tick()
        self.assertFalse(app_._usage_line.isHidden())
        self.assertIn("GPU 35%", app_._usage_line.text())

    def test_the_window_opens_closes_and_is_remembered(self):
        app_ = self.app()
        app_.set_usage_window(True)
        self.assertIsNotNone(app_._usage_window)
        self.assertTrue(app_.cfg["usage_window"])
        app_._usage_window.close()  # its own X button
        self.assertIsNone(app_._usage_window)
        self.assertFalse(app_.cfg["usage_window"])

    def test_off_by_default(self):
        self.assertFalse(config.DEFAULTS["usage_line"])
        self.assertFalse(config.DEFAULTS["usage_window"])
        self.assertTrue(config.DEFAULTS["usage_window_on_top"])


class SettingsTest(unittest.TestCase):
    def test_the_settings_keep_the_choices_and_show_the_figures(self):
        from echosub.settings_dialog import SettingsDialog

        dialog = SettingsDialog(dict(config.DEFAULTS, usage_line=True, usage_window=True, usage_window_on_top=False))
        self.addCleanup(dialog.close)
        values = dialog.values()
        self.assertEqual((values["usage_line"], values["usage_window"], values["usage_window_on_top"]),
                         (True, True, False))
        self.assertTrue(dialog.findChildren(usage_ui.UsageStrip))


class OpenSettingsTest(unittest.TestCase):
    def test_the_app_can_open_settings_at_a_tab(self):
        """"My reminders" opens the Reminders tab; the app used to refuse the tab it was asked for."""
        import inspect

        from echosub.main import App

        self.assertIn("show_tab", inspect.signature(App._open_settings).parameters)


if __name__ == "__main__":
    unittest.main(verbosity=2)
