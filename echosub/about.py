# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""About window: author, version, description, links and legal documents."""
import os
import sys

from PySide6.QtCore import QRectF, QSize, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from . import (
    APP_NAME, AUTHOR, AUTHOR_EMAIL, COPYRIGHT, DESCRIPTION, LICENSE_NAME, LINKS, REPOSITORY_URL, __version__, config,
)

AVATAR_NAMES = ("author.png", "author.jpg", "author.jpeg")
ACCENT = "#14B8A6"


def find_document(name):
    """Locate a document shipped with the app (project root from source, install folder when installed)."""
    candidates = [os.path.dirname(config.PACKAGE_DIR), os.path.dirname(sys.executable),
                  getattr(sys, "_MEIPASS", ""), os.path.join(os.path.dirname(sys.executable), "docs")]
    for folder in candidates:
        path = os.path.join(folder, name) if folder else ""
        if path and os.path.exists(path):
            return path
    return None


def avatar_pixmap(size):
    """Round author photo from assets/author.(png|jpg); falls back to initials."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
    clip = QPainterPath()
    clip.addEllipse(QRectF(0, 0, size, size))
    p.setClipPath(clip)
    photo = next((QPixmap(os.path.join(config.ASSETS_DIR, n)) for n in AVATAR_NAMES
                  if os.path.exists(os.path.join(config.ASSETS_DIR, n))), None)
    if photo is not None and not photo.isNull():
        scaled = photo.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        p.drawPixmap((size - scaled.width()) // 2, (size - scaled.height()) // 2, scaled)
    else:
        p.fillRect(0, 0, size, size, QColor("#1F2937"))
        p.setPen(QColor(ACCENT))
        font = QFont("Segoe UI", int(size * 0.32), QFont.Bold)
        p.setFont(font)
        initials = "".join(part[0] for part in AUTHOR.replace("-", " ").split()[:2]).upper()
        p.drawText(pm.rect(), Qt.AlignCenter, initials)
    p.setClipping(False)
    p.setPen(QColor(255, 255, 255, 60))
    p.drawEllipse(QRectF(0.5, 0.5, size - 1, size - 1))
    p.end()
    return pm


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"About {APP_NAME}")
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setWindowIcon(QIcon(os.path.join(config.ASSETS_DIR, "echosub.ico")))
        self.setMinimumWidth(460)
        self.setStyleSheet(f"""
            QDialog {{ background: #111615; }}
            QLabel {{ color: #E5E7EB; }}
            QLabel#muted {{ color: #9CA3AF; }}
            QPushButton#link {{ background: transparent; color: #E5E7EB; border: 1px solid #2B3432;
                               border-radius: 8px; padding: 9px 16px; font-weight: 600; }}
            QPushButton#link:hover {{ border-color: {ACCENT}; color: white; }}
            QPushButton#small {{ background: transparent; color: #9CA3AF; border: none; padding: 2px 6px; }}
            QPushButton#small:hover {{ color: {ACCENT}; }}
            QPushButton#close {{ background: {ACCENT}; color: #04211D; border: none; border-radius: 8px;
                                padding: 11px; font-weight: 700; font-size: 11pt; }}
            QPushButton#close:hover {{ background: #2DD4BF; }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(36, 26, 36, 26)
        root.setSpacing(10)

        title = QLabel("About")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 17pt; font-weight: 700;")
        root.addWidget(title)

        images = QHBoxLayout()
        images.setSpacing(14)
        images.addStretch(1)
        avatar = QLabel()
        avatar.setPixmap(avatar_pixmap(84))
        avatar.setToolTip(AUTHOR)
        icon = QLabel()
        icon.setPixmap(QIcon(os.path.join(config.ASSETS_DIR, "echosub.ico")).pixmap(QSize(64, 64)))
        images.addWidget(avatar)
        images.addWidget(icon)
        images.addStretch(1)
        root.addLayout(images)

        name = QLabel(f"<b style='font-size:14pt'>{APP_NAME}</b> "
                      f"<span style='color:#9CA3AF; font-size:10pt'>v{__version__}</span>")
        name.setAlignment(Qt.AlignCenter)
        root.addWidget(name)

        desc = QLabel(DESCRIPTION)
        desc.setObjectName("muted")
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        root.addWidget(desc)

        by = QLabel(f"Made by <b>{AUTHOR}</b><br><span style='color:#9CA3AF'>{AUTHOR_EMAIL}</span>")
        by.setAlignment(Qt.AlignCenter)
        by.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(by)

        links = QHBoxLayout()
        links.setSpacing(10)
        links.addStretch(1)
        for label, url in LINKS.items():
            links.addWidget(self._link_button(label, url, "link"))
        links.addWidget(self._link_button("Email", f"mailto:{AUTHOR_EMAIL}?subject={APP_NAME}", "link"))
        links.addStretch(1)
        root.addSpacing(4)
        root.addLayout(links)

        docs = QHBoxLayout()
        docs.addStretch(1)
        for i, (label, target) in enumerate((("License", "LICENSE"), ("Privacy", "PRIVACY.md"),
                                              ("Third-party notices", "THIRD_PARTY_NOTICES.md"),
                                              ("Source code", REPOSITORY_URL))):
            if i:
                dot = QLabel("·")
                dot.setObjectName("muted")
                docs.addWidget(dot)
            docs.addWidget(self._doc_button(label, target))
        docs.addStretch(1)
        root.addLayout(docs)

        legal = QLabel(f"{COPYRIGHT}<br>Licensed under the {LICENSE_NAME}.<br>"
                       "This program comes with ABSOLUTELY NO WARRANTY.")
        legal.setObjectName("muted")
        legal.setAlignment(Qt.AlignCenter)
        legal.setStyleSheet("font-size: 8.5pt;")
        root.addWidget(legal)

        root.addSpacing(6)
        close = QPushButton("Close")
        close.setObjectName("close")
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(self.accept)
        root.addWidget(close)

    def _link_button(self, label, url, style):
        b = QPushButton(label)
        b.setObjectName(style)
        b.setCursor(Qt.PointingHandCursor)
        b.setToolTip(url)
        b.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(url)))
        return b

    def _doc_button(self, label, target):
        b = QPushButton(label)
        b.setObjectName("small")
        b.setCursor(Qt.PointingHandCursor)

        def open_target():
            if target.startswith("http"):
                QDesktopServices.openUrl(QUrl(target))
                return
            path = find_document(target)
            if path:
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            else:
                QDesktopServices.openUrl(QUrl(f"{REPOSITORY_URL}/blob/main/{target}"))

        b.clicked.connect(open_target)
        return b
