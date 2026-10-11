# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""EchoSub Lens: drag a rectangle on any screen to choose the area to translate."""
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

HINT = "Drag over the area to translate  ·  Esc to cancel"
MIN_SIZE = 24


class _ScreenShade(QWidget):
    """Dims one screen; the dragged rectangle stays clear."""

    def __init__(self, picker, screen):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.picker = picker
        self.screen_ = screen
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)
        self.setGeometry(screen.geometry())
        self.start = self.end = None

    def selection(self):
        if self.start is None:
            return QRect()
        return QRect(self.start, self.end).normalized()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(0, 0, 0, 110))
        chosen = self.selection()
        if not chosen.isEmpty():
            p.setCompositionMode(QPainter.CompositionMode_Clear)
            p.fillRect(chosen, Qt.transparent)
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)
            p.setPen(QPen(QColor("#4FC3F7"), 2))
            p.drawRect(chosen.adjusted(-1, -1, 0, 0))
            p.setPen(QColor("white"))
            p.drawText(chosen.bottomLeft() + QPoint(4, 18), f"{chosen.width()} × {chosen.height()}")
        font = QFont("Segoe UI")
        font.setPixelSize(20)
        p.setFont(font)
        p.setPen(QColor("white"))
        p.drawText(self.rect().adjusted(0, 40, 0, 0), Qt.AlignHCenter | Qt.AlignTop, HINT)

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.picker.finish(None)
            return
        self.start = self.end = event.position().toPoint()
        self.update()

    def mouseMoveEvent(self, event):
        if self.start is not None:
            self.end = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if self.start is None or event.button() != Qt.LeftButton:
            return
        chosen = self.selection()
        if chosen.width() < MIN_SIZE or chosen.height() < MIN_SIZE:
            self.start = self.end = None
            self.update()
            return
        self.picker.finish((self.screen_, chosen))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.picker.finish(None)


class RegionPicker:
    """`RegionPicker(on_done).start()`; on_done receives (QScreen, QRect relative to it) or None."""

    def __init__(self, on_done):
        self.on_done = on_done
        self.shades = []

    def start(self):
        self.shades = [_ScreenShade(self, screen) for screen in QGuiApplication.screens()]
        for shade in self.shades:
            shade.show()
        here = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        for shade in self.shades:
            if shade.screen_ is here:
                shade.activateWindow()
                shade.setFocus()

    def finish(self, result):
        shades, self.shades = self.shades, []
        for shade in shades:
            shade.close()
            shade.deleteLater()
        self.on_done(result)
