# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""EchoSub Lens: the Settings window — how translations look, and a key for every option."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTabWidget, QVBoxLayout

from .lens_shortcuts import ShortcutsPage
from .lens_style import AppearancePage

TABS = ("appearance", "shortcuts")


class LensSettings(QDialog):
    """Appearance changes show at once; OK keeps them and the keys, Cancel puts the old look back.

    `apply_style(style)` shows a look; `apply_keys(keys)` registers the keys and returns the
    labels of those another program holds.
    """

    def __init__(self, style, keys, apply_style, apply_keys, tab="appearance", parent=None):
        super().__init__(parent)
        self.setWindowTitle("EchoSub Lens — Settings")
        self.setWindowFlag(Qt.WindowStaysOnTopHint)
        self.resize(660, 560)
        self._original_style = dict(style)
        self._apply_style = apply_style
        self._apply_keys = apply_keys
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.appearance = AppearancePage(style)
        self.appearance.changed.connect(apply_style)
        self.shortcuts = ShortcutsPage(keys)
        self.tabs.addTab(self.appearance, "Appearance")
        self.tabs.addTab(self.shortcuts, "Keyboard shortcuts")
        self.show_tab(tab)
        layout.addWidget(self.tabs)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.shortcuts.changed.connect(
            lambda: self.buttons.button(QDialogButtonBox.Ok).setEnabled(self.shortcuts.valid()))

    def show_tab(self, tab):
        self.tabs.setCurrentIndex(TABS.index(tab) if tab in TABS else 0)

    def accept(self):
        if not self.shortcuts.valid():
            self.show_tab("shortcuts")
            return
        taken = self._apply_keys(self.shortcuts.value())
        if taken:  # stay open and say which keys another program holds
            self.show_tab("shortcuts")
            self.shortcuts.show_unavailable(taken)
            return
        super().accept()

    def reject(self):
        self._apply_style(self._original_style)
        super().reject()
