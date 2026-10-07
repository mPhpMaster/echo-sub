# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Choosing where the caption box sits, straight from the right-click menu."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ECHOSUB_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data"))

from PySide6.QtWidgets import QApplication, QMenu  # noqa: E402

from echosub.tray_menu import COLUMNS, ROWS, TrayMenuMixin  # noqa: E402

app = QApplication.instance() or QApplication([])


class FakeApp(TrayMenuMixin):
    def __init__(self, position="bottom-center"):
        self.cfg = {"box_position": position}
        self.applied = []

    def _apply(self, values):
        self.applied.append(values)
        self.cfg.update(values)


class PositionMenuTest(unittest.TestCase):
    def build(self, position="bottom-center"):
        fake = FakeApp(position)
        menu = QMenu()
        self.addCleanup(menu.deleteLater)
        submenu = fake._build_position_menu(menu)
        return fake, submenu

    def test_all_nine_spots_are_offered(self):
        fake, _menu = self.build()
        expected = {f"{row}-{col}" for row in ROWS for col in COLUMNS}
        self.assertEqual(set(fake.position_actions) - {"custom"}, expected)

    def test_choosing_one_moves_the_box(self):
        fake, _menu = self.build()
        fake.position_actions["top-right"].trigger()
        self.assertEqual(fake.applied, [{"box_position": "top-right"}])

    def test_the_current_spot_is_ticked(self):
        fake, _menu = self.build("middle-left")
        self.assertTrue(fake.position_actions["middle-left"].isChecked())
        self.assertFalse(fake.position_actions["bottom-center"].isChecked())

    def test_the_tick_follows_a_change_made_elsewhere(self):
        fake, menu = self.build("bottom-center")
        fake.cfg["box_position"] = "top-left"  # e.g. changed in the settings
        menu.aboutToShow.emit()
        self.assertTrue(fake.position_actions["top-left"].isChecked())

    def test_a_dragged_box_shows_as_dragged(self):
        fake, _menu = self.build("custom")
        self.assertTrue(fake.position_actions["custom"].isChecked())
        self.assertFalse(fake.position_actions["custom"].isEnabled(), "you drag to get there, not click")

    def test_each_spot_has_a_picture_of_where_it_is(self):
        fake, _menu = self.build()
        self.assertFalse(fake.position_actions["top-left"].icon().isNull())

    def test_the_menu_is_titled_so_it_can_be_found(self):
        _fake, menu = self.build()
        self.assertEqual(menu.title(), "Box position")


if __name__ == "__main__":
    unittest.main(verbosity=2)
