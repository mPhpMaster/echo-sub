# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Always-on-top translucent caption window."""
import itertools
import time

from PySide6.QtCore import (
    QEasingCurve, QEvent, QPoint, QPointF, QPropertyAnimation, QRect, QRectF, QSize, Qt, QTimer,
)
from PySide6.QtGui import (
    QColor, QCursor, QFont, QFontMetricsF, QGuiApplication, QPainter, QPen, QPixmap, QPolygonF, QTextLayout,
    QTextOption,
)
from PySide6.QtWidgets import QLabel, QSizeGrip, QSizePolicy, QToolTip, QVBoxLayout, QWidget

from . import APP_NAME
from .overlay_animation import AnimationMixin
from .overlay_placement import PlacementMixin
from .caption_widgets import (
    CaptionLine, CopyButton, ENTER_SHIFT_PX, FADE_MS, MERGE_MAX_CHARS, MERGE_WINDOW_SEC, PENDING_PLACEHOLDER,
    SCALE_MAX, SCALE_MIN, SCALE_STEP, box_scale, ease_out, entry_view, _entry_keys,
)

class CaptionOverlay(AnimationMixin, PlacementMixin, QWidget):
    """The caption box.

    Lines live in `content`, a column inside the clipping `viewport` (the box minus its padding).
    Content is bottom-aligned in the viewport; when lines are added, removed or change height,
    the content is shifted back to where it was and slid to its new place (a FLIP animation),
    new lines fade/rise in and removed lines fade out while scrolling away.
    """

    def __init__(self, cfg, on_context_menu, on_geometry_changed, on_placement_changed=None, on_shown=None):
        super().__init__()
        self.cfg = cfg
        self.on_context_menu = on_context_menu
        self.on_geometry_changed = on_geometry_changed
        self.on_placement_changed = on_placement_changed or (lambda: None)
        self.on_shown = on_shown or (lambda: None)  # the box was (re)shown and is now on top of other windows
        self.entries = []  # dicts: key, segments[{id, original, translated}], lang, speaker, time
        self.ghosts = []   # entries removed from the top, kept while they animate out
        self.partial = None
        self.status = ""
        self.positioning = False  # show frame + sample so the window can be moved
        self.last_update = 0.0
        self.last_speech = 0.0
        self._drag = None
        self._dragged = False
        self._hovered = False  # the box never auto-hides while the mouse is over it
        self._grip_resizing = False
        self._wheel_delta = 0  # Shift + wheel: angle collected until a full step
        self._copy_buttons = {}  # (entry key, "original"/"translation") -> CopyButton over that row
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(FADE_MS)
        self._fade.setEasingCurve(QEasingCurve.InOutQuad)
        self._fade.finished.connect(self._fade_finished)
        self._fading_out = False

        self._line_by_key = {}
        self._offset_anim = None  # (start_offset, start_time, duration)
        self._geo_anim = None     # box resize/move: (start QRect, target QRect, start_time, duration)
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(15)
        self._anim_timer.timeout.connect(self._tick)

        self.setWindowTitle(APP_NAME)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._apply_flags()

        self.viewport = QWidget(self)
        self.viewport.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.content = QWidget(self.viewport)
        self.content.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSizeConstraint(QVBoxLayout.SetNoConstraint)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #BBBBBB; font-size: 12pt;")
        self.status_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.status_label.hide()
        self.content_layout.addWidget(self.status_label)
        self.grip = QSizeGrip(self)
        self.grip.resize(16, 16)
        self.grip.installEventFilter(self)

        geo = cfg.get("geometry")
        if geo:
            self.setGeometry(QRect(*geo))
            self.user_height = geo[3]
            self._custom_bottom = geo[1] + geo[3]      # custom placement keeps this bottom edge…
            self._custom_center = geo[0] + geo[2] / 2  # …and this horizontal center
            self._custom_width = geo[2]                # width, or maximum width when autosizing
        else:
            self.user_height = 120
            self._custom_bottom = None
            self._custom_center = None
            self._custom_width = 800
        self._fit_geometry()

        self.clear_timer = QTimer(self)
        self.clear_timer.timeout.connect(self._auto_clear)
        self.clear_timer.start(250)
        self.status_timer = QTimer(self)
        self.status_timer.setSingleShot(True)
        self.status_timer.timeout.connect(lambda: self.set_status(""))
        QGuiApplication.instance().screenAdded.connect(lambda _s: self._fit_geometry())
        QGuiApplication.instance().screenRemoved.connect(lambda _s: self._fit_geometry())

    @property
    def lines(self):
        """Visible (non-ghost) caption line widgets, top to bottom."""
        return [line for line in self._ordered_lines() if not line.ghost]

    # ---- window flags / click-through --------------------------------------
    def _apply_flags(self):
        flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        if self.cfg["click_through"] and not self.positioning:
            flags |= Qt.WindowTransparentForInput
        visible = self.isVisible()
        self.setWindowFlags(flags)
        if visible:
            self.show()
            self.on_shown()

    def set_click_through(self, enabled):
        self.cfg["click_through"] = enabled
        self._apply_flags()
        self.update()

    def set_positioning(self, enabled):
        self.positioning = enabled
        self._apply_flags()
        self.refresh()

    # ---- content -----------------------------------------------------------
    def _animation(self):
        mode = self.cfg.get("caption_animation", "slide")
        return mode if mode in ("slide", "fade") else None

    def add_final(self, seg_id, original, translated, lang, speaker=None, source="system"):
        """translated=None means the translation is on its way (see set_translation)."""
        now = time.monotonic()
        segment = {"id": seg_id, "original": original, "translated": translated}
        last = self.entries[-1] if self.entries else None
        if (last is not None and speaker is not None and last["speaker"] == speaker
                and last.get("source", "system") == source
                and last["lang"] == lang and now - last["time"] < MERGE_WINDOW_SEC
                and len(entry_view(last)[0]) + len(original) < MERGE_MAX_CHARS):
            # Same person still talking: continue the current line
            last["segments"].append(segment)
            last["time"] = now
        else:
            self.entries.append({"key": f"e{next(_entry_keys)}", "segments": [segment], "lang": lang,
                                 "speaker": speaker, "time": now, "source": source})
        overflow = self.entries[:-self.cfg["max_lines"]]
        if overflow and self._animation() and self.is_shown():
            self.ghosts.extend(overflow)  # animate them out instead of dropping them instantly
        self.entries = self.entries[-self.cfg["max_lines"]:]
        self.partial = None
        self.last_update = now
        self.refresh()

    def set_translation(self, seg_id, translated):
        for entry in self.entries:
            for segment in entry["segments"]:
                if segment["id"] == seg_id:
                    segment["translated"] = translated
                    self.last_update = time.monotonic()
                    self.refresh()
                    return

    def set_partial(self, original, translated, lang, source="system"):
        self.partial = ({"original": original, "translated": translated, "lang": lang, "speaker": None,
                         "source": source} if original else None)
        self.last_update = time.monotonic()
        self.refresh()

    def speech_activity(self):
        self.last_speech = time.monotonic()

    def set_status(self, text, timeout_ms=0):
        self.status = text
        self.status_label.setText(text)
        self.status_label.setVisible(bool(text))
        if timeout_ms:
            self.status_timer.start(timeout_ms)
        self.refresh()

    def _items(self):
        """[(key, entry, is_partial, is_ghost)] top to bottom."""
        items = [(e["key"], e, False, True) for e in self.ghosts]
        items += [(e.setdefault("key", f"e{next(_entry_keys)}"), e, False, False) for e in self.entries]
        if self.partial and self.cfg["show_partial"]:
            items.append(("partial", self.partial, True, False))
            live = [i for i in items if not i[3]][-(self.cfg["max_lines"] + 1):]
            items = [i for i in items if i[3]] + live
        if not [i for i in items if not i[3]] and self.positioning:
            items += [(f"sample{n}", e, False, False) for n, (e, _) in enumerate(self._sample_items())]
        return items

    def _ordered_lines(self):
        lines = []
        for i in range(self.content_layout.count()):
            w = self.content_layout.itemAt(i).widget()
            if isinstance(w, CaptionLine):
                lines.append(w)
        return lines

    def refresh(self, instant=False):
        animation = self._animation()
        animate = animation is not None and self.is_shown() and not instant
        duration = self.cfg.get("caption_animation_ms", 250)
        # Where each line sits on screen right now (before the change)
        before = {key: self._line_screen_y(line) for key, line in self._line_by_key.items() if line.isVisible()}

        items = self._items()
        keys = [key for key, *_ in items]
        for key in list(self._line_by_key):
            if key not in keys:
                line = self._line_by_key.pop(key)
                self.content_layout.removeWidget(line)
                line.deleteLater()
        for key, entry, partial, ghost in items:
            line = self._line_by_key.get(key)
            new_line = line is None
            if new_line:
                line = CaptionLine(self.content)
                self._line_by_key[key] = line
            was_ghost = line.ghost
            line.ghost = ghost
            line.set(entry, self.cfg, partial, duration if animate and not new_line else 0)
            if new_line and animate and before:
                line.animate_reveal(0.0, 1.0, duration, ENTER_SHIFT_PX if animation == "slide" else 0)
            if ghost and not was_ghost:
                line.animate_reveal(line.reveal, 0.0, duration, 0)
        # Re-order the column to match the items (status label stays last)
        for key in keys:
            self.content_layout.removeWidget(self._line_by_key[key])
        for index, key in enumerate(keys):
            self.content_layout.insertWidget(index, self._line_by_key[key])
            self._line_by_key[key].show()

        scale = box_scale(self.cfg)
        self.content_layout.setSpacing(round(self.cfg["entry_spacing"] * scale))
        self.status_label.setStyleSheet(f"color: #BBBBBB; font-size: {12 * scale:.1f}pt;")
        status_align = {"left": Qt.AlignLeft, "right": Qt.AlignRight}.get(self.cfg["text_align"], Qt.AlignHCenter)
        self.status_label.setAlignment(status_align | Qt.AlignVCenter)

        # Nothing to say -> the window disappears completely
        self._update_copy_buttons()
        should_show = self.positioning or (self.has_text() and self.cfg.get("overlay_enabled", True))
        if should_show:
            self._fade_in()
        else:
            self._fade_out()
        self._fit_geometry(animate=animation == "slide" and animate)

        # FLIP: shift the content so a line that stayed is where it was, then slide it into place
        if animation == "slide" and animate:
            anchor = next((k for k in keys if k in before and not self._line_by_key[k].ghost), None)
            if anchor is None:
                anchor = next((k for k in keys if k in before), None)
            if anchor is not None:
                self._place_content(0)
                delta = before[anchor] - self._line_screen_y(self._line_by_key[anchor])
                if abs(delta) >= 1:
                    self._offset_anim = (self._current_offset() + delta, time.monotonic(), duration / 1000)
        if animate and not self._anim_timer.isActive():
            self._anim_timer.start()
        if not animate:
            self._finish_animations()
        self._place_content(self._current_offset())
        self.update()

    def _copy_rows(self):
        """(key, row widget) for every caption row that has text, top to bottom."""
        for key, line in self._line_by_key.items():
            if line.ghost:
                continue
            for which, row in (("original", line.original), ("translation", line.translated)):
                if row.text and row.isVisible():
                    yield (key, which), row

    def _update_copy_buttons(self):
        """A copy button on every caption row, only while the mouse is over the box."""
        size = 0
        if self._hovered and self.cfg.get("copy_buttons", True) and not self.cfg.get("click_through"):
            size = max(14, round(18 * box_scale(self.cfg)))
        rows = dict(self._copy_rows()) if size else {}
        for key in [k for k in self._copy_buttons if k not in rows]:
            self._copy_buttons.pop(key).deleteLater()
        for key, row in rows.items():
            button = self._copy_buttons.get(key)
            if button is None:
                button = self._copy_buttons[key] = CopyButton(self)
            button.text = row.text
            button.setFixedSize(size, size)
        self._position_copy_buttons()

    def _position_copy_buttons(self):
        """Put every button in the box's right-hand padding, next to its row, and hide those that
        would fall outside the box. With little padding the button moves onto the text edge."""
        inside = self.viewport.geometry()
        pad_x, _ = self._padding()
        for (key, which), button in self._copy_buttons.items():
            line = self._line_by_key.get(key)
            row = None if line is None else (line.original if which == "original" else line.translated)
            if row is None or not row.isVisible():
                button.hide()
                continue
            size = button.width()
            gap = max(2, (pad_x - size) // 2)
            x = self.width() - gap - size
            top = row.mapTo(self, QPoint(0, 0)).y()
            y = top + max(0, (row.height() - size) // 2 if row.height() < size * 2 else 1)
            button.move(round(x), round(y))
            button.setVisible(inside.top() - 2 <= y and y + size <= inside.bottom() + 2)
            button.raise_()

    def is_shown(self):
        return self.isVisible() and not self._fading_out

    def _sample_items(self):
        tgt = self.cfg["target_lang"]
        sample = "هذا مثال على الترجمة لضبط شكل النص" if tgt == "ar" else "Sample caption text to preview the style"
        return [
            ({"original": "This is how the first speaker will look.", "translated": sample,
              "lang": "en", "speaker": 0}, False),
            ({"original": "Y así se verá una segunda persona hablando.", "translated": sample,
              "lang": "es", "speaker": 1}, False),
        ][-max(1, self.cfg["max_lines"]):]

    def clear(self):
        self.entries.clear()
        self.ghosts.clear()
        self.partial = None
        self.refresh()

    def _auto_clear(self):
        limit = self.cfg["clear_after_sec"]
        if not limit or not (self.entries or self.partial) or self._hovered or self._drag is not None:
            return
        quiet_for = time.monotonic() - max(self.last_update, self.last_speech)
        if quiet_for > limit:
            self.clear()

    def has_text(self):
        return bool(self.entries or self.partial or self.status or self.positioning)

    # ---- painting ----------------------------------------------------------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        radius = self.cfg.get("box_radius", 14) * box_scale(self.cfg)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, self.cfg["bg_opacity"]))
        p.drawRoundedRect(rect, radius, radius)
        if self.positioning:
            p.setPen(QPen(QColor(255, 255, 255, 160), 1, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(rect, radius, radius)

    def resizeEvent(self, event):
        self.grip.move(self.width() - self.grip.width() - 4, self.height() - self.grip.height() - 4)
        pad_x, pad_y = self._padding()
        self.viewport.setGeometry(pad_x, pad_y, max(1, self.width() - 2 * pad_x), max(1, self.height() - 2 * pad_y))
        self._place_content(self._current_offset())

    def eventFilter(self, obj, event):
        if obj is self.grip:
            if event.type() == QEvent.MouseButtonPress:
                self._finish_geometry_animation()
                self._grip_resizing = True
            elif event.type() == QEvent.MouseButtonRelease and self._grip_resizing:
                self._grip_resizing = False
                scale = box_scale(self.cfg)  # sizes are kept at 100 %
                if not self.cfg.get("box_autosize"):
                    self.user_height = round(self.height() / scale)  # autosized height always follows the text
                if self.cfg.get("box_position", "custom") != "custom":
                    avail = self.target_screen().availableGeometry()
                    self.cfg["box_width_pct"] = max(20, min(100, round(self.width() * 100 / avail.width() / scale)))
                else:
                    self._custom_bottom = self.geometry().bottom() + 1
                    self._custom_width = round(self.width() / scale)
                    self._custom_center = self.geometry().x() + self.width() / 2
                self._save_geometry()
                self.on_placement_changed()
                QTimer.singleShot(0, self._fit_geometry)
        return super().eventFilter(obj, event)

    # ---- mouse -------------------------------------------------------------
    def enterEvent(self, e):
        self._hovered = True
        if self._fading_out and (self.entries or self.partial):
            self._fade_in()
        self._update_copy_buttons()
        super().enterEvent(e)

    def _cursor_inside(self):
        return self.geometry().contains(QCursor.pos())

    def leaveEvent(self, e):
        if self._cursor_inside():
            # Moving onto a copy button or the resize grip counts as leaving the box for Qt,
            # but the mouse is still on it: keep the box and its buttons as they are.
            return super().leaveEvent(e)
        self._hovered = False
        self.last_update = time.monotonic()  # the hide countdown starts again once the mouse leaves
        self._update_copy_buttons()
        super().leaveEvent(e)

    def wheelEvent(self, e):
        """Shift + mouse wheel over the box makes the box and its text bigger or smaller."""
        if not e.modifiers() & Qt.ShiftModifier:
            return super().wheelEvent(e)
        e.accept()
        delta = e.angleDelta().y() or e.angleDelta().x()  # some systems turn Shift + wheel into a sideways scroll
        if (delta > 0) != (self._wheel_delta > 0):
            self._wheel_delta = 0
        self._wheel_delta += delta
        steps = int(self._wheel_delta / 120)  # one notch = 120; touchpads send smaller amounts
        if steps:
            self._wheel_delta -= steps * 120
            self.set_scale(self.cfg.get("box_scale", 100) + steps * SCALE_STEP, show_tip=True)

    def max_scale(self):
        """The largest zoom that still leaves the box a caption box and not a wall of text.

        Shift + wheel is also how Windows scrolls sideways, so the box can be zoomed by accident;
        it must never end up covering the screen.
        """
        avail = self.target_screen().availableGeometry()
        scale = box_scale(self.cfg)
        height = max(1, self.height() / scale)     # the box's height at 100 %
        width = max(1, self._custom_width if self.cfg.get("box_position", "custom") == "custom"
                    else self.width() / scale)
        fits = min(avail.height() * 0.6 / height, avail.width() * 0.95 / width)
        return max(SCALE_MIN, min(SCALE_MAX, int(fits * 100)))

    def reset_scale(self):
        """Back to 100 %."""
        self.set_scale(100, show_tip=self._hovered)

    def set_scale(self, percent, show_tip=False):
        """Set the box size (zoom) in %, keeping the box anchored where it is."""
        percent = max(SCALE_MIN, min(SCALE_MAX, int(percent)))
        limit = self.max_scale()
        if percent > max(limit, self.cfg.get("box_scale", 100)):
            percent = max(limit, self.cfg.get("box_scale", 100))  # don't grow past the screen
            show_tip = show_tip and percent != self.cfg.get("box_scale", 100)
        if show_tip:
            QToolTip.showText(QCursor.pos(), f"Size {percent} %", self)
        if percent == self.cfg.get("box_scale", 100):
            return
        self.cfg["box_scale"] = percent
        self.refresh(instant=True)
        self.on_placement_changed()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._finish_geometry_animation()
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._dragged = False
        elif e.button() == Qt.RightButton:
            self.on_context_menu(e.globalPosition().toPoint())

    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() & Qt.LeftButton:
            if not self._dragged and self.cfg.get("box_position") != "custom":
                # Dragging by hand switches from a screen preset to a custom position
                col = self.cfg["box_position"].split("-")[1]
                self._custom_width = round(self._preset_max_width(self.target_screen().availableGeometry(), col)
                                           / box_scale(self.cfg))
                self.cfg["box_position"] = "custom"
            self._dragged = True
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        if self._drag is not None:
            self._drag = None
            if self._dragged:
                self._custom_bottom = self.geometry().bottom() + 1
                self._custom_center = self.geometry().x() + self.width() / 2
                screen = QGuiApplication.screenAt(self.geometry().center())
                if screen is not None:
                    self.cfg["box_screen"] = screen.name()
                self._save_geometry()
                self.on_placement_changed()

    def _save_geometry(self):
        # Save the user's own size (not the auto-grown one), keeping the current bottom edge and center
        g = self.geometry()
        h = self.user_height or g.height()
        w = self._custom_width if self.cfg.get("box_position") == "custom" else g.width()
        x = round(g.x() + g.width() / 2 - w / 2)
        self.on_geometry_changed([x, g.y() + g.height() - h, w, h])
