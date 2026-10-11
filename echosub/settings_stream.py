# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""The Stream tab: captions on a page OBS can show as a Browser Source."""
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)


def stream_url(port):
    return f"http://127.0.0.1:{int(port)}/"


class StreamTabMixin:
    """Settings for the stream captions, kept out of the main Settings file."""

    def _stream_tab(self, cfg):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        group = QGroupBox("Captions for a live stream (OBS)")
        form = QFormLayout(group)
        self.stream_enabled = QCheckBox("Offer the captions as a page for OBS's Browser Source")
        self.stream_enabled.setChecked(cfg.get("stream_enabled", False))
        form.addRow(self.stream_enabled)
        how = QLabel("In OBS: Sources → + → Browser, and paste the address below. The page is transparent, so the "
                     "captions sit on top of your stream. Only this PC can open it.")
        how.setWordWrap(True)
        how.setStyleSheet("color: gray;")
        form.addRow(how)

        self.stream_port = QSpinBox()
        self.stream_port.setRange(1024, 65535)
        self.stream_port.setMaximumWidth(120)
        self.stream_port.setValue(int(cfg.get("stream_port", 8790)))
        self.stream_address = QLineEdit(stream_url(self.stream_port.value()))
        self.stream_address.setReadOnly(True)
        copy = QPushButton("Copy")
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.stream_address.text()))
        open_it = QPushButton("Open")
        open_it.setToolTip("See the page in your browser (switch this on and save first)")
        open_it.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self.stream_address.text())))
        self.stream_port.valueChanged.connect(lambda port: self.stream_address.setText(stream_url(port)))
        address_row = QHBoxLayout()
        for item in (self.stream_address, copy, open_it):
            address_row.addWidget(item)
        form.addRow("Address:", address_row)
        form.addRow("Port:", self.stream_port)

        self.stream_lines = QSpinBox()
        self.stream_lines.setRange(1, 6)
        self.stream_lines.setSuffix(" captions")
        self.stream_lines.setValue(int(cfg.get("stream_lines", 2)))
        self.stream_font_size = QSpinBox()
        self.stream_font_size.setRange(12, 120)
        self.stream_font_size.setSuffix(" px")
        self.stream_font_size.setValue(int(cfg.get("stream_font_size", 42)))
        self.stream_hide_after = QSpinBox()
        self.stream_hide_after.setRange(2, 120)
        self.stream_hide_after.setSuffix(" s")
        self.stream_hide_after.setValue(int(cfg.get("stream_hide_after", 8)))
        look = QHBoxLayout()
        for title, item in (("Show", self.stream_lines), ("size", self.stream_font_size),
                            ("for", self.stream_hide_after)):
            look.addWidget(QLabel(title))
            look.addWidget(item)
        look.addStretch(1)
        form.addRow("Captions:", look)
        self.stream_show_original = QCheckBox("Show the original words above the translation")
        self.stream_show_original.setChecked(cfg.get("stream_show_original", True))
        form.addRow(self.stream_show_original)

        for field in (self.stream_port, self.stream_lines, self.stream_font_size, self.stream_hide_after,
                      self.stream_show_original):
            self.stream_enabled.toggled.connect(field.setEnabled)
            field.setEnabled(self.stream_enabled.isChecked())
        layout.addWidget(group)
        layout.addStretch(1)
        return widget

    def stream_values(self):
        return {"stream_enabled": self.stream_enabled.isChecked(), "stream_port": self.stream_port.value(),
                "stream_lines": self.stream_lines.value(), "stream_font_size": self.stream_font_size.value(),
                "stream_hide_after": self.stream_hide_after.value(),
                "stream_show_original": self.stream_show_original.isChecked()}
