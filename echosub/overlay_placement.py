# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Where the caption box sits and how big it is: screen presets, custom placement and autosize."""
import time

from PySide6.QtCore import QRect
from PySide6.QtGui import QGuiApplication

from .caption_widgets import box_scale


class PlacementMixin:
    """The placement half of CaptionOverlay."""

    # ---- placement -----------------------------------------------------------
    def target_screen(self):
        name = self.cfg.get("box_screen")
        for screen in QGuiApplication.screens():
            if name and screen.name() == name:
                return screen
        return QGuiApplication.primaryScreen()

    def _padding(self):
        scale = box_scale(self.cfg)
        return round(self.cfg.get("box_padding_x", 24) * scale), round(self.cfg.get("box_padding_y", 12) * scale)

    def _needed_height(self, width):
        pad_x, pad_y = self._padding()
        return self._content_height(max(1, width - 2 * pad_x), include_ghosts=False) + 2 * pad_y

    def _content_width(self, max_width):
        """Narrowest box width that fits every visible line without extra wrapping."""
        pad_x, _ = self._padding()
        inner_max = max(1, max_width - 2 * pad_x)
        widest = max((line.preferred_width(inner_max) for line in self.lines), default=0)
        if self.status_label.isVisibleTo(self.content) and self.status:
            widest = max(widest, self.status_label.fontMetrics().horizontalAdvance(self.status) + 8)
        return max(160, min(max_width, widest + 2 * pad_x))

    def _preset_max_width(self, avail, col):
        margin = self.cfg["box_margin"]
        return max(200, min(avail.width() - 2 * (margin if col != "center" else 0),
                            int(avail.width() * self.cfg["box_width_pct"] / 100 * box_scale(self.cfg))))

    def _fit_geometry(self, animate=False):
        """Size the box to its text and place it (sliding to the new geometry when `animate`).

        Presets anchor the box to a screen edge/corner and grow it away from that edge;
        custom placement keeps the bottom edge and horizontal center where the user dragged it.
        With autosize the box is only as wide and tall as its text (up to the configured width).
        """
        pad_x, pad_y = self._padding()
        if not (self._drag is not None and self._dragged):  # never fight the user's drag
            avail = self.target_screen().availableGeometry()
            position = self.cfg.get("box_position", "custom")
            autosize = self.cfg.get("box_autosize", False)
            scale = box_scale(self.cfg)
            user_height = round(self.user_height * scale)  # the user's size is kept at 100 %
            if position == "custom":
                max_width = min(round(self._custom_width * scale), self.screen().availableGeometry().width())
                width = self._content_width(max_width) if autosize else max_width
                needed = self._needed_height(width)
                height = needed if autosize else max(user_height, needed)
                center = self._custom_center if self._custom_center is not None else self.geometry().center().x()
                g = QRect(round(center - width / 2), 0, width, height)
                bottom = self._custom_bottom if self._custom_bottom is not None else self.geometry().bottom() + 1
                g.moveBottom(bottom - 1)
                screen = self.screen().availableGeometry()
                if g.top() < screen.top():
                    g.moveTop(screen.top())  # temporary while the text is tall; the anchor bottom is kept
            else:
                row, col = position.split("-")
                margin = self.cfg["box_margin"]
                max_width = self._preset_max_width(avail, col)
                width = self._content_width(max_width) if autosize else max_width
                needed = self._needed_height(width)
                height = min(avail.height(), needed if autosize else max(user_height, needed))
                x = {"left": avail.left() + margin,
                     "center": avail.left() + (avail.width() - width) // 2,
                     "right": avail.right() + 1 - margin - width}[col]
                y = {"top": avail.top() + margin,
                     "middle": avail.top() + (avail.height() - height) // 2,
                     "bottom": avail.bottom() + 1 - margin - height}[row]
                x = max(avail.left(), min(x, avail.right() + 1 - width))
                y = max(avail.top(), min(y, avail.bottom() + 1 - height))
                g = QRect(x, y, width, height)
            if g != self._box_target():
                if animate and not self._grip_resizing:
                    duration = self.cfg.get("caption_animation_ms", 250) / 1000
                    self._geo_anim = (self.geometry(), g, time.monotonic(), duration)
                    if not self._anim_timer.isActive():
                        self._anim_timer.start()
                else:
                    self._geo_anim = None
                    self.setGeometry(g)
        self.viewport.setGeometry(pad_x, pad_y, max(1, self.width() - 2 * pad_x), max(1, self.height() - 2 * pad_y))
        self.grip.raise_()
