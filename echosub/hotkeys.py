# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""System-wide hotkeys via the Win32 RegisterHotKey API (work while a game or video has focus)."""
import ctypes
import logging
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter

log = logging.getLogger(__name__)

WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT = 0x0001, 0x0002, 0x0004, 0x4000
_user32 = ctypes.windll.user32
_user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
_user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]

# name -> (label shown in menus, modifiers, virtual key)
HOTKEYS = {
    "toggle_captions": ("Ctrl+Alt+H", MOD_CONTROL | MOD_ALT, ord("H")),
    "pause": ("Ctrl+Alt+P", MOD_CONTROL | MOD_ALT, ord("P")),
    "lock": ("Ctrl+Alt+L", MOD_CONTROL | MOD_ALT, ord("L")),
}


class GlobalHotkeys(QAbstractNativeEventFilter):
    """Register with `enable(app, {name: callback})`; callbacks run on the Qt main thread."""

    def __init__(self):
        super().__init__()
        self._callbacks = {}  # hotkey id -> callback
        self._app = None

    def enable(self, app, actions):
        """Returns the labels of hotkeys that could not be registered (already used by another app)."""
        self.disable()
        failed = []
        for index, (name, callback) in enumerate(actions.items(), start=1):
            label, mods, vk = HOTKEYS[name]
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
