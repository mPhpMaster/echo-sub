# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""The Settings window must fit the screen it opens on, so Save is always reachable.

It has to hold up on a 1920x1080 screen with Windows text scaling at 125 % or 150 %, which leaves
about 1536x864 or 1280x720 of usable space. Qt's offscreen screen is smaller still, so a window
that fits here fits there.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ECHOSUB_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data"))

from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialogButtonBox  # noqa: E402

from echosub import config, history  # noqa: E402
from echosub.settings_dialog import SettingsDialog  # noqa: E402

app = QApplication.instance() or QApplication([])
SCREENS = {"1920x1080 at 100 %": (1920, 1080), "1920x1080 at 125 %": (1536, 864),
           "1920x1080 at 150 %": (1280, 720), "1366x768 laptop": (1366, 728)}


class SettingsWindowSizeTest(unittest.TestCase):
    def setUp(self):
        self.dialog = SettingsDialog(dict(config.DEFAULTS))

    def test_it_fits_the_screen_it_opens_on(self):
        available = QGuiApplication.primaryScreen().availableGeometry()
        self.assertLessEqual(self.dialog.height(), available.height())
        self.assertLessEqual(self.dialog.width(), available.width())

    def test_it_can_shrink_to_small_screens(self):
        smallest = self.dialog.minimumSizeHint()
        for name, (width, height) in SCREENS.items():
            with self.subTest(screen=name):
                self.assertLessEqual(smallest.height(), height - 60,
                                     f"the window cannot shrink below {smallest.height()} px on {name}")
                self.assertLessEqual(smallest.width(), width - 40)

    def test_the_save_button_stays_below_the_tabs(self):
        box = self.dialog.findChild(QDialogButtonBox)
        self.assertIsNotNone(box)
        save = box.button(QDialogButtonBox.Save)
        self.assertIsNotNone(save, "no Save button")
        self.dialog.show()
        self.dialog.resize(self.dialog.minimumSizeHint())
        app.processEvents()
        save_bottom = save.mapTo(self.dialog, save.rect().bottomLeft()).y()
        self.assertGreater(save_bottom, 0, "the Save button was not laid out")
        self.assertLessEqual(save_bottom, self.dialog.height(),
                             "Save falls outside the window when it is shrunk to its smallest")
        self.dialog.hide()

    def test_every_tab_scrolls_instead_of_stretching_the_window(self):
        from PySide6.QtWidgets import QScrollArea, QTabWidget

        tabs = self.dialog.findChild(QTabWidget)
        for index in range(tabs.count()):
            with self.subTest(tab=tabs.tabText(index)):
                self.assertIsInstance(tabs.widget(index), QScrollArea)


class HistoryWindowSizeTest(unittest.TestCase):
    def test_the_history_window_fits_too(self):
        window = history.HistoryWindow(history.History(), dict(config.DEFAULTS))
        available = QGuiApplication.primaryScreen().availableGeometry()
        self.assertLessEqual(window.height(), available.height())
        self.assertLessEqual(window.width(), available.width())


if __name__ == "__main__":
    unittest.main(verbosity=2)
