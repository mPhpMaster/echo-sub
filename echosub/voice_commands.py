# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Spoken commands, limited to a fixed list of harmless actions.

Safety rules, in order of importance:

1. **A closed list.** Only the actions in `COMMANDS` and the apps in `APPS` can ever run. Nothing
   from the transcript is passed to a shell, used as a file name, or turned into a command line:
   what is heard only ever *selects* one of the entries written in this file.
2. **Nothing destructive.** The list holds only: opening or closing two ordinary Windows apps, and
   EchoSub's own caption controls. Shutting down or restarting the PC, deleting or moving files,
   changing Windows settings, sending keystrokes to other programs, opening a terminal and running
   any program by name are all deliberately absent, and must stay absent.
3. **Closing is as gentle as the app allows.** Notepad can hold text you have not saved, so it is
   asked to close the way the X button does, and it may still ask you to save. Calculator keeps
   nothing, and it ignores a polite request (it is a Store app), so it is closed outright.
4. **A wake word.** EchoSub listens to whatever the PC plays, so a video saying "open the
   calculator" must not open it. A command only counts when the wake word comes first and the
   command follows within a few words.
5. **Off unless asked for.** The feature is disabled by default, and a command is ignored while the
   engine is paused.
"""
import ctypes
import logging
import os
import re
import shutil
import subprocess
import time
import winreg

from . import voice_vocabulary as vocabulary

log = logging.getLogger(__name__)

DEFAULT_WAKE_WORDS = ("echo sub", "echosub", "إيكو صب", "ايكو صب")
MAX_WORDS_AFTER_WAKE = 8   # the command must follow the wake word closely
MAX_WINDOW_CHARS = 60      # ...and in languages written without spaces, this many characters
PREFIX_MATCH_MIN_CHARS = 5  # from this length a word may carry a grammatical ending
REPEAT_COOLDOWN_SEC = 4.0  # the same command is not run twice in a row within this time
CREATE_NO_WINDOW = 0x08000000
WM_CLOSE = 0x0010

# Only these programs may be started or closed. Both are ordinary Windows accessories.
# "close": "polite" asks the window to close (unsaved work is safe); "force" ends the process,
# which is only used for an app that keeps nothing and ignores the polite request.
APPS = {
    "calculator": {
        "launch": "calc.exe", "close": "force",
        "processes": ("CalculatorApp.exe", "Calculator.exe", "calc.exe"),
    },
    "notepad": {
        "launch": "notepad.exe", "close": "polite", "processes": ("Notepad.exe", "notepad.exe"),
    },
    "paint": {
        "launch": "mspaint.exe", "close": "polite", "processes": ("mspaint.exe", "PaintApp.exe"),
    },
    "files": {  # File Explorer: only its folder windows are closed, never the desktop or taskbar
        "launch": "explorer.exe", "close": "polite", "processes": ("explorer.exe",),
        "window_classes": ("CabinetWClass", "ExploreWClass"),
    },
    "settings": {
        "launch": "ms-settings:", "close": "polite", "processes": ("SystemSettings.exe",),
    },
    "task manager": {
        "launch": "taskmgr.exe", "close": "polite", "processes": ("Taskmgr.exe", "taskmgr.exe"),
    },
    "snipping tool": {
        "launch": "snippingtool.exe", "close": "polite",
        "processes": ("SnippingTool.exe", "ScreenSketch.exe", "snippingtool.exe"),
    },
    "on-screen keyboard": {
        "launch": "osk.exe", "close": "force", "processes": ("osk.exe",),
    },
    "magnifier": {
        "launch": "magnify.exe", "close": "force", "processes": ("Magnify.exe", "magnify.exe"),
    },
    "character map": {
        "launch": "charmap.exe", "close": "polite", "processes": ("charmap.exe",),
    },
    "chrome": {
        "launch": "chrome.exe", "close": "polite", "processes": ("chrome.exe",),
    },
    "edge": {
        "launch": "msedge.exe", "close": "polite", "processes": ("msedge.exe",),
    },
    "firefox": {
        "launch": "firefox.exe", "close": "polite", "processes": ("firefox.exe",),
    },
    "vlc": {
        "launch": "vlc.exe", "close": "polite", "processes": ("vlc.exe",),
        "paths": (r"%ProgramFiles%\VideoLAN\VLC\vlc.exe", r"%ProgramFiles(x86)%\VideoLAN\VLC\vlc.exe"),
    },
    "vs code": {
        "launch": "code.exe", "close": "polite", "processes": ("Code.exe",),
        "paths": (r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe",
                  r"%ProgramFiles%\Microsoft VS Code\Code.exe"),
    },
    "discord": {
        "launch": "discord.exe", "close": "polite", "processes": ("Discord.exe",),
        "paths": (r"%LOCALAPPDATA%\Discord\Update.exe",),
        "arguments": ("--processStart", "Discord.exe"),
    },
    "steam": {
        "launch": "steam.exe", "close": "polite", "processes": ("steam.exe",),
        "paths": (r"%ProgramFiles(x86)%\Steam\steam.exe", r"%ProgramFiles%\Steam\steam.exe"),
    },
    "spotify": {
        "launch": "spotify.exe", "close": "polite", "processes": ("Spotify.exe",),
        "paths": (r"%APPDATA%\Spotify\Spotify.exe",),
    },
}
for _name, _app in APPS.items():
    _app["words"] = vocabulary.APP_WORDS[_name]

OPEN_WORDS = vocabulary.OPEN_WORDS
CLOSE_WORDS = vocabulary.CLOSE_WORDS

CAPTION_COMMANDS = (
    {"key": "pause_captions", "action": "app", "target": "pause", "label": "Captions paused"},
    {"key": "resume_captions", "action": "app", "target": "resume", "label": "Captions resumed"},
    {"key": "hide_captions", "action": "app", "target": "hide", "label": "Caption box hidden"},
    {"key": "show_captions", "action": "app", "target": "show", "label": "Caption box shown"},
    {"key": "clear_captions", "action": "app", "target": "clear", "label": "Captions cleared"},
)

APP_COMMANDS = tuple(
    {"key": f"{verb}_{name}", "action": f"{verb}_app", "target": name,
     "label": f"{name.title()} {'opened' if verb == 'open' else 'closed'}"}
    for name in APPS for verb in ("open", "close")
)

COMMANDS = CAPTION_COMMANDS + APP_COMMANDS

_ARABIC_MARKS = re.compile(r"[ً-ْـ]")
_PUNCTUATION = re.compile(r"[^\w\s؀-ۿ]+", re.UNICODE)


def normalize(text):
    """Lower-case, drop punctuation and Arabic diacritics, and even out spacing, alifs and taa."""
    text = _ARABIC_MARKS.sub("", str(text).lower())
    text = _PUNCTUATION.sub(" ", text)
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ة", "ه").replace("ى", "ي")
    return re.sub(r"\s+", " ", text).strip()


def command(key):
    return next(c for c in COMMANDS if c["key"] == key)


def _needs_word_boundary(word):
    """Chinese, Japanese, Korean and Thai are written without spaces, so they match as plain text."""
    return not any(low <= ord(ch) <= high for ch in word for low, high in vocabulary.NO_SPACE_RANGES)


def position_of(window, word):
    """Where `word` appears in the sentence, or -1. Whole words, except for space-less scripts."""
    word = normalize(word)
    if not word:
        return -1
    if not _needs_word_boundary(word):
        return window.find(word)
    # Turkish, Arabic, Hindi and others glue endings onto a word ("altyazi" -> "altyazilari"),
    # so a long word may be the start of the spoken one; a short one must match exactly.
    tail = "" if len(word) >= PREFIX_MATCH_MIN_CHARS else r"(?!\w)"
    match = re.search(rf"(?<!\w){re.escape(word)}{tail}", window)
    return match.start() if match else -1


def _first_position(window, words):
    found = [position_of(window, word) for word in words]
    found = [index for index in found if index >= 0]
    return min(found) if found else -1


def _app_command(window):
    """An app command is 'a word for open/close' plus 'a word for the app', in any order."""
    for name, app in APPS.items():
        if _first_position(window, app["words"]) < 0:
            continue
        opening = _first_position(window, OPEN_WORDS)
        closing = _first_position(window, CLOSE_WORDS)
        if opening < 0 and closing < 0:
            continue
        wants_close = closing >= 0 and (opening < 0 or closing < opening)
        return command(f"{'close' if wants_close else 'open'}_{name}")
    return None


def _echosub_command(window):
    """A caption command is 'a word for the action' plus a word for captions/subtitles."""
    if _first_position(window, vocabulary.CAPTION_WORDS) < 0:
        return None
    best, best_at = None, -1
    for key, words in vocabulary.CAPTION_ACTIONS:
        at = _first_position(window, words)
        if at >= 0 and (best_at < 0 or at < best_at):
            best, best_at = key, at
    return command(best) if best else None


def find(text, wake_words=DEFAULT_WAKE_WORDS):
    """The command in `text`, or None. The wake word must come first, then the command."""
    return find_detail(text, wake_words)[0]


def find_detail(text, wake_words=DEFAULT_WAKE_WORDS):
    """(command, what was said after the wake word).

    The second value lets the app say "I heard you but that was not a command", which is very
    different from not having been spoken to at all.
    """
    spoken = normalize(text)
    heard = None
    for wake in wake_words:
        wake = normalize(wake)
        if not wake:
            continue
        # Whole words only: a short wake word such as "da" must not fire inside "today"
        for match in re.finditer(rf"(?<!\w){re.escape(wake)}(?!\w)", spoken):
            tail = spoken[match.end():].strip()
            if not tail:
                continue
            window = " ".join(tail.split()[:MAX_WORDS_AFTER_WAKE])[:MAX_WINDOW_CHARS]
            found = _echosub_command(window) or _app_command(window)
            if found is not None:
                return found, window
            heard = heard or window
            log.info("Heard the wake word but no command in %r", window)
    return None, heard


class CommandRunner:
    """Runs a command from `COMMANDS`; anything else is refused."""

    def __init__(self, app_action=None, launcher=None, closer=None):
        """`app_action(target)` handles EchoSub's own controls; the others exist for the tests."""
        self.app_action = app_action or (lambda target: False)
        self.launcher = launcher or start_program
        self.closer = closer or close_program
        self._last = (None, 0.0)

    def run(self, command_entry, now=None):
        """Returns what to tell the user, or None when the command was refused or repeated."""
        now = time.monotonic() if now is None else now
        if command_entry not in COMMANDS:
            log.warning("Refused a command that is not on the list: %r", command_entry)
            return None
        key, last_time = self._last
        if key == command_entry["key"] and now - last_time < REPEAT_COOLDOWN_SEC:
            return None  # the same sentence recognized twice, or an echo of it
        self._last = (command_entry["key"], now)
        action, target = command_entry["action"], command_entry["target"]
        if action == "open_app":
            try:
                self.launcher(APPS[target])
            except AppNotInstalled:
                return f"{target.title()} is not installed on this PC"
        elif action == "close_app":
            if not self.closer(APPS[target], APPS[target]["close"]):
                return f"{target.title()} was not open"
        elif action == "app":
            if not self.app_action(target):
                return None
        else:
            log.warning("Refused an unknown action: %r", action)
            return None
        log.info("Voice command: %s", command_entry["key"])
        return command_entry["label"]


class AppNotInstalled(Exception):
    """The app is on the list but not on this PC."""


def resolve_program(app):
    """Where the program is, or None. Only entries of APPS are ever looked up."""
    launch = app["launch"]
    if launch.endswith(":"):
        return launch  # a Windows page such as ms-settings:
    found = shutil.which(launch)
    if found:
        return found
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(root, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{launch}") as key:
                path = str(winreg.QueryValueEx(key, None)[0]).strip('"')
        except OSError:
            continue
        if path and os.path.exists(path):
            return path
    for candidate in app.get("paths", ()):
        candidate = os.path.expandvars(candidate)
        if os.path.exists(candidate):
            return candidate
    return None


def start_program(app):
    """Start one of the allowed programs. The entry is from APPS, never from the transcript."""
    if app not in APPS.values():
        raise ValueError("that program is not on the list")
    target = resolve_program(app)
    if target is None:
        raise AppNotInstalled(app["launch"])
    if target.endswith(":"):
        os.startfile(target)  # noqa: S606 - a fixed Windows page from the list above
        return
    subprocess.Popen([target, *app.get("arguments", ())], shell=False, creationflags=CREATE_NO_WINDOW)


def close_program(app, mode="polite"):
    """Close an allowed program. Returns True when something was closed.

    "polite" asks its windows to close, exactly like clicking the X, so an app with unsaved work
    can still ask the user about it. "force" is only used for an app that keeps nothing and that
    ignores the polite request. File Explorer only ever has its folder windows closed, never the
    desktop or the taskbar, which belong to the same program.
    """
    if app not in APPS.values():
        raise ValueError("that program is not on the list")
    closed = False
    for name in app["processes"]:
        pids = _pids_of(name)
        if not pids:
            continue
        if mode == "polite" and _ask_windows_to_close(pids, app.get("window_classes")):
            closed = True
            continue
        if mode == "force":
            result = subprocess.run(["taskkill", "/IM", name, "/F"], shell=False, capture_output=True,
                                    creationflags=CREATE_NO_WINDOW, timeout=5)
            closed = closed or result.returncode == 0
    return closed


def _pids_of(image_name):
    """The process ids of a running allowed program, straight from Windows' own task list."""
    try:
        result = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/NH", "/FO", "CSV"],
                                shell=False, capture_output=True, text=True,
                                creationflags=CREATE_NO_WINDOW, timeout=5)
    except (OSError, subprocess.SubprocessError) as e:
        log.warning("Could not list processes: %s", e)
        return []
    pids = []
    for line in result.stdout.splitlines():
        parts = [part.strip('" ') for part in line.split('","')]
        if len(parts) > 1 and parts[0].lower() == image_name.lower() and parts[1].isdigit():
            pids.append(int(parts[1]))
    return pids


def _ask_windows_to_close(pids, window_classes=None):
    """Send every top-level window of those processes the same message the X button sends."""
    user32 = ctypes.windll.user32
    wanted, closed = set(pids), False

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def visit(handle, _param):
        nonlocal closed
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(handle, ctypes.byref(pid))
        if pid.value not in wanted or not user32.IsWindowVisible(handle):
            return True
        if window_classes and _window_class(handle) not in window_classes:
            return True  # the desktop and the taskbar are windows of Explorer too
        user32.PostMessageW(handle, WM_CLOSE, 0, 0)
        closed = True
        return True

    user32.EnumWindows(visit, None)
    return closed


def _window_class(handle):
    buffer = ctypes.create_unicode_buffer(256)
    ctypes.windll.user32.GetClassNameW(handle, buffer, len(buffer))
    return buffer.value
