# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""EchoSub Lens: watching an area of the screen, and reading + translating it when it changes.

The area is photographed a few times a second on the Qt thread (cheap). A tiny grey thumbnail tells
whether anything changed. While the picture is still moving (scrolling, a page loading) the old
translations are taken away; once it settles, a worker thread reads the text and translates it.

The translations show in screenshots (so screen sharing shows them too), which means Lens's own
photos contain them. Where a translation lies is left out of the comparison, the text is only ever
read from a photo without translations, and every few seconds Lens makes them invisible for a frame
to see whether the page underneath changed.
"""
import logging
import queue
import threading
import time

import numpy as np
from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QImage

from . import lens_ocr, lens_translate

log = logging.getLogger(__name__)

THUMB = (192, 108)
PIXEL_CHANGE = 24        # grey levels a thumbnail pixel must move to count as changed
CHANGED_SHARE = 0.002    # share of changed thumbnail pixels that means "the screen changed"
MAX_WAIT = 3.0           # s: read a picture that never settles (a video) at least this often
PEEK_MS = 60             # how long the translations are invisible while Lens looks underneath
MIN_VISIBLE = 0.05       # below this share of the area left uncovered, only looking underneath tells
EDGE = 3                 # px: a block this close to the left or right side may be a word cut in two
FRAGMENT = 0.2           # ... and if it is narrower than this share of the area, it is left out


def thumbnail(image):
    small = image.scaled(THUMB[0], THUMB[1], Qt.IgnoreAspectRatio, Qt.FastTransformation)
    small = small.convertToFormat(QImage.Format_Grayscale8)
    stride = small.bytesPerLine()
    data = np.frombuffer(bytes(small.constBits()), np.uint8)[: stride * small.height()]
    return data.reshape(small.height(), stride)[:, : small.width()].astype(np.int16)


def changed(a, b, hidden=None):
    """Whether two thumbnails differ, leaving out the `hidden` cells (where translations are drawn)."""
    if a is None or b is None or a.shape != b.shape:
        return True
    diff = np.abs(a - b) > PIXEL_CHANGE
    if hidden is None or not hidden.any():
        return float(np.mean(diff)) > CHANGED_SHARE
    visible = ~hidden
    count = int(visible.sum())
    if count < MIN_VISIBLE * hidden.size:
        return False
    return int((diff & visible).sum()) / count > CHANGED_SHARE


def thumb_mask(rects, width, height):
    """Thumbnail cells under `rects` (QRects in an area `width` × `height` logical pixels), one cell wider."""
    if not rects:
        return None
    mask = np.zeros((THUMB[1], THUMB[0]), bool)
    sx, sy = THUMB[0] / max(width, 1), THUMB[1] / max(height, 1)
    for r in rects:
        x0, y0 = max(int(r.x() * sx) - 1, 0), max(int(r.y() * sy) - 1, 0)
        x1, y1 = int(np.ceil((r.x() + r.width()) * sx)) + 1, int(np.ceil((r.y() + r.height()) * sy)) + 1
        mask[y0:y1, x0:x1] = True
    return mask


def image_array(image):
    """RGB pixels of a QImage as a numpy array (height, width, 3)."""
    image = image.convertToFormat(QImage.Format_RGB888)
    stride = image.bytesPerLine()
    data = np.frombuffer(bytes(image.constBits()), np.uint8)[: stride * image.height()]
    return data.reshape(image.height(), stride)[:, : image.width() * 3].reshape(image.height(), image.width(), 3)


def cut_at_edge(block, width):
    """A short piece of text touching the side of the area: most likely part of a word or line cut off."""
    box = block.box
    touches = box.x <= EDGE or box.right >= width - EDGE
    return touches and box.w < FRAGMENT * width


def colors_of(pixels, box):
    """(background, text colour) for a block: the commonest colour under it, and black or white on it."""
    h, w = pixels.shape[:2]
    x0, y0 = max(int(box.x), 0), max(int(box.y), 0)
    x1, y1 = min(int(box.right) + 1, w), min(int(box.bottom) + 1, h)
    if x1 <= x0 or y1 <= y0:
        return (255, 255, 255), (0, 0, 0)
    region = pixels[y0:y1, x0:x1].reshape(-1, 3)
    background = tuple(int(v) for v in np.median(region, axis=0))
    luminance = 0.299 * background[0] + 0.587 * background[1] + 0.114 * background[2]
    return background, ((0, 0, 0) if luminance > 140 else (255, 255, 255))


class LensScanner(QObject):
    """Emits `result(blocks)` with translated blocks, `stale()` when they no longer match the screen."""
    result = Signal(object)
    stale = Signal()
    status = Signal(str)
    _done = Signal(int, object, object)

    def __init__(self, interval_ms=700):
        super().__init__()
        self.area = None             # (QScreen, QRect relative to that screen)
        self.target = "ar"
        self.ocr_language = lens_ocr.AUTO
        self.translator = None       # lens_translate.LensTranslator
        self.covered = lambda: []    # QRects of the area where a photo shows a translation
        self.peeking = lambda on: None  # makes the translations invisible (True) and back (False)
        self.paused = lambda: False  # True while somebody selects or copies a translation
        self.peek_every = 5.0        # s between looks under the translations; 0: never
        self.trim_edges = False      # leave out words cut by the sides (the lens around the mouse)
        self.generation = 0
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.tick)
        self._previous = None        # thumbnail of the last photo
        self._submitted = None       # thumbnail of the photo whose translations are (being) shown
        self._showing = False
        self._last_blocks = None     # the translations of that photo
        self._changing_since = None
        self._busy = False
        self._peek_pending = False
        self._last_clean = 0.0       # when a photo without translations was last taken
        self._jobs = queue.Queue(maxsize=1)
        self._done.connect(self._finished)
        threading.Thread(target=self._work, name="lens-worker", daemon=True).start()

    # ---- control -------------------------------------------------------------
    @property
    def running(self):
        return self._timer.isActive()

    def set_interval(self, ms):
        self._timer.setInterval(ms)

    def start(self):
        self.restart()
        self._timer.start()
        QTimer.singleShot(0, self.tick)

    def stop(self):
        self._timer.stop()
        self.restart()

    def restart(self):
        """Forget what was read (new area, language or translator): everything is read again."""
        self.generation += 1
        self._previous = self._submitted = self._last_blocks = None
        self._changing_since = None
        if self._showing:
            self._showing = False
            self.stale.emit()

    def scale(self):
        """Photo pixels per logical pixel of the area (1.25 on a screen scaled to 125 %)."""
        return self.area[0].devicePixelRatio() if self.area else 1.0

    # ---- the Qt thread: photograph, compare, hand over ----------------------
    def grab(self):
        screen, rect = self.area
        return screen.grabWindow(0, rect.x(), rect.y(), rect.width(), rect.height()).toImage()

    def tick(self):
        if self.area is None or self.translator is None or self._peek_pending or self.paused():
            return
        rect = self.area[1]
        hidden = thumb_mask(self.covered(), rect.width(), rect.height())
        image = self.grab()
        if image.isNull():
            return
        now = time.monotonic()
        if hidden is None:
            self._last_clean = now
        thumb = thumbnail(image)
        moving = changed(thumb, self._previous, hidden)
        self._previous = thumb
        if not changed(thumb, self._submitted, hidden):
            self._changing_since = None
            if not self._showing and self._last_blocks is not None and not self._busy:
                self._showing = True  # back to what was translated (a hover or a menu went away)
                self.result.emit(self._last_blocks)
            elif hidden is not None and not self._busy and self.peek_due(now):
                self._peek()
            return
        self._mark_changed(now)
        if hidden is not None:
            return  # this photo shows translations: read the next one, taken without them
        if (moving and now - self._changing_since < MAX_WAIT) or self._busy:
            return
        self._busy = True
        self._submitted = thumb
        self._changing_since = None
        self._jobs.put((self.generation, image, self.target, self.ocr_language, self.translator,
                        self.trim_edges))

    def _mark_changed(self, now):
        if self._changing_since is None:
            self._changing_since = now
        if self._showing:
            self._showing = False
            self.stale.emit()

    def peek_due(self, now):
        return bool(self.peek_every) and now - self._last_clean >= self.peek_every

    def _peek(self):
        """Hide the translations for a moment and look whether the page under them changed."""
        self._peek_pending = True
        self.peeking(True)
        QTimer.singleShot(PEEK_MS, self._peeked)

    def _peeked(self):
        try:
            image = self.grab() if self.area else None
        finally:
            self.peeking(False)
            self._peek_pending = False
        self._last_clean = time.monotonic()
        if image is not None and not image.isNull() and changed(thumbnail(image), self._submitted):
            self._mark_changed(self._last_clean)

    def _finished(self, generation, blocks, error):
        self._busy = False
        if generation != self.generation or not self.running:
            return
        if error:
            self._submitted = None  # try again on the next tick
            self.status.emit(error)
            return
        self._last_blocks = blocks
        self._showing = True
        self.result.emit(blocks)

    # ---- the worker thread: read and translate -----------------------------
    def _work(self):
        reader, reader_language = None, None
        while True:
            generation, image, target, language, translator, trim_edges = self._jobs.get()
            try:
                if reader is None or language != reader_language:
                    reader, reader_language = lens_ocr.Reader(language), language
                started = time.monotonic()
                blocks = self.process(reader, translator, image, target, trim_edges)
                log.debug("Read and translated %d blocks in %.2f s", len(blocks), time.monotonic() - started)
                self._done.emit(generation, blocks, None)
            except Exception as e:
                log.exception("Lens could not read or translate the screen")
                self._done.emit(generation, [], str(e) or e.__class__.__name__)

    @staticmethod
    def process(reader, translator, image, target, trim_edges=False):
        lines = reader.read(image)
        blocks = [b for b in lens_ocr.group_blocks(lines)
                  if lens_ocr.worth_translating(b.text) and not lens_translate.already_in(b.text, target)
                  and not (trim_edges and cut_at_edge(b, image.width()))]
        translations = translator.translate_many([b.text for b in blocks], target)
        pixels = image_array(image) if blocks else None
        for block, translation in zip(blocks, translations):
            block.translation = translation
            block.background, block.foreground = colors_of(pixels, block.box)
        return [b for b in blocks if b.translation and b.translation.strip() != b.text.strip()]
