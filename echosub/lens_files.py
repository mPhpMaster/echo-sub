# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""EchoSub Lens: translating a file — a picture, a PDF, a Word document or a text file.

Pictures and PDF pages are read like the screen (Windows OCR) and the translations are drawn over
them, in the user's Lens look. Word documents and text files keep their own layout: only the words
change, so headings, tables, bold and colours stay where they were.
"""
import html
import os
import re
import zipfile
from xml.sax.saxutils import escape

from . import lens_ocr

IMAGES = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp")
PDF = (".pdf",)
WORD = (".docx",)
TEXT = (".txt", ".md", ".srt", ".csv", ".log")
OPEN_FILTER = ("Files Lens can translate (" + " ".join("*" + e for e in IMAGES + PDF + WORD + TEXT) + ");;"
               "Pictures (" + " ".join("*" + e for e in IMAGES) + ");;PDF documents (*.pdf);;"
               "Word documents (*.docx);;Text files (" + " ".join("*" + e for e in TEXT) + ")")
PDF_SCALE = 2.0          # PDF points -> pixels: about 144 dpi, sharp enough for OCR
WORD_PARTS = re.compile(r"word/(document|header\d*|footer\d*|footnotes|endnotes)\.xml$")
_WORD_TOKENS = re.compile(r"<w:p[ >]|</w:p>|<w:t(?: [^>]*)?>(.*?)</w:t>", re.S)


def kind(path):
    """'image', 'pdf', 'word', 'text', or None for a file Lens cannot translate (.doc: save it as .docx)."""
    ext = os.path.splitext(path)[1].lower()
    for name, exts in (("image", IMAGES), ("pdf", PDF), ("word", WORD), ("text", TEXT)):
        if ext in exts:
            return name
    return None


def output_name(path, target):
    """report.pdf -> report.ar.pdf; a picture is saved as PNG so the translation stays sharp."""
    stem, ext = os.path.splitext(path)
    if kind(path) == "image":
        ext = ".png"
    return f"{stem}.{target}{ext}"


# ---- pictures and PDF pages -------------------------------------------------------
def page_count(path):
    if kind(path) != "pdf":
        return 1
    document = _open_pdf(path)
    try:
        return document.pageCount()
    finally:
        document.close()


def pages(path):
    """The file's pages as QImages, one at a time (a PDF is drawn page by page)."""
    from PySide6.QtGui import QImage

    if kind(path) == "image":
        image = QImage(path)
        if image.isNull():
            raise ValueError("This picture could not be opened")
        yield image
        return
    from PySide6.QtCore import QSize

    document = _open_pdf(path)
    try:
        for index in range(document.pageCount()):
            size = document.pagePointSize(index)
            page = document.render(index, QSize(round(size.width() * PDF_SCALE), round(size.height() * PDF_SCALE)))
            yield _on_white(page)
    finally:
        document.close()


def _on_white(image):
    """A PDF page is drawn on a transparent background: put it on paper, as it is printed."""
    from PySide6.QtGui import QColor, QImage, QPainter

    paper = QImage(image.size(), QImage.Format_RGB32)
    paper.fill(QColor("white"))
    painter = QPainter(paper)
    painter.drawImage(0, 0, image)
    painter.end()
    return paper


def _open_pdf(path):
    from PySide6.QtPdf import QPdfDocument

    document = QPdfDocument()
    error = document.load(path)
    if error != QPdfDocument.Error.None_:
        raise ValueError("This PDF could not be opened" +
                         (" (it is protected by a password)" if error == QPdfDocument.Error.IncorrectPassword else ""))
    return document


def translate_page(reader, translator, image, target):
    """Translated blocks of one page (lens_ocr.Block, boxes in the page's pixels)."""
    from .lens_scanner import LensScanner

    return LensScanner.process(reader, translator, image, target)


def render(image, blocks, target, style):
    """The page with its translations drawn over the original words, in the Lens look. Qt thread only."""
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QPainter

    from .lens_overlay import LensOverlay

    overlay = LensOverlay(style)
    overlay.setGeometry(QRect(0, 0, image.width(), image.height()))
    overlay.show_blocks(blocks, target)
    result = image.convertToFormat(image.Format.Format_ARGB32)
    painter = QPainter(result)
    for label in overlay.labels:
        painter.drawPixmap(label.pos(), label.grab())
    painter.end()
    overlay.deleteLater()
    return result


def save_pages(images, path, page_sizes=None):
    """One picture as PNG/JPG, or every page into a PDF (`page_sizes`: each page's size in points)."""
    if not path.lower().endswith(".pdf"):
        if not images[0].save(path):
            raise OSError(f"Could not save {path}")
        return
    from PySide6.QtCore import QMarginsF, QRectF, QSizeF
    from PySide6.QtGui import QPageLayout, QPageSize, QPainter, QPdfWriter

    writer = QPdfWriter(path)
    writer.setResolution(72)
    painter = None
    for index, image in enumerate(images):
        points = page_sizes[index] if page_sizes else QSizeF(image.width() / PDF_SCALE, image.height() / PDF_SCALE)
        layout = QPageLayout(QPageSize(points, QPageSize.Point), QPageLayout.Portrait, QMarginsF())
        writer.setPageLayout(layout)
        if painter is None:
            painter = QPainter(writer)
        else:
            writer.newPage()
        painter.drawImage(QRectF(0, 0, points.width(), points.height()), image)
    if painter is not None:
        painter.end()


# ---- Word documents --------------------------------------------------------------
def _paragraphs(xml):
    """[(text, [(start, end) of each <w:t> element])] for every paragraph, nested ones (text boxes) too."""
    found, stack = [], []
    for match in _WORD_TOKENS.finditer(xml):
        token = match.group(0)
        if token.startswith("<w:p"):
            stack.append([[], []])
        elif token == "</w:p>":
            if stack:
                texts, spans = stack.pop()
                if spans:
                    found.append(("".join(texts), spans))
        elif stack:
            stack[-1][0].append(html.unescape(match.group(1)))
            stack[-1][1].append(match.span())
    return found


def word_texts(path):
    """Every paragraph worth translating in a .docx: body, tables, text boxes, headers, footers, notes."""
    texts = []
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if WORD_PARTS.match(name):
                xml = archive.read(name).decode("utf-8")
                texts += [t for t, _ in _paragraphs(xml) if lens_ocr.worth_translating(t)]
    return list(dict.fromkeys(texts))


def _translated_xml(xml, translations):
    edits = []
    for text, spans in _paragraphs(xml):
        new = translations.get(text)
        if not new:
            continue
        edits.append((spans[0], f'<w:t xml:space="preserve">{escape(new)}</w:t>'))
        edits += [(span, "<w:t></w:t>") for span in spans[1:]]  # the words now sit in the first run
    for (start, end), replacement in sorted(edits, reverse=True):
        xml = xml[:start] + replacement + xml[end:]
    return xml


def write_word(path, out_path, translations):
    """A copy of the .docx with each paragraph's words replaced by `translations[text]`; formatting kept."""
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if WORD_PARTS.match(item.filename):
                data = _translated_xml(data.decode("utf-8"), translations).encode("utf-8")
            target.writestr(item, data)


# ---- text files ------------------------------------------------------------------
def read_text(path):
    with open(path, "rb") as f:
        raw = f.read()
    for encoding in ("utf-8-sig", "utf-16", "cp1256", "cp1252"):
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        if encoding != "utf-16" or raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
            return text
    return raw.decode("utf-8", errors="replace")


def text_lines(text):
    """The lines worth translating (subtitle numbers and times, empty lines and numbers stay as they are)."""
    return list(dict.fromkeys(line.strip() for line in text.splitlines() if lens_ocr.worth_translating(line)))


def translated_text(text, translations):
    out = []
    for line in text.splitlines():
        new = translations.get(line.strip())
        out.append(line.replace(line.strip(), new) if new else line)
    return "\n".join(out) + ("\n" if text.endswith(("\n", "\r")) else "")


def write_text(out_path, text):
    with open(out_path, "w", encoding="utf-8-sig", newline="\n") as f:
        f.write(text)
