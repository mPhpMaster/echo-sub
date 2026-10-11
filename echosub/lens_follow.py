# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""EchoSub Lens: the lens that follows the mouse — only the text around the pointer is translated.

The lens stays put while the pointer moves a little inside it (so reading a translation does not
make it jump), and moves once the pointer has gone a quarter of its size away.
"""
from PySide6.QtCore import QPoint, QRect

SIZES = {
    "small": (320, 120),
    "medium": (480, 180),
    "large": (720, 280),
    "wide": (960, 160),
}
MIN_SIZE = (160, 60)
GROW = 1.25


def lens_rect(pointer, screen_size, size):
    """The lens around `pointer` (relative to its screen), kept whole on the screen."""
    w = min(int(size[0]), screen_size.width())
    h = min(int(size[1]), screen_size.height())
    x = min(max(pointer.x() - w // 2, 0), screen_size.width() - w)
    y = min(max(pointer.y() - h // 2, 0), screen_size.height() - h)
    return QRect(x, y, w, h)


def should_move(anchor, pointer, size):
    """True once the pointer has left the middle of the lens it last placed."""
    if anchor is None:
        return True
    delta = QPoint(pointer) - QPoint(anchor)
    return abs(delta.x()) > size[0] / 4 or abs(delta.y()) > size[1] / 4


def resized(size, bigger, limit):
    """The lens a step bigger or smaller, within MIN_SIZE and `limit` (the screen's QSize)."""
    factor = GROW if bigger else 1 / GROW
    w = min(max(round(size[0] * factor), MIN_SIZE[0]), limit.width())
    h = min(max(round(size[1] * factor), MIN_SIZE[1]), limit.height())
    return [w, h]
