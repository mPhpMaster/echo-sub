# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""EchoSub Lens: the window that shows a translated file, page by page, and saves a translated copy."""
import logging
import os
import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QPushButton,
                               QScrollArea, QSplitter, QVBoxLayout, QWidget)

from . import languages, lens_files, lens_ocr

log = logging.getLogger(__name__)


class _Signals(QObject):
    page = Signal(int, object, object)      # index, original QImage, translated blocks
    texts = Signal(object)                  # {original: translation} of a Word or text file
    progress = Signal(str)
    failed = Signal(str)
    done = Signal()


class FileWindow(QWidget):
    """Translates `path` in a thread of its own; pages appear as they are done."""

    def __init__(self, path, target, translator, ocr_language, style, open_another=None):
        super().__init__(None, Qt.Window)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.path, self.target, self.style = path, target, style
        self.kind = lens_files.kind(path)
        self._open_another = open_another
        self.originals, self.blocks, self.rendered = {}, {}, {}
        self.translations = None
        self.finished = False
        self._cancel = threading.Event()
        self.setWindowTitle(f"{os.path.basename(path)} → {languages.name(target)} — EchoSub Lens")
        self.resize(1100, 780)
        self._build()
        self.signals = _Signals()
        self.signals.page.connect(self._page_done)
        self.signals.texts.connect(self._texts_done)
        self.signals.progress.connect(self.status.setText)
        self.signals.failed.connect(self._failed)
        self.signals.done.connect(self._done)
        threading.Thread(target=self._work, args=(translator, ocr_language), name="lens-file", daemon=True).start()

    # ---- layout --------------------------------------------------------------
    def _build(self):
        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.status = QLabel("Starting…")
        bar.addWidget(self.status, 1)
        self.original_button = QPushButton("Show the original")
        self.original_button.setCheckable(True)
        self.original_button.toggled.connect(self._show_pages)
        self.copy_button = QPushButton("Copy all translated text")
        self.copy_button.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.text_view.toPlainText()))
        self.save_button = QPushButton("Save translated copy…")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save)
        another = QPushButton("Translate another file…")
        another.clicked.connect(lambda: self._open_another and self._open_another())
        for widget in (self.original_button, self.copy_button, self.save_button, another):
            bar.addWidget(widget)
        layout.addLayout(bar)

        splitter = QSplitter(Qt.Horizontal)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        holder = QWidget()
        self.page_box = QVBoxLayout(holder)
        self.page_box.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self.scroll.setWidget(holder)
        self.original_text = QPlainTextEdit()
        self.original_text.setReadOnly(True)
        self.text_view = QPlainTextEdit()
        self.text_view.setReadOnly(True)
        self.text_view.setPlaceholderText("The translated text appears here, ready to select and copy.")
        if self.target in languages.RTL:
            self.text_view.setLayoutDirection(Qt.RightToLeft)
        pictures = self.kind in ("image", "pdf")
        splitter.addWidget(self.scroll if pictures else self.original_text)
        splitter.addWidget(self.text_view)
        splitter.setSizes([700, 400] if pictures else [550, 550])
        self.original_button.setVisible(pictures)
        layout.addWidget(splitter, 1)
        self.page_labels = []

    # ---- the worker thread -----------------------------------------------------
    def _work(self, translator, ocr_language):
        try:
            if self.kind in ("image", "pdf"):
                self._work_pages(translator, ocr_language)
            else:
                self._work_texts(translator)
            if not self._cancel.is_set():
                self.signals.done.emit()
        except Exception as e:
            log.exception("Could not translate %s", self.path)
            self.signals.failed.emit(str(e) or e.__class__.__name__)

    def _work_pages(self, translator, ocr_language):
        reader = lens_ocr.Reader(ocr_language)
        total = lens_files.page_count(self.path)
        for index, image in enumerate(lens_files.pages(self.path)):
            if self._cancel.is_set():
                return
            self.signals.progress.emit(f"Reading and translating page {index + 1} of {total}…")
            blocks = lens_files.translate_page(reader, translator, image, self.target)
            self.signals.page.emit(index, image, blocks)

    def _work_texts(self, translator):
        if self.kind == "word":
            texts = lens_files.word_texts(self.path)
        else:
            texts = lens_files.text_lines(lens_files.read_text(self.path))
        self.signals.progress.emit(f"Translating {len(texts)} paragraphs…")
        translations = {}
        step = 40
        for start in range(0, len(texts), step):
            if self._cancel.is_set():
                return
            chunk = texts[start:start + step]
            translations.update(zip(chunk, translator.translate_many(chunk, self.target)))
            self.signals.progress.emit(f"Translated {min(start + step, len(texts))} of {len(texts)} paragraphs…")
        self.signals.texts.emit(translations)

    # ---- results (Qt thread) ---------------------------------------------------
    def _page_done(self, index, image, blocks):
        self.originals[index], self.blocks[index] = image, blocks
        self.rendered[index] = lens_files.render(image, blocks, self.target, self.style)
        label = QLabel()
        label.setAlignment(Qt.AlignCenter)
        self.page_labels.append(label)
        self.page_box.addWidget(label)
        self._show_page(index)
        self._fill_text()

    def _show_pages(self, *_):
        for index in self.rendered:
            self._show_page(index)

    def _show_page(self, index):
        image = self.originals[index] if self.original_button.isChecked() else self.rendered[index]
        width = max(self.scroll.viewport().width() - 24, 200)
        pixmap = QPixmap.fromImage(image)
        if pixmap.width() > width:
            pixmap = pixmap.scaledToWidth(width, Qt.SmoothTransformation)
        self.page_labels[index].setPixmap(pixmap)

    def _fill_text(self):
        parts = []
        for index in sorted(self.blocks):
            if len(self.blocks) > 1:
                parts.append(f"— Page {index + 1} —")
            parts += [block.translation for block in self.blocks[index]]
        self.text_view.setPlainText("\n".join(parts))

    def _texts_done(self, translations):
        self.translations = translations
        if self.kind == "word":
            original = "\n\n".join(lens_files.word_texts(self.path))
            translated = "\n\n".join(translations.get(t, t) for t in lens_files.word_texts(self.path))
        else:
            original = lens_files.read_text(self.path)
            translated = lens_files.translated_text(original, translations)
        self.original_text.setPlainText(original)
        self.text_view.setPlainText(translated)

    def _done(self):
        self.finished = True
        self.save_button.setEnabled(True)
        self.status.setText("Done — select text on the right to copy it, or save a translated copy.")

    def _failed(self, message):
        self.status.setText(f"Could not translate this file: {message}")

    def restyle(self, style):
        """The Lens look changed: draw the translations again."""
        self.style = style
        for index in list(self.rendered):
            self.rendered[index] = lens_files.render(self.originals[index], self.blocks[index], self.target, style)
        self._show_pages()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._show_pages()

    # ---- saving ----------------------------------------------------------------
    def save(self):
        suggested = lens_files.output_name(self.path, self.target)
        filters = {"image": "PNG picture (*.png);;JPEG picture (*.jpg)", "pdf": "PDF document (*.pdf)",
                   "word": "Word document (*.docx)"}.get(self.kind, f"Text file (*{os.path.splitext(self.path)[1]})")
        out, _ = QFileDialog.getSaveFileName(self, "Save the translated copy", suggested, filters)
        if not out:
            return
        try:
            self.write(out)
        except Exception as e:
            log.exception("Could not save %s", out)
            QMessageBox.warning(self, "EchoSub Lens", f"Could not save the file: {e}")
            return
        self.status.setText(f"Saved: {out}")

    def write(self, out):
        if os.path.abspath(out) == os.path.abspath(self.path):
            raise ValueError("Choose another name: the original file is kept as it is")
        if self.kind in ("image", "pdf"):
            images = [self.rendered[i] for i in sorted(self.rendered)]
            sizes = None
            if self.kind == "pdf":
                from PySide6.QtCore import QSizeF

                sizes = [QSizeF(img.width() / lens_files.PDF_SCALE, img.height() / lens_files.PDF_SCALE)
                         for img in images]
            lens_files.save_pages(images, out, sizes)
        elif self.kind == "word":
            lens_files.write_word(self.path, out, self.translations)
        else:
            lens_files.write_text(out, lens_files.translated_text(lens_files.read_text(self.path),
                                                                  self.translations))

    def closeEvent(self, event):
        self._cancel.set()
        super().closeEvent(event)
