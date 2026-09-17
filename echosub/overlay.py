# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Always-on-top translucent caption window."""
import itertools
import time

from PySide6.QtCore import QEasingCurve, QEvent, QPointF, QPropertyAnimation, QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QColor, QFont, QFontMetricsF, QGuiApplication, QPainter, QPen, QPixmap, QTextLayout, QTextOption,
)
from PySide6.QtWidgets import QLabel, QSizeGrip, QSizePolicy, QVBoxLayout, QWidget

from . import APP_NAME, languages

MERGE_WINDOW_SEC = 6.0
MERGE_MAX_CHARS = 140
FADE_MS = 160
OUTLINE_OFFSETS = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy] + [(2, 2)]
PENDING_PLACEHOLDER = "…"
ENTER_SHIFT_PX = 12  # how far a new line rises while it fades in (slide mode)

_flag_cache = {}
_entry_keys = itertools.count(1)


def _flag_pixmap(lang):
    path = languages.flag_path(lang)
    if path is None:
        return None
    if path not in _flag_cache:
        pm = QPixmap(path)
        _flag_cache[path] = None if pm.isNull() else pm
    return _flag_cache[path]


def ease_out(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def entry_view(entry):
    """Flatten a caption entry into (original, translated, pending).

    A line made of several sentences shows each one's translation, or its original text
    while that translation is still being computed.
    """
    if "segments" not in entry:
        return entry["original"], entry["translated"], False
    segs = entry["segments"]
    original = " ".join(s["original"] for s in segs)
    translated = " ".join(s["translated"] if s["translated"] is not None else s["original"] for s in segs)
    return original, translated, any(s["translated"] is None for s in segs)


def resolve_alignment(align, rtl):
    """'left' | 'right' | 'center' for a text, given the text_align setting and the text's direction."""
    if align == "reading":
        return "right" if rtl else "left"
    return align if align in ("left", "right") else "center"


class Badge:
    """Language label drawn next to a caption: optional flag and optional text (code or name)."""

    def __init__(self, lang, kind, position, font):
        self.position = position
        self.flag = _flag_pixmap(lang) if kind.startswith("flag") else None
        if kind in ("code", "flag_code") or (kind == "flag" and self.flag is None):
            self.text = languages.code_label(lang)  # a language without a flag image shows its code instead
        elif kind in ("name", "flag_name"):
            self.text = languages.name(lang)
        else:
            self.text = ""
        self.font = QFont(font)
        self.font.setPointSizeF(max(7.0, font.pointSizeF() * 0.8))
        self.font.setBold(True)
        fm = QFontMetricsF(self.font)
        self.gap = fm.averageCharWidth() * 0.6
        self.text_width = fm.horizontalAdvance(self.text) if self.text else 0.0
        self.text_height = fm.height()
        self.flag_height = round(fm.height() * 0.8)
        self.flag_width = (round(self.flag.width() * self.flag_height / self.flag.height()) if self.flag else 0)
        self.width = self.flag_width + self.text_width + (self.gap * 0.6 if self.flag and self.text else 0)
        self.height = max(self.flag_height, self.text_height if self.text else 0)

    def key(self):
        return (self.position, self.text, id(self.flag), self.font.toString())

    def draw(self, p, x, y, color):
        cy = y + self.height / 2
        if self.flag is not None:
            target = QRectF(x, cy - self.flag_height / 2, self.flag_width, self.flag_height)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            opacity = p.opacity()
            p.setOpacity(opacity * color.alphaF())
            p.drawPixmap(target, self.flag, QRectF(self.flag.rect()))
            p.setOpacity(opacity)
            p.setPen(QPen(QColor(0, 0, 0, int(color.alpha() * 0.6)), 1))
            p.setBrush(Qt.NoBrush)
            p.drawRect(target)
            x += self.flag_width + (self.gap * 0.6 if self.text else 0)
        if self.text:
            p.setFont(self.font)
            fm = QFontMetricsF(self.font)
            baseline = cy - self.text_height / 2 + fm.ascent()
            p.setPen(QColor(0, 0, 0, int(color.alpha() * 0.85)))
            for dx, dy in OUTLINE_OFFSETS:
                p.drawText(QPointF(x + dx, baseline + dy), self.text)
            p.setPen(color)
            p.drawText(QPointF(x, baseline), self.text)


class CaptionText(QWidget):
    """Word-wrapped caption text drawn with a dark outline, with an optional language badge.

    Lays text out with QTextLayout so any line height works: below 100% lines overlap
    slightly instead of being clipped, which QLabel's rich text would do. When the text
    changes while animations are on, the old text cross-fades into the new one.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        policy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self._text = ""
        self._font = QFont()
        self._color = QColor("white")
        self._line_height = 100
        self._rtl = False
        self._align = "center"
        self._badge = None
        self._state = None
        self._cache = None  # (width, layout, height, text_top)
        self._old = None    # previous rendering being faded out: (layout, color, badge, badge_xy, start, duration)

    def set(self, text, font, color, alpha, line_height, rtl, align="center", badge=None, crossfade_ms=0):
        color = QColor(color)
        color.setAlpha(alpha)
        state = (text, font.toString(), color.rgba(), line_height, rtl, align, badge.key() if badge else None)
        if state == self._state:
            return
        if crossfade_ms and self._text and text != self._text and self.isVisible() and self.width() > 1:
            layout, _, _ = self._layout(self.width())
            badge_xy = self._badge_position(layout, self.width()) if self._badge and layout.lineCount() else None
            self._old = (layout, QColor(self._color), self._badge, badge_xy, time.monotonic(), crossfade_ms / 1000)
        self._state = state
        self._text, self._font, self._color = text, QFont(font), color
        self._line_height, self._rtl, self._align, self._badge = line_height, rtl, align, badge
        self._cache = None
        self.updateGeometry()
        self.update()

    def animating(self, now):
        if self._old is not None and now - self._old[4] >= self._old[5]:
            self._old = None
        return self._old is not None

    def _badge_side(self):
        """'left' or 'right' for before/after badges; before = where reading starts."""
        start = "right" if self._rtl else "left"
        end = "left" if self._rtl else "right"
        return start if self._badge.position == "before" else end

    def _layout(self, width):
        width = max(1, width)
        if self._cache and self._cache[0] == width:
            return self._cache[1:]
        badge = self._badge if self._text else None
        inline = badge is not None and badge.position in ("before", "after")
        reserve = badge.width + badge.gap if inline else 0.0
        text_left = reserve if inline and self._badge_side() == "left" else 0.0
        text_top = badge.height + badge.gap * 0.5 if badge is not None and badge.position == "above" else 0.0

        layout = QTextLayout(self._text, self._font)
        side = resolve_alignment(self._align, self._rtl)
        qt_align = {"left": Qt.AlignLeft | Qt.AlignAbsolute, "right": Qt.AlignRight | Qt.AlignAbsolute,
                    "center": Qt.AlignHCenter}[side]
        option = QTextOption(qt_align)
        option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        option.setTextDirection(Qt.RightToLeft if self._rtl else Qt.LeftToRight)
        layout.setTextOption(option)
        natural = QFontMetricsF(self._font).height()
        step = natural * self._line_height / 100
        y, count = text_top, 0
        layout.beginLayout()
        while True:
            line = layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(max(1.0, width - reserve))
            line.setPosition(QPointF(text_left, y))
            y += step
            count += 1
        layout.endLayout()
        # The last line gets at least its natural height so nothing hangs outside the widget
        text_bottom = text_top + ((count - 1) * step + max(natural, step) if count else 0)
        height = text_bottom
        if badge is not None:
            if badge.position == "below":
                height = text_bottom + badge.gap * 0.5 + badge.height
            elif inline:
                height = max(text_bottom, text_top + badge.height)
        height = int(height + 0.999) + 2 if count else 0
        self._cache = (width, layout, height, text_top)
        return layout, height, text_top

    def _badge_position(self, layout, width):
        badge = self._badge
        count = layout.lineCount()
        if badge.position in ("above", "below"):
            side = resolve_alignment(self._align, self._rtl)
            x = {"left": 0.0, "right": width - badge.width, "center": (width - badge.width) / 2}[side]
            if badge.position == "above":
                return x, 0.0
            last = layout.lineAt(count - 1)
            natural = QFontMetricsF(self._font).height()
            return x, last.y() + max(natural, natural * self._line_height / 100) + badge.gap * 0.5
        ref = layout.lineAt(0 if badge.position == "before" else count - 1)
        rect = ref.naturalTextRect()
        natural = QFontMetricsF(self._font).height()
        y = ref.y() + (natural - badge.height) / 2
        if self._badge_side() == "left":
            return rect.left() - badge.gap - badge.width, y
        return rect.right() + badge.gap, y

    def preferred_width(self, max_width):
        """Width the text actually needs when wrapped at max_width (for autosizing the box)."""
        if not self._text or not self.isVisibleTo(self.parentWidget()):
            return 0
        layout, _, _ = self._layout(max_width)
        widest = max((layout.lineAt(i).naturalTextWidth() for i in range(layout.lineCount())), default=0.0)
        badge = self._badge
        if badge is not None:
            if badge.position in ("before", "after"):
                widest += badge.width + badge.gap
            else:
                widest = max(widest, badge.width)
        return min(max_width, int(widest + 0.999) + 4)  # + outline

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._layout(width)[1]

    def sizeHint(self):
        return QSize(self.width(), self.heightForWidth(self.width()))

    def minimumSizeHint(self):
        return QSize(0, 0)

    @staticmethod
    def _draw(p, layout, color, badge, badge_xy):
        p.setPen(QColor(0, 0, 0, int(color.alpha() * 0.85)))
        for dx, dy in OUTLINE_OFFSETS:
            layout.draw(p, QPointF(dx, dy))
        p.setPen(color)
        layout.draw(p, QPointF(0, 0))
        if badge is not None and badge_xy is not None:
            badge.draw(p, badge_xy[0], badge_xy[1], color)

    def paintEvent(self, event):
        line = self.parentWidget()
        reveal = getattr(line, "reveal", 1.0)
        if reveal <= 0 or (not self._text and self._old is None):
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.translate(0, (1 - reveal) * getattr(line, "reveal_shift", 0))
        new_weight = 1.0
        now = time.monotonic()
        if self.animating(now):
            old_layout, old_color, old_badge, old_xy, start, duration = self._old
            new_weight = ease_out((now - start) / duration)
            p.setOpacity(reveal * (1 - new_weight))
            self._draw(p, old_layout, old_color, old_badge, old_xy)
        if self._text:
            layout, _, _ = self._layout(self.width())
            badge_xy = self._badge_position(layout, self.width()) if self._badge and layout.lineCount() else None
            p.setOpacity(reveal * new_weight)
            self._draw(p, layout, self._color, self._badge, badge_xy)


class CaptionLine(QWidget):
    """One caption entry: optional original-text row above the translation row."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.original = CaptionText(self)
        self.translated = CaptionText(self)
        self.lay.addWidget(self.original)
        self.lay.addWidget(self.translated)
        self.reveal = 1.0          # 0 = invisible, 1 = fully shown (enter/leave animation)
        self.reveal_shift = 0      # px the line is pushed down while not fully revealed
        self._reveal_anim = None   # (from, to, start, duration)
        self.ghost = False         # removed line still sliding/fading out

    def animate_reveal(self, start_value, end_value, duration_ms, shift):
        self.reveal = start_value
        self.reveal_shift = shift
        self._reveal_anim = (start_value, end_value, time.monotonic(), duration_ms / 1000)

    def tick(self, now):
        """Advance animations; returns True while something is still moving."""
        active = False
        if self._reveal_anim is not None:
            a, b, start, duration = self._reveal_anim
            t = (now - start) / duration
            self.reveal = a + (b - a) * ease_out(t)
            if t >= 1:
                self.reveal = b
                self._reveal_anim = None
            else:
                active = True
        return active or self.original.animating(now) or self.translated.animating(now)

    def set(self, entry, cfg, partial, crossfade_ms=0):
        original, translated, pending = entry_view(entry)
        lang = entry["lang"]
        target = cfg["target_lang"]
        live = partial

        trans_color, orig_color = cfg["text_color"], cfg["original_color"]
        spk = entry.get("speaker")
        if spk is not None and cfg["speaker_detection"] and cfg["speaker_colors"]:
            spk_color = cfg["speaker_colors"][spk % len(cfg["speaker_colors"])]
            if cfg["speaker_color_target"] in ("both", "translation"):
                trans_color = spk_color
            if cfg["speaker_color_target"] in ("both", "original"):
                orig_color = spk_color

        lh, align = cfg["line_height"], cfg["text_align"]
        self.lay.setSpacing(cfg["original_gap"])

        of = QFont(cfg["font_family"])
        of.setPointSize(cfg["original_font_size"])
        of.setBold(cfg["original_bold"])
        tf = QFont(cfg["font_family"])
        tf.setPointSize(cfg["font_size"])

        def badge(font, text_lang, which):
            kind = cfg[f"{which}_label"]
            if kind == "none" or not text_lang:
                return None
            return Badge(text_lang, kind, cfg[f"{which}_label_position"], font)

        same_language = bool(translated) and original == translated and not pending
        if cfg["show_original"] and original and not same_language:
            # Two rows: original transcript (with its language label) and the translation.
            # While the translation is being computed the second row shows a placeholder, so the
            # layout doesn't jump when it arrives.
            alpha = 165 if live else 255
            self.original.show()
            self.original.set(original, of, orig_color, alpha, lh, lang in languages.RTL, align,
                              badge(of, lang, "original"), crossfade_ms)
            waiting = pending or not translated
            tf.setBold(cfg["translation_bold"] and not live and not waiting)
            main = PENDING_PLACEHOLDER if waiting else translated
            self.translated.set(main, tf, trans_color, 110 if waiting else alpha, lh, target in languages.RTL,
                                align, None if waiting else badge(tf, target, "translation"), crossfade_ms)
        else:
            # One row: the translation, or the original text when there is nothing else to show
            self.original.hide()
            dim = live or pending
            showing_original = pending or same_language or not translated
            main = translated or original
            main_lang = lang if showing_original else target
            tf.setBold(cfg["translation_bold"] and not dim)
            label = badge(tf, lang, "original") if showing_original else badge(tf, target, "translation")
            self.translated.set(main, tf, trans_color, 165 if dim else 255, lh, main_lang in languages.RTL,
                                align, label, crossfade_ms)

    def preferred_width(self, max_width):
        return max(self.original.preferred_width(max_width), self.translated.preferred_width(max_width))


class CaptionOverlay(QWidget):
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

    def add_final(self, seg_id, original, translated, lang, speaker=None):
        """translated=None means the translation is on its way (see set_translation)."""
        now = time.monotonic()
        segment = {"id": seg_id, "original": original, "translated": translated}
        last = self.entries[-1] if self.entries else None
        if (last is not None and speaker is not None and last["speaker"] == speaker
                and last["lang"] == lang and now - last["time"] < MERGE_WINDOW_SEC
                and len(entry_view(last)[0]) + len(original) < MERGE_MAX_CHARS):
            # Same person still talking: continue the current line
            last["segments"].append(segment)
            last["time"] = now
        else:
            self.entries.append({"key": f"e{next(_entry_keys)}", "segments": [segment], "lang": lang,
                                 "speaker": speaker, "time": now})
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

    def set_partial(self, original, translated, lang):
        self.partial = ({"original": original, "translated": translated, "lang": lang, "speaker": None}
                        if original else None)
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

    def refresh(self):
        animation = self._animation()
        animate = animation is not None and self.is_shown()
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

        pad_x, pad_y = self.cfg.get("box_padding_x", 24), self.cfg.get("box_padding_y", 12)
        self.content_layout.setSpacing(self.cfg["entry_spacing"])
        status_align = {"left": Qt.AlignLeft, "right": Qt.AlignRight}.get(self.cfg["text_align"], Qt.AlignHCenter)
        self.status_label.setAlignment(status_align | Qt.AlignVCenter)

        # Nothing to say -> the window disappears completely
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

    def is_shown(self):
        return self.isVisible() and not self._fading_out

    # ---- placement -----------------------------------------------------------
    def target_screen(self):
        name = self.cfg.get("box_screen")
        for screen in QGuiApplication.screens():
            if name and screen.name() == name:
                return screen
        return QGuiApplication.primaryScreen()

    def _padding(self):
        return self.cfg.get("box_padding_x", 24), self.cfg.get("box_padding_y", 12)

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
                            int(avail.width() * self.cfg["box_width_pct"] / 100)))

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
            if position == "custom":
                max_width = self._custom_width
                width = self._content_width(max_width) if autosize else max_width
                needed = self._needed_height(width)
                height = needed if autosize else max(self.user_height, needed)
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
                height = min(avail.height(), needed if autosize else max(self.user_height, needed))
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
        radius = self.cfg.get("box_radius", 14)
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
                if not self.cfg.get("box_autosize"):
                    self.user_height = self.height()  # autosized height always follows the text
                if self.cfg.get("box_position", "custom") != "custom":
                    avail = self.target_screen().availableGeometry()
                    self.cfg["box_width_pct"] = max(20, min(100, round(self.width() * 100 / avail.width())))
                else:
                    self._custom_bottom = self.geometry().bottom() + 1
                    self._custom_width = self.width()
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
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hovered = False
        self.last_update = time.monotonic()  # the hide countdown starts again once the mouse leaves
        super().leaveEvent(e)

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
                self._custom_width = self._preset_max_width(self.target_screen().availableGeometry(), col)
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
