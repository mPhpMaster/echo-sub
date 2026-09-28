# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""The pieces a caption is drawn from: language badges, copy buttons, and the text itself."""
import itertools
import time

from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor, QCursor, QFont, QFontMetricsF, QGuiApplication, QPainter, QPen, QPixmap, QPolygonF, QTextLayout,
    QTextOption,
)
from PySide6.QtWidgets import QSizePolicy, QToolTip, QVBoxLayout, QWidget

from . import languages

MERGE_WINDOW_SEC = 6.0
MERGE_MAX_CHARS = 140
FADE_MS = 160
OUTLINE_OFFSETS = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy] + [(2, 2)]
PENDING_PLACEHOLDER = "…"
ENTER_SHIFT_PX = 12  # how far a new line rises while it fades in (slide mode)
SCALE_MIN, SCALE_MAX, SCALE_STEP = 50, 300, 10  # box size (zoom) in %; Shift + wheel changes it by one step

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


def box_scale(cfg):
    """Size (zoom) factor applied to the box's fonts, spacing, padding, corners and width."""
    return max(SCALE_MIN, min(SCALE_MAX, cfg.get("box_scale", 100))) / 100


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

    def __init__(self, lang, kind, position, font, extra=""):
        self.position = position
        self.flag = _flag_pixmap(lang) if kind.startswith("flag") else None
        if kind in ("code", "flag_code") or (kind == "flag" and self.flag is None):
            self.text = languages.code_label(lang)  # a language without a flag image shows its code instead
        elif kind in ("name", "flag_name"):
            self.text = languages.name(lang)
        else:
            self.text = ""
        if extra:  # the microphone's label ("You"), so it is clear who is talking
            self.text = f"{extra} {self.text}".strip()
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


class CopyButton(QWidget):
    """Small copy icon shown over a caption row; copies that row's text to the clipboard."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.text = ""
        self._hover = False
        self._copied_until = 0.0
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Copy this text")

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.text:
            QGuiApplication.clipboard().setText(self.text)
            self._copied_until = time.monotonic() + 1.2
            QToolTip.showText(e.globalPosition().toPoint(), "Copied", self)
            self.update()
        e.accept()

    def mouseReleaseEvent(self, e):
        e.accept()  # never starts a box drag

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        copied = time.monotonic() < self._copied_until
        alpha = 110 if copied or self._hover else 55
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, alpha))
        side = min(self.width(), self.height())
        p.drawRoundedRect(QRectF(0, 0, side, side), side * 0.25, side * 0.25)
        pen = QPen(QColor(60, 220, 130) if copied else QColor(255, 255, 255, 235 if self._hover else 190))
        pen.setWidthF(max(1.0, side * 0.09))
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        if copied:  # a check mark while the text has just been copied
            p.drawPolyline(QPolygonF([QPointF(side * 0.26, side * 0.53), QPointF(side * 0.43, side * 0.70),
                                      QPointF(side * 0.76, side * 0.31)]))
        else:       # two stacked sheets
            r = side * 0.12
            p.drawRoundedRect(QRectF(side * 0.20, side * 0.20, side * 0.44, side * 0.44), r, r)
            p.drawRoundedRect(QRectF(side * 0.36, side * 0.36, side * 0.44, side * 0.44), r, r)


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

    @property
    def text(self):
        return self._text

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
        from_mic = entry.get("source") == "mic"
        if from_mic and cfg.get("mic_color"):
            trans_color = orig_color = cfg["mic_color"]
        spk = entry.get("speaker")
        if spk is not None and cfg["speaker_detection"] and cfg["speaker_colors"]:
            spk_color = cfg["speaker_colors"][spk % len(cfg["speaker_colors"])]
            if cfg["speaker_color_target"] in ("both", "translation"):
                trans_color = spk_color
            if cfg["speaker_color_target"] in ("both", "original"):
                orig_color = spk_color

        lh, align = cfg["line_height"], cfg["text_align"]
        scale = box_scale(cfg)
        self.lay.setSpacing(round(cfg["original_gap"] * scale))

        of = QFont(cfg["font_family"])
        of.setPointSizeF(max(1.0, cfg["original_font_size"] * scale))
        of.setBold(cfg["original_bold"])
        tf = QFont(cfg["font_family"])
        tf.setPointSizeF(max(1.0, cfg["font_size"] * scale))

        def badge(font, text_lang, which):
            kind = cfg[f"{which}_label"]
            label = cfg.get("mic_label", "") if from_mic else ""
            if kind == "none" and not label:
                return None
            if not text_lang and not label:
                return None
            return Badge(text_lang, kind if kind != "none" else "none", cfg[f"{which}_label_position"], font,
                         extra=label)

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
