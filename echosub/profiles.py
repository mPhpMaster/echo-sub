# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Profiles: the current settings saved under a name ("Game", "Meeting"…), switched in one go.

A profile keeps how EchoSub looks and works — the speech model, light mode, where the box sits,
text sizes, reading aloud and so on. It never keeps your own lists (commands, reminders, spellings,
keys), which stay the same whichever profile is in use. Switching goes through the same path as
saving the Settings window, so the engine only restarts when a profile changes something it needs.
"""
import logging

from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QInputDialog, QMessageBox, QSystemTrayIcon

from . import APP_NAME, config

log = logging.getLogger(__name__)

MAX_PROFILES = 20
MAX_NAME = 40
# Kept out of every profile: your own lists and secrets, window state, and the profiles themselves
NOT_IN_PROFILES = frozenset({
    "profiles", "active_profile", "profiles_enabled", "geometry", "last_update_check", "ai_profiles",
    "reminders", "voice_custom_commands", "voice_go_folders", "screen_reply_pairs", "transcript_fixes",
    "alert_words", "voice_command_wake", "usage_window",
})


def clean_name(name):
    name = " ".join(str(name or "").split())[:MAX_NAME]
    return name if name and name.lower() not in ("none", "default") else ""


def snapshot(cfg):
    """The part of the settings a profile keeps."""
    return {key: cfg[key] for key in config.DEFAULTS if key not in NOT_IN_PROFILES and key in cfg}


def values_of(profiles, name):
    """The settings to apply for a saved profile, limited to what a profile may change; None if unknown."""
    saved = (profiles or {}).get(name)
    if not isinstance(saved, dict):
        return None
    return {key: value for key, value in saved.items() if key in config.DEFAULTS and key not in NOT_IN_PROFILES}


def find_name(spoken, names):
    """The saved profile whose name was said, longest name first; None if none was."""
    from .voice_text import normalize

    said = f" {normalize(spoken)} "
    for name in sorted(names, key=len, reverse=True):
        if f" {normalize(name)} " in said:
            return name
    return None


class ProfileMixin:
    """For the App: the Profiles menu, saving, switching and removing."""

    def _build_profile_menu(self, menu):
        self.profile_menu = menu.addMenu("Profile")
        self.profile_menu.aboutToShow.connect(self._fill_profile_menu)
        self.profile_menu.menuAction().setVisible(bool(self.cfg.get("profiles_enabled", True)))
        return self.profile_menu

    def _fill_profile_menu(self):
        menu = self.profile_menu
        menu.clear()
        names = sorted(self.cfg.get("profiles") or {})
        group = QActionGroup(menu)
        for name in names:
            action = QAction(name, menu, checkable=True, checked=name == self.cfg.get("active_profile"))
            action.triggered.connect(lambda _checked=False, n=name: self.switch_profile(n))
            group.addAction(action)
            menu.addAction(action)
        if not names:
            empty = menu.addAction("No profiles yet")
            empty.setEnabled(False)
        menu.addSeparator()
        menu.addAction("Save current settings as a profile…", self.save_profile_dialog)
        if names:
            remove = menu.addMenu("Remove a profile")
            for name in names:
                remove.addAction(name, lambda n=name: self.remove_profile(n))

    def save_profile(self, name):
        name = clean_name(name)
        profiles = dict(self.cfg.get("profiles") or {})
        if not name or (name not in profiles and len(profiles) >= MAX_PROFILES):
            return False
        profiles[name] = snapshot(self.cfg)
        self.cfg["profiles"] = profiles
        self.cfg["active_profile"] = name
        self._save()
        log.info("Saved profile %r", name)
        return True

    def save_profile_dialog(self):
        name, ok = QInputDialog.getText(None, f"{APP_NAME} — save a profile",
                                        "Name for the current settings (for example Game, Meeting, Video):",
                                        text=self.cfg.get("active_profile", ""))
        if ok and clean_name(name):
            if not self.save_profile(name):
                QMessageBox.information(None, APP_NAME, f"At most {MAX_PROFILES} profiles can be kept.")

    def switch_profile(self, name):
        if not self.cfg.get("profiles_enabled", True):
            return False
        values = values_of(self.cfg.get("profiles"), name)
        if values is None:
            return False
        log.info("Switching to profile %r", name)
        self.cfg["active_profile"] = name
        self._apply(values)
        self.tray.showMessage(APP_NAME, f"Profile: {name}", QSystemTrayIcon.Information, 2000)
        return True

    def remove_profile(self, name):
        profiles = dict(self.cfg.get("profiles") or {})
        if profiles.pop(name, None) is None:
            return False
        self.cfg["profiles"] = profiles
        if self.cfg.get("active_profile") == name:
            self.cfg["active_profile"] = ""
        self._save()
        return True
