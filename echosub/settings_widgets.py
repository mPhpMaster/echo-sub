# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Widgets and window sizing shared by the Settings window: searchable lists, colour buttons,
position icons, and keeping a window inside the screen it opens on."""
import re

import shiboken6
from PySide6.QtCore import QEvent, QObject, QSize, QStringListModel, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QColorDialog, QComboBox, QCompleter, QPushButton, QScrollArea,
)

from . import languages

SEARCH_ALIAS_ROLE = Qt.UserRole + 1


def _sorted_languages():
    return sorted(languages.LANGUAGES, key=languages.name)


# Extra text an item can be found by (e.g. a language's Arabic name) without showing it
SEARCH_ALIAS_ROLE = Qt.UserRole + 1


class SearchableComboBox(QComboBox):
    """Dropdown you can type into: the list filters to items containing the typed text."""

    def __init__(self, parent=None):
        super().__init__(parent)
        make_searchable(self)


_ARABIC_DIACRITICS = re.compile("[\u064B-\u0652\u0670\u0640]")  # harakat, dagger alif, tatweel
_ARABIC_LETTERS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي", "ؤ": "و", "ئ": "ي"})


def screen_for(widget):
    from PySide6.QtGui import QCursor

    return (QGuiApplication.screenAt(QCursor.pos()) or widget.screen()
            or QGuiApplication.primaryScreen())


def fit_to_screen(window, preferred_width, preferred_height):
    """Open at a comfortable size, but never bigger than the screen it appears on."""
    available = screen_for(window).availableGeometry()
    width = min(max(preferred_width, window.sizeHint().width()), available.width() - 40)
    height = min(max(preferred_height, window.sizeHint().height()), available.height() - 60)
    window.setMinimumWidth(min(480, width))
    window.setMaximumSize(available.width(), available.height())
    window.resize(width, height)


def move_onto_screen(window):
    """Pull a window back if it opens partly outside the screen."""
    available = screen_for(window).availableGeometry()
    frame = window.frameGeometry()
    x = min(max(frame.x(), available.left()), available.right() + 1 - frame.width())
    y = min(max(frame.y(), available.top()), available.bottom() + 1 - frame.height())
    if (x, y) != (frame.x(), frame.y()):
        window.move(max(available.left(), x), max(available.top(), y))


def _scrollable(widget):
    """The tab's contents in a scroll area that grows with the window."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.NoFrame)
    area.setWidget(widget)
    return area


def normalize_search(text):
    """Case-, hamza- and diacritic-insensitive form, so "ايطال" matches "الإيطالية"."""
    return _ARABIC_DIACRITICS.sub("", text.casefold()).translate(_ARABIC_LETTERS)


def make_searchable(combo):
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.NoInsert)
    edit = combo.lineEdit()
    edit.setPlaceholderText("Type to search…")

    # Our own match list instead of QCompleter's filtering, which can't ignore hamza/diacritics
    matches = QStringListModel(edit)
    completer = QCompleter(matches, edit)
    completer.setCompletionMode(QCompleter.UnfilteredPopupCompletion)
    edit.setCompleter(completer)

    def update_matches(text):
        needle = normalize_search(text.strip())
        items = []
        for i in range(combo.count()):
            label = combo.itemText(i)
            haystack = normalize_search(f"{label} {combo.itemData(i, SEARCH_ALIAS_ROLE) or ''}")
            if needle in haystack:
                items.append(label)
        matches.setStringList(items)
        if matches.rowCount():
            completer.complete()
        else:
            completer.popup().hide()

    def choose(text):
        index = combo.findText(text, Qt.MatchExactly)
        if index >= 0:
            combo.setCurrentIndex(index)

    def restore_text():
        # Typed text that isn't an item -> fall back to the selected item
        if not shiboken6.isValid(edit) or not shiboken6.isValid(combo):
            return  # fired while the dialog is being destroyed
        if combo.findText(edit.text(), Qt.MatchExactly) < 0:
            edit.setText(combo.itemText(combo.currentIndex()))  # currentText() would echo the typed text

    edit.textEdited.connect(update_matches)
    completer.activated[str].connect(choose)
    edit.editingFinished.connect(restore_text)
    edit.installEventFilter(_SelectAllOnFocus(edit))


class _SelectAllOnFocus(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.FocusIn:
            QTimer.singleShot(0, obj.selectAll)  # typing replaces the current value right away
        return False


def position_icon(row, col):
    """A tiny screen with the caption box drawn where this preset puts it."""
    w, h = 28, 18
    pm = QPixmap(w, h)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QColor("#9E9E9E"))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(1, 1, w - 2, h - 2, 3, 3)
    bw, bh = 12, 4
    x = {"left": 4, "center": (w - bw) // 2, "right": w - bw - 4}[col]
    y = {"top": 4, "middle": (h - bh) // 2, "bottom": h - bh - 4}[row]
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#E0E0E0"))
    p.drawRoundedRect(x, y, bw, bh, 1.5, 1.5)
    p.end()
    return QIcon(pm)


class ColorButton(QPushButton):
    changed = Signal()

    def __init__(self, color, text=True):
        super().__init__()
        self.show_text = text
        self.setMinimumWidth(36)
        self.setMaximumWidth(220 if text else 44)
        self.setToolTip("Click to pick a colour")
        self.set_color(color)
        self.clicked.connect(self._pick)

    def set_color(self, color):
        self.color = color
        self.setText(color.upper() if self.show_text else "")
        fg = "#000" if QColor(color).lightness() > 128 else "#fff"
        self.setStyleSheet(f"background:{color}; color:{fg}; border:1px solid #666; padding:4px;")

    def _pick(self):
        c = QColorDialog.getColor(QColor(self.color), self)
        if c.isValid():
            self.set_color(c.name())
            self.changed.emit()
