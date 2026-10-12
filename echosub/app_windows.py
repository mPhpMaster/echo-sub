# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Listening to one window: the open windows, the one in front, and the program behind a window.

Windows mixes sound per program, not per window, so "one window" means the program instance that
owns it — a second copy of VLC or a game started twice can be told apart, but two windows of one
Chrome cannot. A window is found again by its title; when the title changes (a new song, a new
tab), by the program that owned it as long as that program is still running.
"""
import ctypes
import logging
import os
from collections import namedtuple
from ctypes import wintypes

import psutil

log = logging.getLogger(__name__)

Window = namedtuple("Window", "title pid exe")

GW_OWNER = 4
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x80
DWMWA_CLOAKED = 14


def _exe(pid):
    try:
        return psutil.Process(pid).name()
    except Exception:
        return ""


def _title(user32, hwnd):
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value.strip()


def _pid(user32, hwnd):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _shown_in_taskbar(user32, hwnd):
    """Like the Alt+Tab list: visible, not a tool window, not owned by another, not hidden by Windows."""
    if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, GW_OWNER):
        return False
    if user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
        return False
    cloaked = wintypes.DWORD()
    try:
        ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
    except Exception:
        pass
    return not cloaked.value


def open_windows():
    """The windows a person can switch to, other than EchoSub's own, sorted by program and title."""
    try:
        user32 = ctypes.windll.user32
    except AttributeError:
        return []
    own = os.getpid()
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        try:
            if _shown_in_taskbar(user32, hwnd):
                title, pid = _title(user32, hwnd), _pid(user32, hwnd)
                if title and pid and pid != own:
                    found.append(Window(title, pid, _exe(pid)))
        except Exception:
            log.debug("Skipping a window", exc_info=True)
        return True

    try:
        user32.EnumWindows(visit, 0)
    except Exception as e:
        log.info("Could not list the open windows: %s", e)
    return sorted(found, key=lambda w: (w.exe.lower(), w.title.lower()))


def window_in_front():
    """The window in front right now, or None (nothing, or it is EchoSub's own)."""
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
    except Exception:
        return None
    if not hwnd:
        return None
    pid = _pid(user32, hwnd)
    title = _title(user32, hwnd)
    if not pid or pid == os.getpid() or not title:
        return None
    return Window(title, pid, _exe(pid))


def instance_root(pid):
    """The top process of the program copy that owns a window (its parents with the same file name)."""
    try:
        proc = psutil.Process(pid)
        name = proc.name().lower()
        while True:
            parent = proc.parent()
            if parent is None or parent.name().lower() != name:
                return proc.pid
            proc = parent
    except Exception:
        return pid


def find_pid(title, exe="", saved_pid=0, windows=None, exe_of=_exe):
    """The process to listen to for a chosen window, or None when it is not open.

    The same title first, then a title that contains it, then the program that owned the window
    when it was chosen, if it is still running (the title may have changed).
    """
    title = str(title or "").strip()
    exe = str(exe or "").strip().lower()
    if not title:
        return None
    windows = open_windows() if windows is None else windows
    mine = [w for w in windows if not exe or w.exe.lower() == exe]
    wanted = title.lower()
    for match in ([w for w in mine if w.title.lower() == wanted], [w for w in mine if wanted in w.title.lower()]):
        if match:
            return match[0].pid
    running = exe_of(saved_pid).lower() if saved_pid else ""
    if running and (not exe or running == exe):
        return saved_pid
    return None
