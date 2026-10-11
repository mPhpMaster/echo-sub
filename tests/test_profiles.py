# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Profiles: saving the current settings under a name, and switching to them by menu or by voice."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ECHOSUB_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data"))

from PySide6.QtWidgets import QApplication, QMenu  # noqa: E402

from echosub import config, profiles, voice_commands  # noqa: E402
from test_voice_command_ui import FakeApp  # noqa: E402

app = QApplication.instance() or QApplication([])


class ProfileApp(FakeApp, profiles.ProfileMixin):
    def __init__(self, **cfg):
        super().__init__(**cfg)
        self.applied = []

    def _apply(self, values):
        self.applied.append(values)
        self.cfg.update(values)


class SnapshotTest(unittest.TestCase):
    def test_your_own_lists_and_keys_are_never_in_a_profile(self):
        cfg = dict(config.DEFAULTS, reminders=[{"x": 1}], ai_profiles={"claude": {"key": "secret"}},
                   voice_custom_commands=[{"phrase": "a"}], light_mode=True)
        saved = profiles.snapshot(cfg)
        for key in ("reminders", "ai_profiles", "voice_custom_commands", "transcript_fixes", "profiles", "geometry"):
            self.assertNotIn(key, saved)
        self.assertTrue(saved["light_mode"])

    def test_a_saved_profile_can_only_change_what_a_profile_may(self):
        values = profiles.values_of({"Game": {"light_mode": True, "ai_profiles": {"x": 1}, "nonsense": 3}}, "Game")
        self.assertEqual(values, {"light_mode": True})
        self.assertIsNone(profiles.values_of({}, "Game"))

    def test_names(self):
        self.assertEqual(profiles.clean_name("  My   game  "), "My game")
        self.assertEqual(profiles.clean_name(""), "")
        self.assertEqual(profiles.find_name("echo sub switch to the meeting profile", ["Game", "Meeting"]), "Meeting")
        self.assertIsNone(profiles.find_name("echo sub gamer profile", ["Game"]), "whole words only")


class AppTest(unittest.TestCase):
    def test_save_then_switch(self):
        app_ = ProfileApp(voice_commands=True, light_mode=True, box_position="top-center")
        self.assertTrue(app_.save_profile("Game"))
        app_.cfg.update(light_mode=False, box_position="bottom-center")
        self.assertTrue(app_.switch_profile("Game"))
        self.assertTrue(app_.cfg["light_mode"])
        self.assertEqual(app_.cfg["box_position"], "top-center")
        self.assertEqual(app_.cfg["active_profile"], "Game")

    def test_by_voice(self):
        app_ = ProfileApp(voice_commands=True, light_mode=True)
        app_.save_profile("Game")
        app_.cfg["light_mode"] = False
        app_._handle_voice_command("echo sub game profile")
        self.assertTrue(app_.cfg["light_mode"])

    def test_a_name_never_saved_does_nothing(self):
        app_ = ProfileApp(voice_commands=True)
        self.assertFalse(app_.switch_profile("Nope"))
        self.assertIsNone(voice_commands.find("echo sub game profile"), "no profiles, nothing to match")
        self.assertFalse(app_._run_app_command("profile:Nope"))

    def test_switched_off_it_is_neither_offered_nor_obeyed(self):
        app_ = ProfileApp(voice_commands=True, light_mode=True)
        app_.save_profile("Game")
        app_.cfg.update(light_mode=False, profiles_enabled=False)
        app_._handle_voice_command("echo sub game profile")
        self.assertFalse(app_.switch_profile("Game"))
        self.assertFalse(app_.cfg["light_mode"])

    def test_removing(self):
        app_ = ProfileApp()
        app_.save_profile("Game")
        self.assertTrue(app_.remove_profile("Game"))
        self.assertEqual(app_.cfg["profiles"], {})
        self.assertEqual(app_.cfg["active_profile"], "")

    def test_the_menu_lists_them_and_ticks_the_one_in_use(self):
        app_ = ProfileApp()
        app_.save_profile("Game")
        app_.save_profile("Meeting")
        menu = QMenu()
        app_._build_profile_menu(menu)
        app_._fill_profile_menu()
        texts = [a.text() for a in app_.profile_menu.actions()]
        self.assertIn("Game", texts)
        self.assertTrue(next(a for a in app_.profile_menu.actions() if a.text() == "Meeting").isChecked())

    def test_on_by_default_with_none_saved(self):
        self.assertTrue(config.DEFAULTS["profiles_enabled"])
        self.assertEqual(config.DEFAULTS["profiles"], {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
