# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Typing out what was said, into whatever window has the keyboard.

This is the one command that puts the spoken words themselves into another program, so it is the
one with the most care around it:

- **Off unless you switch it on**, in *Settings → Commands*.
- **The wake word is still required** for anything the PC plays, so a video or a call has to
  address EchoSub by name before a word of it can be typed. Your own microphone follows the same
  rule as every other command.
- **The countdown shows the exact text first.** Nothing is typed until it ends, and one click on
  the notice stops it.
- **Only printable characters**, trimmed and capped. A new line, a tab and every control character
  are removed, so a typed line can never submit itself; `Enter` is a separate command you have to
  ask for by name.
"""
import ctypes
import re
from ctypes import wintypes

MAX_TYPE_CHARS = 200
VK_RETURN = 0x0D
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

_ULONG_PTR = ctypes.POINTER(ctypes.c_ulong)


class _KeyboardInput(ctypes.Structure):
    _fields_ = (("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", _ULONG_PTR))


class _MouseInput(ctypes.Structure):
    _fields_ = (("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", _ULONG_PTR))


class _HardwareInput(ctypes.Structure):
    _fields_ = (("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD))


class _InputUnion(ctypes.Union):
    _fields_ = (("mi", _MouseInput), ("ki", _KeyboardInput), ("hi", _HardwareInput))


class _Input(ctypes.Structure):
    _fields_ = (("type", wintypes.DWORD), ("value", _InputUnion))


def safe_text(said):
    """What may actually be typed: printable characters only, tidied and capped.

    Line breaks and tabs are taken out rather than escaped, because a typed line that can press
    Enter by itself would be able to send a message or run a command without being asked.
    """
    text = "".join(ch for ch in str(said) if ch.isprintable())
    return re.sub(r"\s+", " ", text).strip()[:MAX_TYPE_CHARS]


def type_text(text):
    """Type `text` into whichever window has the keyboard, one character at a time."""
    text = safe_text(text)
    if not text:
        raise ValueError("there is nothing to type")
    # UTF-16 code units, so letters outside the basic set (an emoji, say) arrive whole.
    encoded = text.encode("utf-16-le")
    events = []
    for index in range(0, len(encoded), 2):
        code = int.from_bytes(encoded[index:index + 2], "little")
        for flags in (KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP):
            events.append(_Input(type=INPUT_KEYBOARD,
                                 value=_InputUnion(ki=_KeyboardInput(wVk=0, wScan=code, dwFlags=flags,
                                                                     time=0, dwExtraInfo=None))))
    array = (_Input * len(events))(*events)
    ctypes.windll.user32.SendInput(len(events), array, ctypes.sizeof(_Input))
    return text


def press_enter():
    """Press Enter once. Asked for by name, never bundled into typed text."""
    user32 = ctypes.windll.user32
    user32.keybd_event(VK_RETURN, 0, 0, 0)
    user32.keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0)
