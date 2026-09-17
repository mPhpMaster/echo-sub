# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Progress window for model downloads, with Cancel / Retry."""
import os

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout

from . import APP_NAME, config
from .downloads import human_size


def format_eta(seconds):
    if seconds is None:
        return "estimating time left…"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} s left"
    if seconds < 3600:
        return f"{seconds // 60} min {seconds % 60:02d} s left"
    return f"{seconds // 3600} h {(seconds % 3600) // 60:02d} min left"


def summary(event):
    """'812.0 MB of 1.6 GB · 12.3 MB/s · 1 min 05 s left'"""
    parts = [f"{human_size(event['done'])} of {human_size(event['total'])}" if event["total"]
             else human_size(event["done"])]
    if event["state"] == "progress" and event["speed"] > 1:
        parts.append(f"{human_size(event['speed'])}/s")
        parts.append(format_eta(event["eta"]))
    return " · ".join(parts)


def percent(event):
    return int(event["done"] * 100 / event["total"]) if event["total"] else 0


class DownloadDialog(QDialog):
    cancel_requested = Signal()
    retry_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} — Downloading AI models")
        self.setWindowIcon(QIcon(os.path.join(config.ASSETS_DIR, "echosub.ico")))
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(480)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(8)
        self.title = QLabel()
        self.title.setStyleSheet("font-size: 12pt; font-weight: 600;")
        root.addWidget(self.title)
        self.note = QLabel("This is needed only once. EchoSub works offline afterwards.")
        self.note.setStyleSheet("color: gray;")
        self.note.setWordWrap(True)
        root.addWidget(self.note)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(True)
        self.bar.setMinimumHeight(22)
        root.addWidget(self.bar)
        self.detail = QLabel()
        self.detail.setWordWrap(True)
        root.addWidget(self.detail)
        self.file = QLabel()
        self.file.setStyleSheet("color: gray; font-size: 8.5pt;")
        root.addWidget(self.file)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.retry = QPushButton("Retry")
        self.retry.clicked.connect(self._retry)
        self.cancel = QPushButton("Cancel")
        self.cancel.clicked.connect(self._cancel)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.hide)
        for b in (self.retry, self.cancel, self.close_button):
            buttons.addWidget(b)
        root.addLayout(buttons)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)
        self._set_mode("downloading")

    def _set_mode(self, mode):
        """downloading | stopped (canceled or failed)"""
        downloading = mode == "downloading"
        self.cancel.setVisible(downloading)
        self.cancel.setEnabled(True)
        self.cancel.setText("Cancel")
        self.retry.setVisible(not downloading)
        self.close_button.setVisible(not downloading)

    def update_event(self, event):
        state = event["state"]
        self.title.setText(event["title"])
        if event["total"]:
            self.bar.setRange(0, 1000)
            self.bar.setValue(int(event["done"] * 1000 / event["total"]))
            self.bar.setFormat(f"{percent(event)} %")
        else:
            self.bar.setRange(0, 0)  # unknown size: busy indicator
        self.detail.setText(summary(event))
        self.file.setText(event["file"] or "")
        if state in ("start", "progress"):
            self._hide_timer.stop()
            self._set_mode("downloading")
            self.note.setText("This is needed only once. EchoSub works offline afterwards.")
            if not self.isVisible():
                self.show()
        elif state == "finished":
            self.bar.setValue(1000)
            self.bar.setFormat("100 %")
            self.detail.setText(f"Done — {human_size(event['total'])}")
            self.file.setText("")
            self._hide_timer.start(1200)  # the next model's download may start right away
        elif state == "canceled":
            self._set_mode("stopped")
            self.note.setText("Download canceled. What was already downloaded is kept, so Retry continues where "
                              "it stopped.")
            self.detail.setText(f"Stopped at {summary(event)}")
            self.show()
        elif state == "failed":
            self._set_mode("stopped")
            self.note.setText("The download failed. Check your internet connection, then Retry — it continues "
                              "where it stopped.")
            self.detail.setText(event.get("error") or "Unknown error")
            self.show()

    def _cancel(self):
        self.cancel.setEnabled(False)
        self.cancel.setText("Canceling…")
        self.cancel_requested.emit()

    def _retry(self):
        self._set_mode("downloading")
        self.detail.setText("Starting…")
        self.retry_requested.emit()

    def closeEvent(self, event):
        # Closing the window while downloading only hides it; the download continues (the tray shows progress)
        event.ignore()
        self.hide()
