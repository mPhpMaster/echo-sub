# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Shift + wheel is also Windows' sideways-scroll gesture, so the caption box can be zoomed by
accident. It must never grow into a wall of text, and one click must bring it back.

Runs without a screen (Qt's offscreen platform).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ECHOSUB_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from echosub import config  # noqa: E402
from echosub.overlay import SCALE_MAX, CaptionOverlay  # noqa: E402

app = QApplication.instance() or QApplication([])


def make_overlay(**overrides):
    cfg = dict(config.DEFAULTS, target_lang="ar", box_position="custom", box_autosize=True,
               geometry=[400, 400, 700, 120], caption_animation="none")
    cfg.update(overrides)
    overlay = CaptionOverlay(cfg, lambda p: None, lambda g: None, lambda: None)
    overlay.show()
    overlay.add_final(1, "This is a caption that is long enough to wrap in the box.",
                      "هذه ترجمة السطر لاختبار الحجم", "en", 0)
    app.processEvents()
    return overlay, cfg


class ZoomLimitTest(unittest.TestCase):
    def test_zooming_stops_before_the_box_covers_the_screen(self):
        overlay, cfg = make_overlay()
        screen = overlay.target_screen().availableGeometry()
        for _ in range(40):  # forty notches of Shift + wheel, as if scrolling sideways in Explorer
            overlay.set_scale(cfg["box_scale"] + 10)
            app.processEvents()
        self.assertLess(cfg["box_scale"], SCALE_MAX, "the zoom ran all the way to the maximum")
        self.assertLessEqual(overlay.height(), screen.height() * 0.75,
                             f"the box is {overlay.height()} px tall on a {screen.height()} px screen")
        self.assertLessEqual(overlay.width(), screen.width())

    def test_one_click_brings_the_normal_size_back(self):
        overlay, cfg = make_overlay()
        for _ in range(5):
            overlay.set_scale(cfg["box_scale"] + 10)
        self.assertGreater(cfg["box_scale"], 100)
        overlay.reset_scale()
        self.assertEqual(cfg["box_scale"], 100)

    def test_zooming_out_always_works(self):
        overlay, cfg = make_overlay(box_scale=200)
        for _ in range(30):
            overlay.set_scale(cfg["box_scale"] - 10)
        self.assertEqual(cfg["box_scale"], 50, "the box could not be made smaller again")

    def test_a_size_the_user_already_had_is_never_shrunk_by_the_limit(self):
        overlay, cfg = make_overlay(box_scale=280)
        overlay.set_scale(280)
        self.assertEqual(cfg["box_scale"], 280, "an existing size was changed behind the user's back")


if __name__ == "__main__":
    unittest.main(verbosity=2)
