# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""EchoSub Lens: the see-through window that lays each translation over the text it translates.

Clicks go straight through it to the page or program underneath. While Ctrl is held (or "select
mode" is on) the translations themselves take the mouse: select a word or a sentence and copy it.
It shows in screenshots and screen sharing (Discord, Teams, OBS) unless the user hides it there.
"""
import ctypes
import sys

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QLabel, QMenu, QWidget

from . import languages, lens_style

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
WDA_NONE = 0x00
WDA_EXCLUDEFROMCAPTURE = 0x11
MIN_FONT_PX = 9
READABLE_PX = 12      # small print is translated a little larger when there is room
FONT_FAMILY = "Segoe UI"
FRAME_MARGIN = 4      # the lens frame is drawn just outside the area Lens reads, never inside it
FRAME_COLOR = QColor(79, 195, 247, 200)


def _font(family, px, bold=False):
    font = QFont(family)
    font.setPixelSize(max(int(px), MIN_FONT_PX))
    font.setBold(bool(bold))
    return font


def fit_font_px(text, width, height, start_px, family=FONT_FAMILY, minimum=MIN_FONT_PX, bold=False):
    """The largest pixel size, up to `start_px`, at which `text` wrapped to `width` fits in `height`."""
    px = max(int(start_px), minimum)
    while True:
        needed = QFontMetrics(_font(family, px, bold)).boundingRect(
            QRect(0, 0, max(int(width), 1), 100_000), Qt.TextWordWrap, text).height()
        if needed <= height or px <= minimum:
            return px
        px -= 1


def fit_line_px(text, width, height, start_px, family=FONT_FAMILY, minimum=MIN_FONT_PX, bold=False):
    """The largest pixel size, up to `start_px`, at which `text` fits on one line `width` × `height`."""
    px = max(int(start_px), minimum)
    while px > minimum:
        metrics = QFontMetrics(_font(family, px, bold))
        if metrics.horizontalAdvance(text) <= width and metrics.height() <= height:
            break
        px -= 1
    return px


def _css(rgb, alpha=255):
    return f"rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, {alpha})"


class BlockLabel(QLabel):
    """One translated block. Selectable; right-click offers to copy it, its original or everything."""

    def __init__(self, parent, block, rtl, style, copy_all):
        super().__init__(block.translation, parent)
        self.block = block
        self._copy_all = copy_all
        self.menu_open = False
        self.setTextFormat(Qt.PlainText)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        self.setLayoutDirection(Qt.RightToLeft if rtl else Qt.LeftToRight)
        self.setAlignment((Qt.AlignRight if rtl else Qt.AlignLeft) | Qt.AlignVCenter)
        self.setToolTip(block.text)
        background, foreground = lens_style.colors(style, block.background, block.foreground)
        self.setStyleSheet(f"QLabel {{ background: {_css(background, round(255 * style['opacity']))}; "
                           f"color: {_css(foreground)}; padding: 0px 2px; "
                           f"border-radius: {int(style['radius'])}px; }}")

    def mousePressEvent(self, event):
        self.window().activateWindow()  # take the keyboard, so Ctrl+C copies the selection
        super().mousePressEvent(event)

    def _menu(self, pos):
        menu = QMenu(self)
        selected = self.selectedText()
        if selected:
            menu.addAction("Copy selection", lambda: _copy(selected))
        menu.addAction("Copy this translation", lambda: _copy(self.block.translation))
        menu.addAction("Copy the original text", lambda: _copy(self.block.text))
        menu.addSeparator()
        menu.addAction("Copy all translations", self._copy_all)
        self.menu_open = True
        try:
            menu.exec(self.mapToGlobal(pos))
        finally:
            self.menu_open = False


def _copy(text):
    QGuiApplication.clipboard().setText(text)


class LensOverlay(QWidget):
    """Covers the translated area exactly. `show_blocks()` draws translations; `clear()` removes them."""

    def __init__(self, style=None):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowTitle("EchoSub Lens")
        self.style = lens_style.merged(style)
        self.interactive = False
        self.capture_hidden = False   # True: left out of screenshots and screen sharing
        self.labels = []
        self._blocks, self._target = [], None
        self._scale = 1.0
        self.frame = False            # a thin frame around the area (the lens that follows the mouse)
        self._margin = 0

    # ---- placement ---------------------------------------------------------
    def cover(self, rect, scale, frame=False):
        """Lie over `rect` (global logical pixels); OCR boxes arrive in pixels `scale` times larger.

        With `frame`, the window is a little larger than `rect` and the frame is drawn in that margin,
        so the photos Lens takes of `rect` never contain it.
        """
        self._scale = scale or 1.0
        self.frame = frame
        self._margin = FRAME_MARGIN if frame else 0
        m = self._margin
        outer = rect.adjusted(-m, -m, m, m)
        if self.geometry() != outer:
            self.setGeometry(outer)
        self.update()
        if not self.isVisible():
            self.show()
            self._apply_styles()

    def paintEvent(self, event):
        if not self.frame:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(FRAME_COLOR, 2))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 5, 5)
        p.end()

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_styles()

    # ---- content -----------------------------------------------------------
    def clear(self):
        self._blocks = []
        self._remove_labels()

    def _remove_labels(self):
        for label in self.labels:
            label.hide()
            label.deleteLater()
        self.labels = []

    def set_style(self, style):
        """New font, size or colours: what is on the screen is drawn again at once."""
        self.style = lens_style.merged(style)
        if self._blocks:
            self.show_blocks(self._blocks, self._target)

    def show_blocks(self, blocks, target):
        """Replace what is shown with `blocks` (lens_ocr.Block with .translation set)."""
        self._remove_labels()
        self._blocks, self._target = list(blocks), target
        rtl = target in languages.RTL
        self.labels = [self._place(block, rtl) for block in self._blocks if block.translation]

    def _place(self, block, rtl):
        style, s = self.style, self._scale
        family, bold = style["font_family"], style["bold"]
        scale = style["size_scale"] / 100
        fixed = style["size_mode"] == "fixed"
        box = block.box
        x, y, w, h = box.x / s, box.y / s, box.w / s, box.h / s
        pad = max(2.0, 0.15 * block.line_height / s)
        x, w, h = x - pad, max(w + 2 * pad, 24), h + pad
        if fixed:
            start_px = int(style["font_px"])
        else:
            start_px = max(block.line_height / s * 1.05, READABLE_PX) * scale
        one_line = len(block.lines) == 1  # a label or a button: kept on one line, a little wider if need be
        if one_line:
            natural = QFontMetrics(_font(family, start_px, bold)).horizontalAdvance(block.translation) + 8
            w = max(w, min(natural, w * (3 if fixed else 1.6), self.width() - 2 * self._margin - x))
        if fixed:
            px = start_px
        elif one_line:
            px = fit_line_px(block.translation, w - 6, h * 1.3 * scale, start_px, family, bold=bold)
        else:
            px = fit_font_px(block.translation, w - 4, h * scale, start_px, family, bold=bold)
        label = BlockLabel(self, block, rtl, style, self.copy_all)
        label.setWordWrap(not one_line or fixed)
        label.setFont(_font(family, px, bold))
        needed = label.heightForWidth(int(w)) if label.wordWrap() else label.sizeHint().height()
        height = max(box.h / s + pad, needed)  # rather grow than cut words off
        label.setGeometry(int(x + self._margin), int(y - pad / 2 + self._margin), int(w), int(height))
        label.show()
        return label

    def all_text(self):
        return "\n".join(label.block.translation for label in self.labels)

    def copy_all(self):
        _copy(self.all_text())

    def covered(self):
        """Rectangles (in this window) where a screenshot shows a translation instead of the page."""
        if self.capture_hidden or not self.isVisible() or self.windowOpacity() == 0.0:
            return []
        return [label.geometry().translated(-self._margin, -self._margin) for label in self.labels]

    def engaged(self):
        """True while somebody is selecting or copying: the translations must stay as they are."""
        return any(label.hasSelectedText() or label.menu_open for label in self.labels)

    # ---- screenshots and screen sharing ---------------------------------------
    def set_capture_hidden(self, hidden):
        self.capture_hidden = bool(hidden)
        self._apply_styles()

    def set_peeking(self, peeking):
        """Fully transparent for a moment, so Lens can see the page under its own translations."""
        self.setWindowOpacity(0.0 if peeking else 1.0)

    # ---- mouse: through to the app, or ours while Ctrl is held ----------------
    def set_interactive(self, interactive):
        if interactive == self.interactive:
            return
        self.interactive = interactive
        self._apply_styles()
        if not interactive:
            for label in self.labels:
                label.setSelection(0, 0)

    def _apply_styles(self):
        if sys.platform != "win32" or not self.isVisible():
            return
        user32 = ctypes.windll.user32
        hwnd = int(self.winId())
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE) | WS_EX_LAYERED
        if self.interactive:
            style &= ~(WS_EX_TRANSPARENT | WS_EX_NOACTIVATE)
        else:
            style |= WS_EX_TRANSPARENT | WS_EX_NOACTIVATE
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        # Windows 10 2004 and later can leave a window out of screenshots and screen sharing
        user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE if self.capture_hidden else WDA_NONE)
