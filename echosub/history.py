# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Session caption history: a viewer window and optional transcript files."""
import datetime
import html
import logging
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout,
)

from . import APP_NAME, config, languages

log = logging.getLogger(__name__)

TRANSCRIPTS_DIR = os.path.join(config.DATA_DIR, "transcripts")
MAX_RECORDS = 2000


def record_to_text(r):
    who = f"Speaker {r['speaker'] + 1}" if r["speaker"] is not None else "Speaker"
    head = f"[{r['time']:%H:%M:%S}] {who} ({languages.name(r['lang'])}): {r['original']}"
    if r["translated"] is not None and r["translated"] != r["original"]:
        head += f"\n    → {r['translated']}"
    return head


class History:
    """Keeps this session's captions and, if enabled, appends finished ones to a transcript file."""

    def __init__(self):
        self.records = []
        self._by_id = {}
        self._written = set()
        self.listeners = []
        self.save_to_file = False
        self._file_path = None

    def add(self, key, original, translated, lang, speaker):
        r = {"key": key, "time": datetime.datetime.now(), "original": original,
             "translated": translated, "lang": lang, "speaker": speaker}
        self.records.append(r)
        self._by_id[key] = r
        if len(self.records) > MAX_RECORDS:
            old = self.records.pop(0)
            self._by_id.pop(old["key"], None)
        if translated is not None:
            self._write(r)
        self._notify()

    def set_translation(self, key, translated):
        r = self._by_id.get(key)
        if r is not None:
            r["translated"] = translated
            self._write(r)
            self._notify()

    def flush_pending(self):
        """Write captions whose translation never arrived (engine restart / exit)."""
        for r in self.records:
            if r["key"] not in self._written:
                self._write(r)

    def clear(self):
        self.flush_pending()
        self.records.clear()
        self._by_id.clear()
        self._notify()

    def transcript_path(self):
        if self._file_path is None:
            os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)
            name = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".txt"
            self._file_path = os.path.join(TRANSCRIPTS_DIR, name)
        return self._file_path

    def _write(self, r):
        if r["key"] in self._written:
            return
        self._written.add(r["key"])
        if not self.save_to_file:
            return
        try:
            with open(self.transcript_path(), "a", encoding="utf-8") as f:
                f.write(record_to_text(r) + "\n")
        except OSError:
            log.exception("Could not write transcript")

    def _notify(self):
        for listener in list(self.listeners):
            listener()


class HistoryWindow(QDialog):
    def __init__(self, history, cfg, parent=None):
        super().__init__(parent)
        self.history = history
        self.cfg = cfg
        self.setWindowTitle(f"{APP_NAME} — Caption History")
        from .settings_dialog import fit_to_screen

        fit_to_screen(self, 760, 520)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)

        root = QVBoxLayout(self)
        self.count = QLabel()
        root.addWidget(self.count)
        self.view = QTextBrowser()
        self.view.setOpenLinks(False)
        root.addWidget(self.view)

        row = QHBoxLayout()
        copy_btn = QPushButton("Copy all")
        copy_btn.clicked.connect(self._copy)
        save_btn = QPushButton("Save as…")
        save_btn.clicked.connect(self._save)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(history.clear)
        folder_btn = QPushButton("Open transcripts folder")
        folder_btn.clicked.connect(open_transcripts_folder)
        for b in (copy_btn, save_btn, clear_btn, folder_btn):
            row.addWidget(b)
        row.addStretch(1)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.close)
        row.addWidget(close)
        root.addLayout(row)

        history.listeners.append(self.refresh)
        self.refresh()

    def closeEvent(self, event):
        if self.refresh in self.history.listeners:
            self.history.listeners.remove(self.refresh)
        super().closeEvent(event)

    def refresh(self):
        bar = self.view.verticalScrollBar()
        at_bottom = bar.value() >= bar.maximum() - 4
        colors = self.cfg["speaker_colors"]
        blocks = []
        for r in self.history.records:
            color = colors[r["speaker"] % len(colors)] if r["speaker"] is not None and colors else "#FFFFFF"
            who = f"Speaker {r['speaker'] + 1}" if r["speaker"] is not None else "Speaker"
            rtl_orig = ' dir="rtl"' if r["lang"] in languages.RTL else ""
            rtl_tr = ' dir="rtl"' if self.cfg["target_lang"] in languages.RTL else ""
            block = (
                f'<div style="margin-bottom:8px">'
                f'<span style="color:#888">{r["time"]:%H:%M:%S}</span> '
                f'<b style="color:{color}; background:#222">&nbsp;{who}&nbsp;</b> '
                f'<span style="color:#888">{html.escape(languages.name(r["lang"]))}</span>'
                f'<div{rtl_orig}>{html.escape(r["original"])}</div>'
            )
            if r["translated"] is None:
                block += '<div style="color:#888"><i>translating…</i></div>'
            elif r["translated"] != r["original"]:
                block += f'<div{rtl_tr} style="font-weight:600">{html.escape(r["translated"])}</div>'
            blocks.append(block + "</div>")
        self.view.setHtml("".join(blocks) or '<p style="color:#888">No captions yet in this session.</p>')
        self.count.setText(f"{len(self.history.records)} captions this session")
        if at_bottom:
            bar.setValue(bar.maximum())

    def _copy(self):
        QGuiApplication.clipboard().setText("\n".join(record_to_text(r) for r in self.history.records))

    def _save(self):
        default = os.path.join(TRANSCRIPTS_DIR, datetime.datetime.now().strftime("captions_%Y-%m-%d_%H-%M.txt"))
        os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(self, "Save captions", default, "Text files (*.txt)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(record_to_text(r) for r in self.history.records) + "\n")


def open_transcripts_folder():
    os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)
    os.startfile(TRANSCRIPTS_DIR)
