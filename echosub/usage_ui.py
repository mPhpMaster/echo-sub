# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Showing what EchoSub costs the PC: a small window with bars, a line in the Settings window, and
a line in the caption box. The tray icon's tooltip is kept in main.py with the rest of the tray.

Each display reads `usage.shared().latest` on a timer of its own, so nothing is ever sent to a
window that has already closed.
"""
import psutil
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QCheckBox, QGridLayout, QLabel, QProgressBar, QVBoxLayout, QWidget

from . import APP_NAME, gpu, usage

REFRESH_MS = 1000
DISK_SCALE = 50 * 1024 * 1024   # a full disk bar: 50 MB/s, far more than EchoSub ever needs


def _percent(part, whole):
    return int(round(100 * part / whole)) if part is not None and whole else 0


class UsageWindow(QWidget):
    """Bars for the processor, memory, graphics card, its memory and the disk."""
    closed = Signal()
    on_top_changed = Signal(bool)

    def __init__(self, on_top=True, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} — usage")
        self.setWindowFlag(Qt.Tool, True)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, bool(on_top))
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.total_ram = psutil.virtual_memory().total
        self.total_vram = gpu.memory_size()
        layout = QVBoxLayout(self)
        grid = QGridLayout()
        self.bars, self.values = {}, {}
        for row, (key, title) in enumerate((("cpu", "Processor"), ("ram", "Memory"), ("gpu", "Graphics card"),
                                            ("vram", "Graphics memory"), ("disk", "Disk"))):
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setTextVisible(False)
            bar.setFixedHeight(10)
            value = QLabel("–")
            value.setMinimumWidth(90)
            value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            grid.addWidget(QLabel(title), row, 0)
            grid.addWidget(bar, row, 1)
            grid.addWidget(value, row, 2)
            self.bars[key], self.values[key] = bar, value
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        note = QLabel("EchoSub and the programs it started, as Task Manager counts them.")
        note.setStyleSheet("color: gray;")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.on_top = QCheckBox("Keep on top of other windows")
        self.on_top.setChecked(bool(on_top))
        self.on_top.toggled.connect(self._set_on_top)
        layout.addWidget(self.on_top)
        self.resize(360, self.sizeHint().height())
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(REFRESH_MS)
        self.refresh()

    def _set_on_top(self, on):
        self.setWindowFlag(Qt.WindowStaysOnTopHint, on)
        self.show()  # changing a window flag hides the window until it is shown again
        self.on_top_changed.emit(on)

    def show_sample(self, sample):
        if sample is None:
            return
        self._set("cpu", sample.cpu, f"{sample.cpu:.0f}%")
        self._set("ram", _percent(sample.ram, self.total_ram), usage.human_bytes(sample.ram))
        self._set("gpu", sample.gpu, "–" if sample.gpu is None else f"{sample.gpu:.0f}%")
        vram_text = usage.human_bytes(sample.vram)
        if sample.vram is not None and self.total_vram:
            vram_text += f" of {usage.human_bytes(self.total_vram)}"
        self._set("vram", _percent(sample.vram, self.total_vram), vram_text)
        self._set("disk", _percent(min(sample.disk, DISK_SCALE), DISK_SCALE), f"{usage.human_bytes(sample.disk)}/s")

    def _set(self, key, percent, text):
        self.bars[key].setValue(int(round(percent or 0)))
        self.values[key].setText(text)

    def refresh(self):
        self.show_sample(usage.shared().latest)

    def closeEvent(self, event):
        self._timer.stop()
        self.closed.emit()
        super().closeEvent(event)


class UsageStrip(QLabel):
    """One line of figures, for the bottom of the Settings window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("color: gray;")
        self.setToolTip("What EchoSub is using right now, with the programs it started")
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(REFRESH_MS)
        self.refresh()

    def refresh(self):
        text = usage.summary(usage.shared().latest)
        self.setText(f"{APP_NAME} is using: {text}" if text else f"{APP_NAME} is measuring its usage…")


def caption_line(overlay):
    """A small line at the top of the caption box for the figures; hidden until it has text."""
    label = QLabel()
    label.setStyleSheet("color: #9A9A9A; font-size: 9pt;")
    label.setAttribute(Qt.WA_TransparentForMouseEvents)
    label.hide()
    overlay.content_layout.insertWidget(0, label)
    return label
