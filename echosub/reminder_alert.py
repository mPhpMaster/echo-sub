# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""The window a reminder opens when its time comes.

A tray notification was the wrong shape for this: it appears in the corner, lasts a few seconds and
is gone, which is exactly what someone busy enough to need a reminder will miss. This takes the
middle of the screen, sounds, stays until it is answered, and offers to come back in five minutes.
"""
import logging

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

log = logging.getLogger(__name__)

SNOOZE_MINUTES = 5
BACKGROUND = QColor(24, 24, 30, 248)
BORDER = QColor(255, 196, 0)
PULSE_MS = 650


def chime():
    """Windows' own alert sound. Silence is never worth a crash, so failure is ignored."""
    try:
        import winsound

        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except Exception as e:
        log.info("Could not play the reminder sound: %s", e)


class ReminderAlert(QWidget):
    """"⏰ take the bread out" in the middle of the screen, until you answer it."""

    dismissed = Signal()
    snoozed = Signal(int)

    def __init__(self, what, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("Reminder")
        self._bright = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 22)
        layout.setSpacing(14)
        heading = QLabel("⏰  Reminder")
        heading.setStyleSheet("color: #FFC400;")
        font = QFont(heading.font())
        font.setPointSizeF(font.pointSizeF() * 1.3)
        font.setBold(True)
        heading.setFont(font)
        layout.addWidget(heading)

        self.message = QLabel(str(what) or "Reminder")
        self.message.setWordWrap(True)
        self.message.setStyleSheet("color: white;")
        big = QFont(self.message.font())
        big.setPointSizeF(big.pointSizeF() * 2.0)
        big.setBold(True)
        self.message.setFont(big)
        self.message.setMinimumWidth(420)
        layout.addWidget(self.message)

        buttons = QHBoxLayout()
        snooze = QPushButton(f"Remind me again in {SNOOZE_MINUTES} minutes")
        snooze.clicked.connect(self._snooze)
        done = QPushButton("Done")
        done.setDefault(True)
        done.clicked.connect(self._dismiss)
        buttons.addWidget(snooze)
        buttons.addStretch(1)
        buttons.addWidget(done)
        layout.addLayout(buttons)

        self._pulse = QTimer(self)
        self._pulse.timeout.connect(self._flash)
        self._pulse.start(PULSE_MS)

    def show_on_screen(self):
        """Put it in the middle of the screen, in front, and make a sound."""
        self.adjustSize()
        screen = QApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            self.move(area.center().x() - self.width() // 2, area.center().y() - self.height() // 2)
        self.show()
        self.raise_()
        self.activateWindow()
        chime()
        return self

    def _flash(self):
        self._bright = not self._bright
        self.update()

    def _snooze(self):
        self._pulse.stop()
        self.snoozed.emit(SNOOZE_MINUTES)
        self.close()

    def _dismiss(self):
        self._pulse.stop()
        self.dismissed.emit()
        self.close()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Escape, Qt.Key_Return, Qt.Key_Enter):
            self._dismiss()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        box = self.rect().adjusted(2, 2, -2, -2)
        path = QPainterPath()
        path.addRoundedRect(box, 14, 14)
        p.fillPath(path, BACKGROUND)
        edge = QColor(BORDER)
        edge.setAlpha(255 if self._bright else 90)  # a slow pulse, to catch the eye
        p.setPen(edge)
        p.drawPath(path)
