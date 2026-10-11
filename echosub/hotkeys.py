# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""System-wide hotkeys via the Win32 RegisterHotKey API (work while a game or video has focus)."""
import ctypes
import logging
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter

log = logging.getLogger(__name__)

WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x0001, 0x0002, 0x0004, 0x0008, 0x4000
_user32 = ctypes.windll.user32
_user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
_user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]

# name -> (label shown in menus, modifiers, virtual key)
HOTKEYS = {
    "toggle_captions": ("Ctrl+Alt+H", MOD_CONTROL | MOD_ALT, ord("H")),
    "pause": ("Ctrl+Alt+P", MOD_CONTROL | MOD_ALT, ord("P")),
    "lock": ("Ctrl+Alt+L", MOD_CONTROL | MOD_ALT, ord("L")),
}


def _special_keys():
    """Qt key -> Windows virtual key, for the keys that are not a letter, a digit or F1-F24."""
    from PySide6.QtCore import Qt

    k = Qt.Key
    return {
        k.Key_Space: 0x20, k.Key_Return: 0x0D, k.Key_Enter: 0x0D, k.Key_Escape: 0x1B, k.Key_Tab: 0x09,
        k.Key_Backspace: 0x08, k.Key_Insert: 0x2D, k.Key_Delete: 0x2E, k.Key_Home: 0x24, k.Key_End: 0x23,
        k.Key_PageUp: 0x21, k.Key_PageDown: 0x22, k.Key_Left: 0x25, k.Key_Up: 0x26, k.Key_Right: 0x27,
        k.Key_Down: 0x28, k.Key_Pause: 0x13, k.Key_Print: 0x2C, k.Key_ScrollLock: 0x91, k.Key_CapsLock: 0x14,
        k.Key_NumLock: 0x90, k.Key_Semicolon: 0xBA, k.Key_Equal: 0xBB, k.Key_Plus: 0xBB, k.Key_Comma: 0xBC,
        k.Key_Minus: 0xBD, k.Key_Period: 0xBE, k.Key_Slash: 0xBF, k.Key_QuoteLeft: 0xC0,
        k.Key_BracketLeft: 0xDB, k.Key_Backslash: 0xDC, k.Key_BracketRight: 0xDD, k.Key_Apostrophe: 0xDE,
        k.Key_VolumeMute: 0xAD, k.Key_VolumeDown: 0xAE, k.Key_VolumeUp: 0xAF, k.Key_MediaNext: 0xB0,
        k.Key_MediaPrevious: 0xB1, k.Key_MediaStop: 0xB2, k.Key_MediaPlay: 0xB3, k.Key_MediaTogglePlayPause: 0xB3,
        k.Key_Asterisk: 0x6A,
    }


def parse(text):
    """(modifiers, virtual key) of a shortcut written like "Ctrl+Shift+F5", "F8" or "Alt+1"; None if unusable.

    Any key can be used, alone or with Ctrl, Alt, Shift and the Windows key. Keypad digits count
    as their own keys ("Num+5").
    """
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeySequence

    if not text:
        return None
    sequence = QKeySequence(text, QKeySequence.PortableText)
    if sequence.count() != 1:
        return None
    combo = sequence[0]
    key, held = combo.key(), combo.keyboardModifiers()
    mods = 0
    for flag, mod in ((Qt.ControlModifier, MOD_CONTROL), (Qt.AltModifier, MOD_ALT),
                      (Qt.ShiftModifier, MOD_SHIFT), (Qt.MetaModifier, MOD_WIN)):
        if held & flag:
            mods |= mod
    value = int(key.value if hasattr(key, "value") else key)
    if held & Qt.KeypadModifier and ord("0") <= value <= ord("9"):
        return mods, 0x60 + value - ord("0")
    if ord("A") <= value <= ord("Z") or ord("0") <= value <= ord("9"):
        return mods, value
    f1 = int(Qt.Key.Key_F1.value)
    if f1 <= value <= f1 + 23:
        return mods, 0x70 + value - f1
    vk = {int(k.value): code for k, code in _special_keys().items()}.get(value)
    return (mods, vk) if vk else None


class GlobalHotkeys(QAbstractNativeEventFilter):
    """Register with `enable(app, {name: callback})`; callbacks run on the Qt main thread."""

    def __init__(self):
        super().__init__()
        self._callbacks = {}  # hotkey id -> callback
        self._app = None

    def enable(self, app, actions):
        """Returns the labels of hotkeys that could not be registered (already used by another app)."""
        return self.enable_keys(app, [HOTKEYS[name] + (callback,) for name, callback in actions.items()])

    def enable_keys(self, app, bindings):
        """`bindings`: [(label, modifiers, virtual key, callback)]. Returns the labels already taken elsewhere."""
        self.disable()
        failed = []
        for index, (label, mods, vk, callback) in enumerate(bindings, start=1):
            if _user32.RegisterHotKey(None, index, mods | MOD_NOREPEAT, vk):
                self._callbacks[index] = callback
            else:
                log.warning("Hotkey %s is already in use by another program", label)
                failed.append(label)
        if self._callbacks:
            self._app = app
            app.installNativeEventFilter(self)
        return failed

    def disable(self):
        for index in self._callbacks:
            _user32.UnregisterHotKey(None, index)
        self._callbacks.clear()
        if self._app is not None:
            self._app.removeNativeEventFilter(self)
            self._app = None

    def nativeEventFilter(self, event_type, message):
        if event_type == b"windows_generic_MSG" and self._callbacks:
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam in self._callbacks:
                self._callbacks[msg.wParam]()
                return True, 0
        return False, 0


def label(name):
    return HOTKEYS[name][0]
