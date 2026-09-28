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

from echosub import config, engine  # noqa: E402
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

    def test_light_mode_can_use_base_instead_of_small(self):
        """Measured here: Base is 2-6x faster than Small and as accurate down to 0 dB of noise."""
        cfg = dict(config.DEFAULTS, whisper_model="large-v3-turbo", light_mode=True, light_model="base")
        dialog = SettingsDialog(cfg)
        self.assertEqual(dialog.values()["light_model"], "base")
        self.assertEqual(engine.effective_whisper_model(dialog.values()), "base")

    def test_an_unknown_light_model_falls_back_to_small(self):
        cfg = dict(config.DEFAULTS, whisper_model="large-v3-turbo", light_mode=True, light_model="made up")
        self.assertEqual(engine.effective_whisper_model(cfg), engine.LIGHT_WHISPER_MODEL)

    def test_the_light_model_list_follows_the_checkbox(self):
        dialog = SettingsDialog(dict(config.DEFAULTS, light_mode=False))
        self.assertFalse(dialog.light_model.isEnabled())
        dialog.light_mode.setChecked(True)
        self.assertTrue(dialog.light_model.isEnabled())

    def test_default_is_off(self):
        self.assertFalse(config.DEFAULTS["light_mode"])
        self.assertFalse(SettingsDialog(dict(config.DEFAULTS)).values()["light_mode"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
