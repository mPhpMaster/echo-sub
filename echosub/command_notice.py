# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""The short pause between hearing a command and carrying it out.

EchoSub hears everything the PC plays and, from your own microphone, it no longer waits for the
wake word. So before anything happens, what was understood is written on screen with a countdown,
and one click stops it. Nothing runs until that countdown ends.

The notice is its own small window rather than part of the caption box, because the caption box can
be set to let clicks pass straight through it, and a cancel button you cannot click is no use.
"""
import time

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QWidget

BACKGROUND = QColor(20, 20, 24, 235)
BORDER = QColor(255, 196, 0, 220)
TEXT = QColor(255, 255, 255)
HINT = QColor(255, 196, 0)
MARGIN, PADDING, RADIUS = 18, 14, 10
TICK_MS = 80


class CommandNotice(QWidget):
    """"<command> — running in 2.4 s. Click to cancel." Clicking anywhere on it cancels."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Click to cancel this command")
        self._label = ""
        self._ends_at = 0.0
        self._seconds = 0.0
        self._on_run = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.hide()

    # ---- what it is showing -------------------------------------------------
    def start(self, label, seconds, on_run, now=None):
        """Announce `label`, then call `on_run()` after `seconds` unless it is cancelled first."""
        now = time.monotonic() if now is None else now
        self._label = str(label)
        self._seconds = max(0.1, float(seconds))
        self._ends_at = now + self._seconds
        self._on_run = on_run
        self._resize_to_text()
        self._place()
        self.show()
        self.raise_()
        self._timer.start(TICK_MS)

    def cancel(self):
        """Stop the pending command. Safe to call when nothing is pending."""
        pending = self._on_run is not None
        self._timer.stop()
        self._on_run = None
        self.hide()
        return pending

    def remaining(self, now=None):
        now = time.monotonic() if now is None else now
        return max(0.0, self._ends_at - now)

    def pending(self):
        return self._on_run is not None

    def fire_now(self):
        """Run the pending command at once; used by the tests and when the countdown ends."""
        run = self._on_run
        self._timer.stop()
        self._on_run = None
        self.hide()
        if run is not None:
            run()
        return run is not None

    # ---- appearance ---------------------------------------------------------
    def _tick(self):
        if self._on_run is None:
            self._timer.stop()
            return
        if self.remaining() <= 0:
            self.fire_now()
        else:
            self.update()

    def _font(self):
        font = QFont(self.font())
        font.setPointSizeF(max(9.0, font.pointSizeF() * 1.05))
        font.setBold(True)
        return font

    def _text(self):
        return f"{self._label} — in {self.remaining():.1f} s"

    def _resize_to_text(self):
        from PySide6.QtGui import QFontMetricsF

        fm = QFontMetricsF(self._font())
        width = max(fm.horizontalAdvance(f"{self._label} — in 0.0 s"), fm.horizontalAdvance(self.HINT_TEXT))
        self.resize(round(width + PADDING * 2), round(fm.height() * 2 + PADDING * 2))

    HINT_TEXT = "Click to cancel"

    def _place(self):
        screen = QApplication.primaryScreen()
        window = self.window().windowHandle()
        if window is not None and window.screen() is not None:
            screen = window.screen()
        area = screen.availableGeometry()
        self.move(area.center().x() - self.width() // 2, area.top() + MARGIN)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.cancel()
        super().mousePressEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        box = self.rect().adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(box, RADIUS, RADIUS)
        p.fillPath(path, BACKGROUND)
        share = 0.0 if self._seconds <= 0 else self.remaining() / self._seconds
        p.setPen(QPen(BORDER, 2))
        p.drawPath(path)
        if share > 0:  # a bar that shrinks as the moment to act runs out
            p.fillRect(box.left() + 2, box.bottom() - 3, round((box.width() - 4) * share), 3, BORDER)
        p.setFont(self._font())
        from PySide6.QtGui import QFontMetricsF

        fm = QFontMetricsF(self._font())
        p.setPen(TEXT)
        p.drawText(PADDING, round(PADDING + fm.ascent()), self._text())
        p.setPen(HINT)
        p.drawText(PADDING, round(PADDING + fm.height() + fm.ascent()), self.HINT_TEXT)
