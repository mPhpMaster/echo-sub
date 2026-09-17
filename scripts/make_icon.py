# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Draws the EchoSub icon and writes echosub/assets/echosub.ico (+ PNGs). Run by build.ps1."""
import os
import struct
import sys

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath, QPen

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "echosub", "assets")
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def draw(size):
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    s = size / 256.0

    # background: rounded square, blue -> teal
    grad = QLinearGradient(QPointF(0, 0), QPointF(size, size))
    grad.setColorAt(0.0, QColor("#2563EB"))
    grad.setColorAt(1.0, QColor("#14B8A6"))
    p.setPen(Qt.NoPen)
    p.setBrush(grad)
    p.drawRoundedRect(QRectF(8 * s, 8 * s, 240 * s, 240 * s), 56 * s, 56 * s)

    # speech bubble with tail
    bubble = QPainterPath()
    bubble.addRoundedRect(QRectF(30 * s, 62 * s, 150 * s, 112 * s), 28 * s, 28 * s)
    tail = QPainterPath()
    tail.moveTo(62 * s, 166 * s)
    tail.lineTo(48 * s, 204 * s)
    tail.lineTo(96 * s, 170 * s)
    tail.closeSubpath()
    p.setBrush(QColor("#FFFFFF"))
    p.drawPath(bubble.united(tail))

    # caption lines inside the bubble
    p.setBrush(QColor("#1E3A8A"))
    p.drawRoundedRect(QRectF(54 * s, 94 * s, 102 * s, 17 * s), 8.5 * s, 8.5 * s)
    p.setBrush(QColor("#0F766E"))
    p.drawRoundedRect(QRectF(68 * s, 125 * s, 74 * s, 17 * s), 8.5 * s, 8.5 * s)

    # sound waves ("echo") coming off the bubble's right side
    pen = QPen(QColor(255, 255, 255, 235), max(1.2, 13 * s), Qt.SolidLine, Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    cx, cy = 176, 118
    for r in ((30, 52) if size >= 24 else (40,)):
        p.drawArc(QRectF((cx - r) * s, (cy - r) * s, 2 * r * s, 2 * r * s), -42 * 16, 84 * 16)
    p.end()
    return img


def png_bytes(img):
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(data)


def write_ico(path, images):
    """ICO file whose entries are PNGs (supported since Windows Vista)."""
    header = struct.pack("<HHH", 0, 1, len(images))
    entries, blobs = b"", b""
    offset = 6 + 16 * len(images)
    for size, img in images:
        blob = png_bytes(img)
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(blob), offset)
        blobs += blob
        offset += len(blob)
    with open(path, "wb") as f:
        f.write(header + entries + blobs)


def main():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)  # noqa: F841 (needed for fonts/painting)
    os.makedirs(ASSETS, exist_ok=True)
    images = [(size, draw(size)) for size in SIZES]
    write_ico(os.path.join(ASSETS, "echosub.ico"), images)
    for size, img in images:
        if size in (64, 256):
            img.save(os.path.join(ASSETS, f"echosub-{size}.png"), "PNG")
    print("icon written to", ASSETS)


if __name__ == "__main__":
    main()
