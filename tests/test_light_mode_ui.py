# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Light mode is reachable from the Settings window and keeps the user's own choices.

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
from echosub.settings_dialog import SettingsDialog  # noqa: E402

app = QApplication.instance() or QApplication([])


class SettingsWindowTest(unittest.TestCase):
    def test_the_checkbox_shows_and_saves_light_mode(self):
        cfg = dict(config.DEFAULTS, whisper_model="large-v3-turbo", light_mode=True)
        dialog = SettingsDialog(cfg)
        self.assertTrue(dialog.light_mode.isChecked())
        self.assertTrue(dialog.values()["light_mode"])
        dialog.light_mode.setChecked(False)
        self.assertFalse(dialog.values()["light_mode"])

    def test_the_chosen_model_is_still_saved_while_light_mode_is_on(self):
        cfg = dict(config.DEFAULTS, whisper_model="large-v3", light_mode=True)
        values = SettingsDialog(cfg).values()
        self.assertEqual(values["whisper_model"], "large-v3", "light mode must not overwrite the user's model")
        self.assertTrue(values["light_mode"])

    def test_default_is_off(self):
        self.assertFalse(config.DEFAULTS["light_mode"])
        self.assertFalse(SettingsDialog(dict(config.DEFAULTS)).values()["light_mode"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
