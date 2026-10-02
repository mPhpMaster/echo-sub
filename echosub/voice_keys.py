# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Pressing keys by name, including combinations like Windows+R.

What this reaches is wide on purpose — the Windows key, Escape, the function keys and any
combination of them — because that is what was asked for. It is therefore kept behind its own
switch, off by default, and everything that guards a spoken command guards this one too: the PC's
own sound has to say the wake word first, and the countdown shows the keys before they are pressed.

Only the keys named in `KEYS` below can ever be sent. A word that is not in that table is not a
key, so a sentence that merely sounds like one presses nothing at all.
"""
import ctypes

MAX_KEYS = 4
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002

MODIFIERS = {
    "ctrl": 0x11, "control": 0x11, "ctl": 0x11, "كنترول": 0x11,
    "shift": 0x10, "شفت": 0x10,
    "alt": 0x12, "option": 0x12, "الت": 0x12,
    "windows": 0x5B, "win": 0x5B, "start": 0x5B, "super": 0x5B, "cmd": 0x5B,
    "ويندوز": 0x5B, "ستارت": 0x5B,
}

NAMED = {
    "enter": 0x0D, "return": 0x0D,
    "escape": 0x1B, "esc": 0x1B,
    "tab": 0x09, "space": 0x20, "spacebar": 0x20,
    "backspace": 0x08, "delete": 0x2E, "del": 0x2E, "insert": 0x2D,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "printscreen": 0x2C, "capslock": 0x14,
    "انتر": 0x0D, "ادخال": 0x0D,      # enter
    "اسكيب": 0x1B, "خروج": 0x1B,      # escape
    "تاب": 0x09, "مسافه": 0x20,            # tab, space
    "حذف": 0x2E, "فوق": 0x26, "تحت": 0x28,
    "يمين": 0x27, "يسار": 0x25,
}
NAMED.update({f"f{n}": 0x6F + n for n in range(1, 13)})            # F1 - F12
NAMED.update({chr(code): code for code in range(ord("A"), ord("Z") + 1)})
NAMED.update({chr(code).lower(): code for code in range(ord("A"), ord("Z") + 1)})
NAMED.update({str(digit): ord(str(digit)) for digit in range(10)})

KEYS = dict(NAMED)
KEYS.update(MODIFIERS)

# Keys Windows treats as "extended"; sending them without this flag works unreliably in some apps.
EXTENDED = {0x5B, 0x25, 0x26, 0x27, 0x28, 0x24, 0x23, 0x21, 0x22, 0x2D, 0x2E, 0x2C}

# Words that merely join two key names together and are not keys themselves.
JOINERS = {"and", "plus", "then", "with", "+", "&", "و", "مع", "ثم"}


def _names(words):
    names = [str(word).strip().lower().replace(" ", "") for word in words]
    return [name for name in names if name and name not in JOINERS]


def resolve(words):
    """Turn spoken words into the key presses to make, or None when any word is not a key.

    Two shapes, told apart by whether a modifier was named:

    - **A combination**: "windows and r" holds Windows while R is tapped — one press.
    - **One after another**: "a b c" taps those three keys in turn, which is what this did before
      combinations existed.

    "windows" on its own taps the Windows key, which is what opens the Start menu.
    """
    names = _names(words)
    if not names or len(names) > MAX_KEYS or any(name not in KEYS for name in names):
        return None
    modifier_codes = set(MODIFIERS.values())
    held = [KEYS[name] for name in names[:-1]]
    if not held or all(code in modifier_codes for code in held):
        return ((tuple(held), KEYS[names[-1]]),)
    if any(KEYS[name] in modifier_codes for name in names):
        return None  # a modifier in the middle of a run is neither shape, so press nothing
    return tuple(((), KEYS[name]) for name in names)


def label(words):
    """How it is written on screen: "Windows + R" for a combination, "A B C" for a run of keys."""
    names = _names(words)
    shown = [name.upper() if len(name) == 1 else name.title() for name in names]
    combination = len(names) > 1 and any(name in MODIFIERS for name in names[:-1])
    return (" + " if combination else " ").join(shown)


def _send(code, up):
    flags = (KEYEVENTF_EXTENDEDKEY if code in EXTENDED else 0) | (KEYEVENTF_KEYUP if up else 0)
    ctypes.windll.user32.keybd_event(code, 0, flags, 0)


def press(words):
    """Press the named keys. Held modifiers are always released, even if something goes wrong."""
    strokes = resolve(words)
    if strokes is None:
        raise ValueError("those are not keys I can press")
    for held, key in strokes:
        for code in held:
            _send(code, up=False)
        try:
            _send(key, up=False)
            _send(key, up=True)
        finally:
            for code in reversed(held):
                _send(code, up=True)
