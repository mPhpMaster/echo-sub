# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""EchoSub Lens: the lens that follows the mouse and translates only the text around the pointer."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ECHOSUB_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data"))

from PySide6.QtCore import QPoint, QRect, QSize  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from echosub import lens_app, lens_follow, lens_scanner, lens_shortcuts  # noqa: E402
from echosub.lens_ocr import Block, Box, Line  # noqa: E402
from echosub.lens_overlay import FRAME_MARGIN, LensOverlay  # noqa: E402

app = QApplication.instance() or QApplication([])


class FollowTest(unittest.TestCase):
    def test_the_lens_is_centred_on_the_pointer_and_stays_on_the_screen(self):
        screen = QSize(1920, 1080)
        self.assertEqual(lens_follow.lens_rect(QPoint(960, 540), screen, (480, 180)), QRect(720, 450, 480, 180))
        self.assertEqual(lens_follow.lens_rect(QPoint(5, 5), screen, (480, 180)), QRect(0, 0, 480, 180))
        self.assertEqual(lens_follow.lens_rect(QPoint(1915, 1075), screen, (480, 180)), QRect(1440, 900, 480, 180))
        self.assertEqual(lens_follow.lens_rect(QPoint(10, 10), QSize(300, 100), (480, 180)), QRect(0, 0, 300, 100))

    def test_small_moves_keep_the_lens_where_it_is(self):
        size = (480, 180)
        self.assertTrue(lens_follow.should_move(None, QPoint(1, 1), size))
        self.assertFalse(lens_follow.should_move(QPoint(500, 500), QPoint(560, 530), size))
        self.assertTrue(lens_follow.should_move(QPoint(500, 500), QPoint(500, 560), size))   # the next line
        self.assertTrue(lens_follow.should_move(QPoint(500, 500), QPoint(700, 500), size))

    def test_bigger_and_smaller_within_limits(self):
        screen = QSize(1920, 1080)
        self.assertEqual(lens_follow.resized([480, 180], True, screen), [600, 225])
        self.assertEqual(lens_follow.resized([160, 60], False, screen), [160, 60])
        self.assertEqual(lens_follow.resized([1900, 1000], True, screen), [1920, 1080])

    def test_cut_words_at_the_sides_are_left_out(self):
        cut = Block([Line([("nts", Box(0, 10, 30, 16))])])
        whole = Block([Line([("The weather is nice", Box(100, 10, 200, 16))])])
        long_line = Block([Line([("a long line cut on both sides", Box(0, 40, 480, 16))])])
        self.assertTrue(lens_scanner.cut_at_edge(cut, 480))
        self.assertFalse(lens_scanner.cut_at_edge(whole, 480))
        self.assertFalse(lens_scanner.cut_at_edge(long_line, 480))  # still worth reading


class FrameTest(unittest.TestCase):
    def test_the_frame_lies_outside_the_area_lens_reads(self):
        overlay = LensOverlay()
        overlay.cover(QRect(100, 100, 400, 150), 1.0, frame=True)
        m = FRAME_MARGIN
        self.assertEqual(overlay.geometry(), QRect(100, 100, 400, 150).adjusted(-m, -m, m, m))
        overlay.show_blocks([Block([Line([("Hello", Box(20, 30, 60, 16))])], translation="Bonjour")], "fr")
        label = overlay.labels[0]
        self.assertGreaterEqual(label.x(), 20 - 4 + FRAME_MARGIN - 1)     # placed inside the frame
        covered = overlay.covered()[0]
        self.assertEqual(covered.topLeft(), label.geometry().topLeft() - QPoint(FRAME_MARGIN, FRAME_MARGIN))
        overlay.cover(QRect(100, 100, 400, 150), 1.0)  # no frame: the window is the area again
        self.assertEqual(overlay.geometry(), QRect(100, 100, 400, 150))
        overlay.close()


class MouseModeTest(unittest.TestCase):
    def make(self, pointer, **cfg):
        from echosub import lens_ui

        self.pointer = pointer
        self.patches = [
            mock.patch.object(lens_ui.QCursor, "pos", side_effect=lambda: self.pointer[0]),
            mock.patch.object(lens_ui.hotkeys.GlobalHotkeys, "enable_keys", return_value=[]),
            mock.patch("echosub.lens_menu.lens_ocr.available_languages", return_value=[]),
            mock.patch.object(lens_ui.LensScanner, "start"),
            mock.patch.object(lens_ui, "ctrl_held", return_value=False),
        ]
        for p in self.patches:
            p.start()
        self.saved = []
        lens = lens_ui.LensApp(app, dict(lens_app.DEFAULTS, style=None, **cfg), self.saved.append,
                               echosub_cfg={"target_lang": "ar", "translator": "google"})
        lens.scanner._timer.start()  # "running", without photographing anything
        return lens

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_the_lens_follows_the_pointer(self):
        lens = self.make([QPoint(600, 400)])
        lens.use_mouse_mode(True)
        self.assertEqual(lens.cfg["mode"], "mouse")
        self.assertEqual(lens.cfg["mode_before_mouse"], "screen")
        screen, rect = lens.area()
        self.assertTrue(rect.contains(QPoint(600, 400) - screen.geometry().topLeft()))  # kept on the screen
        self.assertTrue(lens.overlay.frame)
        self.assertTrue(lens.scanner.trim_edges)
        generation = lens.scanner.generation
        self.pointer[0] = QPoint(620, 410)  # a little: stays
        lens._follow_ctrl()
        self.assertEqual(lens.area()[1], rect)
        self.assertEqual(lens.scanner.generation, generation)
        self.pointer[0] = QPoint(300, 200)  # far away: moves, reads again
        lens._follow_ctrl()
        self.assertNotEqual(lens.area()[1], rect)
        self.assertGreater(lens.scanner.generation, generation)
        lens.use_mouse_mode(False)
        self.assertEqual(lens.cfg["mode"], "screen")
        self.assertFalse(lens.overlay.frame)
        self.assertFalse(lens.scanner.trim_edges)
        lens.quit()

    def test_the_lens_stays_while_selecting(self):
        from echosub import lens_ui

        lens = self.make([QPoint(600, 400)], mode="mouse")
        rect = lens.area()[1]
        self.pointer[0] = QPoint(900, 900)
        with mock.patch.object(lens_ui, "ctrl_held", return_value=True):
            lens._follow_ctrl()
        self.assertEqual(lens.area()[1], rect)
        lens.quit()

    def test_size_frame_and_keys(self):
        lens = self.make([QPoint(600, 400)], mode="mouse")
        lens.set_lens_size([320, 120])
        self.assertEqual(lens.area()[1].size(), QSize(320, 120))
        lens.resize_lens(True)
        self.assertEqual(self.saved[-1]["lens_size"], [400, 150])
        lens.set_lens_frame(False)
        self.assertFalse(lens.overlay.frame)
        for name in ("mouse_mode", "lens_bigger", "lens_smaller"):
            self.assertIn(name, lens.actions())
            self.assertIn(name, lens_shortcuts.ACTIONS)
        self.assertEqual(lens_shortcuts.problems(lens_shortcuts.defaults()), {})
        lens.actions()["mouse_mode"]()  # the key turns it off
        self.assertNotEqual(lens.cfg["mode"], "mouse")
        lens.quit()


if __name__ == "__main__":
    unittest.main()
