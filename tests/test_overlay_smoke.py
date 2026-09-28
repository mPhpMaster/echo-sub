# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Drives a visible caption box through the paths the app actually uses.

The caption box is split across three files (widgets, placement, animation). These tests run the
sliding animations, the box resizing itself and the copy buttons, which is where a piece that was
moved to another file but left a name behind shows up.
"""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ECHOSUB_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from echosub import config  # noqa: E402
from echosub.overlay import CaptionOverlay  # noqa: E402

app = QApplication.instance() or QApplication([])


def settle(seconds=0.4):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


class AnimatedOverlayTest(unittest.TestCase):
    """With animations on and the window shown — the state the app itself runs in."""

    def make(self, **overrides):
        cfg = dict(config.DEFAULTS, target_lang="ar", caption_animation="slide", caption_animation_ms=120,
                   max_lines=2, box_autosize=True, geometry=[-4000, 200, 700, 120])
        cfg.update(overrides)
        overlay = CaptionOverlay(cfg, lambda p: None, lambda g: None, lambda: None)
        overlay.setWindowOpacity(0.0)
        overlay.show()  # off-screen and invisible, but a real shown window
        self.addCleanup(overlay.close)
        settle(0.1)
        return overlay, cfg

    def test_captions_slide_in_and_the_box_resizes(self):
        overlay, _ = self.make()
        for i in range(4):
            overlay.add_final(i, f"Caption number {i} which is long enough to wrap onto another line.",
                              "ترجمة السطر رقم " + str(i), "en", i % 2)
            settle(0.2)
        self.assertTrue(overlay.lines, "no captions were shown")
        self.assertTrue(overlay.is_shown())

    def test_live_text_then_a_finished_caption(self):
        overlay, _ = self.make()
        overlay.set_partial("this is live text as it is spoken", None, "en")
        settle(0.15)
        overlay.set_partial("this is live text as it is spoken now", "هذا نص حي", "en")
        settle(0.15)
        overlay.add_final(1, "This is live text as it is spoken now.", "هذا نص حي الآن.", "en", 0)
        settle(0.25)
        self.assertIsNone(overlay.partial, "the live text stayed after the caption arrived")

    def test_every_box_position_lays_out_while_animating(self):
        for position in ("top-left", "middle-center", "bottom-right", "custom"):
            with self.subTest(position=position):
                overlay, _ = self.make(box_position=position, box_autosize=False)
                overlay.add_final(1, "A caption to place.", "سطر للترجمة", "en", 0)
                settle(0.2)
                overlay.add_final(2, "A second caption that makes the box taller.", "سطر آخر", "en", 1)
                settle(0.25)
                self.assertGreater(overlay.width(), 0)

    def test_zooming_and_the_copy_buttons_while_animating(self):
        overlay, cfg = self.make()
        overlay.add_final(1, "A caption to copy.", "سطر للنسخ", "en", 0)
        settle(0.2)
        overlay._hovered = True
        overlay._update_copy_buttons()
        settle(0.1)
        self.assertTrue(overlay._copy_buttons, "no copy buttons appeared")
        overlay.set_scale(cfg["box_scale"] + 20)
        settle(0.25)
        overlay.reset_scale()
        settle(0.25)
        self.assertEqual(cfg["box_scale"], 100)

    def test_clearing_and_auto_hiding(self):
        overlay, cfg = self.make(clear_after_sec=1)
        overlay.add_final(1, "Something said once.", "شيء قيل مرة", "en", 0)
        settle(0.2)
        overlay.clear()
        settle(0.2)
        self.assertFalse(overlay.has_text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
