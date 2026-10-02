# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""The tray icon's menu: every switch the app has, in one place."""
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QMenu

from . import APP_NAME, hotkeys, languages

QUICK_TARGETS = ["ar", "en", "fr", "de", "es", "it", "pt", "tr", "fa", "ur", "hi", "zh", "ja", "ko", "ru"]


class TrayMenuMixin:
    """Builds the menu and keeps its hotkey labels in step with the settings."""

    def _build_menu(self):
        m = QMenu()
        self.act_show = QAction("Show captions", m, checkable=True, checked=self.cfg["overlay_enabled"])
        self.act_show.toggled.connect(self._set_overlay_enabled)
        self.act_position = QAction("Adjust window position and size", m, checkable=True)
        self.act_position.toggled.connect(self.overlay.set_positioning)
        self.act_lock = QAction("Lock window (click-through)", m, checkable=True, checked=self.cfg["click_through"])
        self.act_lock.toggled.connect(self._set_lock)
        self.act_pause = QAction("Pause", m, checkable=True)
        self.act_pause.toggled.connect(self._set_paused)
        self.act_light = QAction("Light mode (faster on a busy PC)", m, checkable=True,
                                 checked=self.cfg.get("light_mode", False))
        self.act_light.toggled.connect(self._set_light_mode)
        self.act_mic_mute = QAction("Mute my microphone", m, checkable=True)
        self.act_mic_mute.setToolTip("Your microphone is still heard for the phrase that brings it back")
        self.act_mic_mute.toggled.connect(self.set_mic_muted)

        lang_menu = m.addMenu("Translation language")
        group = QActionGroup(lang_menu)
        self.lang_actions = {}
        for code in QUICK_TARGETS:
            a = QAction(languages.name(code), lang_menu, checkable=True, checked=self.cfg["target_lang"] == code)
            a.triggered.connect(lambda _=False, c=code: self._apply({"target_lang": c}))
            group.addAction(a)
            lang_menu.addAction(a)
            self.lang_actions[code] = a
        lang_menu.addSeparator()
        lang_menu.addAction("More languages…", self._open_settings)

        m.addAction(self.act_show)
        m.addAction(self.act_position)
        m.addAction(self.act_lock)
        m.addAction(self.act_pause)
        m.addAction(self.act_light)
        m.addAction(self.act_mic_mute)
        m.addAction(self._make_voice_command_action(m))
        m.addAction("Caption size: back to 100%", self.overlay.reset_scale)
        m.addAction("Clear captions", self.overlay.clear)
        m.addSeparator()
        m.addAction("What can I say?…", self.open_help_window)
        m.addAction("Caption history…", self._open_history)
        m.addAction("Settings…", self._open_settings)
        m.addAction("Open log file", self._open_log)
        m.addAction("Check for updates…", lambda: self._check_updates_async(manual=True))
        m.addAction(f"About {APP_NAME}…", self._open_about)
        m.addAction("Restart engine", self._start_engine)
        m.addSeparator()
        m.addAction("Exit", self._quit)
        self._update_hotkey_labels()
        return m

    def _update_hotkey_labels(self):
        enabled = self.cfg["global_hotkeys"]
        for action, name, text in ((self.act_show, "toggle_captions", "Show captions"),
                                   (self.act_pause, "pause", "Pause"),
                                   (self.act_lock, "lock", "Lock window (click-through)")):
            # Text after a tab is drawn in the menu's shortcut column
            action.setText(f"{text}\t{hotkeys.label(name)}" if enabled else text)
