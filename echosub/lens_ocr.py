# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""EchoSub Lens: reading the text on the screen with Windows' own OCR, and grouping it into blocks.

Windows 10 and 11 recognize text offline for every language whose OCR pack is installed
(Settings → Time & language → Language). Nothing is downloaded and nothing leaves the PC.
"""
import asyncio
import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

AUTO = "auto"            # the languages of the Windows user profile
MAX_SCALE = 2.0          # small text is read better when the picture is enlarged first
SCALE_BELOW = 1600       # ... but only pictures narrower than this are enlarged


@dataclass
class Box:
    x: float
    y: float
    w: float
    h: float

    @property
    def right(self):
        return self.x + self.w

    @property
    def bottom(self):
        return self.y + self.h

    def united(self, other):
        x, y = min(self.x, other.x), min(self.y, other.y)
        return Box(x, y, max(self.right, other.right) - x, max(self.bottom, other.bottom) - y)


@dataclass
class Line:
    """One line of text, as Windows read it: its words and where they are (image pixels)."""
    words: list           # [(text, Box)]

    @property
    def box(self):
        box = self.words[0][1]
        for _, other in self.words[1:]:
            box = box.united(other)
        return box

    @property
    def text(self):
        return " ".join(word for word, _ in self.words)


@dataclass
class Block:
    """Lines that belong together (a paragraph, a menu item, a caption): translated as one text."""
    lines: list = field(default_factory=list)
    translation: str = ""
    background: tuple = (255, 255, 255)
    foreground: tuple = (0, 0, 0)

    @property
    def box(self):
        box = self.lines[0].box
        for line in self.lines[1:]:
            box = box.united(line.box)
        return box

    @property
    def text(self):
        return " ".join(line.text for line in self.lines)

    @property
    def line_height(self):
        return sum(line.box.h for line in self.lines) / len(self.lines)


def available_languages():
    """BCP-47 tags of the OCR languages installed in Windows, e.g. ['ar-SA', 'en-US']."""
    try:
        from winrt.windows.media.ocr import OcrEngine
        return [str(lang.language_tag) for lang in OcrEngine.available_recognizer_languages]
    except Exception:
        log.exception("Windows OCR is not available")
        return []


def split_columns(line, gap_factor=2.2):
    """Cut a line where its words are far apart: two columns, a menu bar, a toolbar."""
    parts, current = [], [line.words[0]]
    for word in line.words[1:]:
        previous, box = current[-1][1], word[1]
        height = max(previous.h, box.h, 1)
        gap = max(box.x - previous.right, previous.x - box.right)  # right-to-left text runs leftwards
        if gap > gap_factor * height:
            parts.append(Line(current))
            current = []
        current.append(word)
    parts.append(Line(current))
    return parts


def group_blocks(lines):
    """Join lines that read as one paragraph: same size, close below each other, overlapping sideways."""
    pieces = sorted((part for line in lines if line.words for part in split_columns(line)),
                    key=lambda line: (line.box.y, line.box.x))
    blocks = []
    for line in pieces:
        box = line.box
        for block in reversed(blocks[-8:]):  # only blocks just above can continue
            last = block.lines[-1].box
            height = block.line_height
            same_size = 0.7 <= box.h / max(height, 1) <= 1.45
            close_below = -0.3 * height <= box.y - last.bottom <= 0.9 * height
            overlap = min(box.right, last.right) - max(box.x, last.x)
            if same_size and close_below and overlap > 0.3 * min(box.w, last.w):
                block.lines.append(line)
                break
        else:
            blocks.append(Block([line]))
    return blocks


def worth_translating(text):
    """Skip numbers, prices, times and single symbols: they read the same in every language."""
    letters = sum(1 for ch in text if ch.isalpha())
    return letters >= 2


class Reader:
    """Reads a QImage. One per worker thread; `language` is a tag from available_languages() or AUTO."""

    def __init__(self, language=AUTO):
        from winrt.windows.globalization import Language
        from winrt.windows.media.ocr import OcrEngine

        engine = None
        if language != AUTO:
            engine = OcrEngine.try_create_from_language(Language(language))
        if engine is None:
            engine = OcrEngine.try_create_from_user_profile_languages()
        if engine is None:
            raise RuntimeError("Windows has no text recognition (OCR) language installed")
        self._engine = engine
        self.language = str(engine.recognizer_language.language_tag)
        self.max_dimension = int(OcrEngine.max_image_dimension)
        self._loop = asyncio.new_event_loop()

    def close(self):
        self._loop.close()

    def read(self, image):
        """Lines found in `image` (a QImage); boxes are in the image's own pixels."""
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QImage
        from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
        from winrt.windows.storage.streams import DataWriter

        scale = 1.0
        if image.width() < SCALE_BELOW:
            scale = min(MAX_SCALE, self.max_dimension / max(image.width(), image.height(), 1))
        scale = max(scale, 1.0)
        if scale > 1.0:
            image = image.scaled(int(image.width() * scale), int(image.height() * scale),
                                 Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        image = image.convertToFormat(QImage.Format_ARGB32)  # BGRA in memory on Windows
        width, height = image.width(), image.height()
        if max(width, height) > self.max_dimension:
            raise ValueError("The area is too large to read")
        writer = DataWriter()
        writer.write_bytes(bytes(image.constBits())[: width * height * 4])
        bitmap = SoftwareBitmap.create_copy_from_buffer(writer.detach_buffer(), BitmapPixelFormat.BGRA8,
                                                        width, height)
        result = self._loop.run_until_complete(self._recognize(bitmap))
        lines = []
        for line in result.lines:
            words = []
            for word in line.words:
                r = word.bounding_rect
                words.append((str(word.text), Box(r.x / scale, r.y / scale, r.width / scale, r.height / scale)))
            if words:
                lines.append(Line(words))
        return lines

    async def _recognize(self, bitmap):
        return await self._engine.recognize_async(bitmap)
