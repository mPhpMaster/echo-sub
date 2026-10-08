# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Where the app shows its own usage: the tray tooltip, a line in the caption box and a small window.

The Settings window has a line of its own (usage_ui.UsageStrip). All of them read the one shared
monitor, which measures in the background every couple of seconds.
"""
from PySide6.QtCore import QTimer

from . import APP_NAME, usage, usage_ui

TICK_MS = 2000
TOOLTIP_MAX = 127  # Windows cuts a tray tooltip off after this many characters


def tray_text(title, figures, detail=None):
    """The tray tooltip: the state, then the figures, then any status detail that still fits."""
    lines = [title] + [line for line in (figures, detail) if line]
    text = "\n".join(lines)
    while len(text) > TOOLTIP_MAX and len(lines) > 2:
        lines.pop()  # the detail goes first; the figures are what this tooltip is for
        text = "\n".join(lines)
    return text[:TOOLTIP_MAX]


class UsageMixin:
    """For the App: keeps the figures on show wherever the settings ask for them."""

    def init_usage(self):
        usage.shared()
        self._usage_window = None
        self._usage_line = usage_ui.caption_line(self.overlay)
        self._usage_timer = QTimer()
        self._usage_timer.timeout.connect(self._usage_tick)
        self._usage_timer.start(TICK_MS)
        if self.cfg.get("usage_window"):
            QTimer.singleShot(0, lambda: self.set_usage_window(True))

    def _usage_tick(self):
        figures = usage.summary(usage.shared().latest)
        self.tray.setToolTip(tray_text(self._tray_title(), figures, getattr(self, "_tray_detail", None)))
        show = bool(figures) and bool(self.cfg.get("usage_line"))
        if self._usage_line.text() != figures or self._usage_line.isVisible() != show:
            self._usage_line.setText(figures)
            self._usage_line.setVisible(show)
            if show or self.overlay.isVisible():
                self.overlay.refresh()

    def set_usage_window(self, on):
        """Open or close the usage window, and remember the choice."""
        self.cfg["usage_window"] = bool(on)
        self._save()
        if hasattr(self, "act_usage") and self.act_usage.isChecked() != bool(on):
            self.act_usage.setChecked(bool(on))
        if on and self._usage_window is None:
            window = usage_ui.UsageWindow(on_top=self.cfg.get("usage_window_on_top", True))
            window.closed.connect(self._usage_window_closed)
            window.on_top_changed.connect(self._usage_window_on_top)
            self._usage_window = window
            window.show()
        elif not on and self._usage_window is not None:
            window, self._usage_window = self._usage_window, None
            window.close()

    def _usage_window_closed(self):
        if self._usage_window is not None:  # closed with its own X button
            self._usage_window = None
            self.set_usage_window(False)

    def _usage_window_on_top(self, on):
        self.cfg["usage_window_on_top"] = bool(on)
        self._save()

    def apply_usage_settings(self):
        """After Settings are saved: the window, its staying on top, and the caption-box line."""
        self.set_usage_window(bool(self.cfg.get("usage_window")))
        if self._usage_window is not None:
            self._usage_window.on_top.setChecked(bool(self.cfg.get("usage_window_on_top", True)))
        self._usage_tick()

    def _tray_title(self):
        return getattr(self, "_tray_state_text", APP_NAME)
