# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""The way to support EchoSub: one fixed link, in the About window and the tray menu."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ECHOSUB_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data"))

from PySide6.QtWidgets import QApplication  # noqa: E402

import echosub  # noqa: E402
from echosub import about  # noqa: E402

app = QApplication.instance() or QApplication([])
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class SupportTest(unittest.TestCase):
    def test_the_link_is_the_authors_paypal(self):
        self.assertEqual(echosub.DONATE_URL, "https://paypal.me/mfsafadi")

    def test_the_about_window_offers_it(self):
        dialog = about.AboutDialog()
        self.addCleanup(dialog.close)
        self.assertIn("Support", dialog.support_button.text())
        self.assertEqual(dialog.support_button.toolTip(), echosub.DONATE_URL, "it says where it goes")

    def test_the_tray_menu_offers_it(self):
        with open(os.path.join(ROOT, "echosub", "tray_menu.py"), encoding="utf-8") as f:
            self.assertIn("DONATE_URL", f.read())

    def test_the_repository_page_shows_it(self):
        with open(os.path.join(ROOT, ".github", "FUNDING.yml"), encoding="utf-8") as f:
            self.assertIn(echosub.DONATE_URL, f.read())


if __name__ == "__main__":
    unittest.main(verbosity=2)
