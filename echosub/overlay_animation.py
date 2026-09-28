# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""How captions move: the sliding of lines and of the box itself, and fading the window in and out.

Lines are laid out where they will end up, then shifted back to where they were and slid into
place (a FLIP animation), so text never re-wraps or wobbles while the box changes size.
"""
import time

from PySide6.QtCore import QRect

from .caption_widgets import ease_out


class AnimationMixin:
    """The animation half of CaptionOverlay."""

    def _line_screen_y(self, line):
        return self.geometry().y() + self.viewport.y() + self.content.y() + line.y()

    def _box_target(self):
        """Where the box is going (its final geometry while a resize animation runs)."""
        return self._geo_anim[1] if self._geo_anim is not None else self.geometry()

    def _current_offset(self):
        if self._offset_anim is None:
            return 0.0
        start, t0, duration = self._offset_anim
        t = (time.monotonic() - t0) / duration
        return 0.0 if t >= 1 else start * (1 - ease_out(t))

    def _tick(self):
        now = time.monotonic()
        active = any([line.tick(now) for line in self._line_by_key.values()])
        if self._geo_anim is not None:
            start, target, t0, duration = self._geo_anim
            t = (now - t0) / duration
            if t >= 1:
                self._geo_anim = None
                self.setGeometry(target)
            else:
                e = ease_out(t)
                self.setGeometry(QRect(round(start.x() + (target.x() - start.x()) * e),
                                       round(start.y() + (target.y() - start.y()) * e),
                                       round(start.width() + (target.width() - start.width()) * e),
                                       round(start.height() + (target.height() - start.height()) * e)))
                active = True
        if self._offset_anim is not None:
            if now - self._offset_anim[1] >= self._offset_anim[2]:
                self._offset_anim = None
            else:
                active = True
        if self.ghosts and not any(self._line_by_key[e["key"]]._reveal_anim for e in self.ghosts
                                   if e["key"] in self._line_by_key):
            if self._offset_anim is None:
                self.ghosts.clear()
                self.refresh()
                return
        self._place_content(self._current_offset())
        self.content.update()
        for line in self._line_by_key.values():
            line.original.update()
            line.translated.update()
        if not active and not self.ghosts:
            self._anim_timer.stop()

    def _finish_geometry_animation(self):
        if self._geo_anim is not None:
            target = self._geo_anim[1]
            self._geo_anim = None
            self.setGeometry(target)

    def _finish_animations(self):
        self._offset_anim = None
        self._finish_geometry_animation()
        if self.ghosts:
            self.ghosts.clear()
            for key in [k for k, line in self._line_by_key.items() if line.ghost]:
                line = self._line_by_key.pop(key)
                self.content_layout.removeWidget(line)
                line.deleteLater()
        for line in self._line_by_key.values():
            line._reveal_anim = None
            line.reveal = 1.0
            line.original._old = None
            line.translated._old = None
        self._anim_timer.stop()

    def _content_height(self, inner_width, include_ghosts=True):
        self.content_layout.activate()
        height = self.content_layout.heightForWidth(inner_width) if self.content_layout.hasHeightForWidth() \
            else self.content_layout.sizeHint().height()
        if not include_ghosts:
            for entry in self.ghosts:
                line = self._line_by_key.get(entry["key"])
                if line is not None:
                    height -= line.heightForWidth(inner_width) + self.content_layout.spacing()
        return max(0, height)

    def _place_content(self, offset):
        """Bottom-align the content column, shifted down by `offset` px.

        The column is laid out for the box's final size and kept where it will end up on screen,
        so while the box slides to a new size the text doesn't re-wrap or wobble; the box edges
        just open up around it (or close in).
        """
        target, current = self._box_target(), self.geometry()
        pad_x, pad_y = self._padding()
        inner_w = max(1, target.width() - 2 * pad_x)
        inner_h = max(1, target.height() - 2 * pad_y)
        height = self._content_height(inner_w)
        dx, dy = target.x() - current.x(), target.y() - current.y()
        self.content.setGeometry(dx, round(dy + inner_h - height + offset), inner_w, height)
        self.content_layout.activate()
        self._position_copy_buttons()

    def _fade_in(self):
        if self.isVisible() and not self._fading_out:
            return
        self._fade.stop()
        self._fading_out = False
        if not self.isVisible():
            self.setWindowOpacity(0.0)
            self.show()
            self.on_shown()
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(1.0)
        self._fade.start()

    def _fade_out(self):
        if not self.isVisible() or self._fading_out:
            return
        self._fade.stop()
        self._fading_out = True
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(0.0)
        self._fade.start()

    def _fade_finished(self):
        if self._fading_out:
            self._fading_out = False
            self.hide()
            self.setWindowOpacity(1.0)
