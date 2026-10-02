# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Carrying out a command that was already recognized and checked.

Every entry that reaches here comes from `voice_registry` — a program name, a fixed address or a
Windows media key — or from something the user wrote in the settings: a folder, or a program line
of their own. Nothing is ever taken from the spoken text, and nothing goes through a shell.
"""
import ctypes
import logging
import os
import shlex
import shutil
import subprocess
import time
import webbrowser
import winreg

from . import voice_destinations, voice_keys, voice_typing
from .voice_registry import (
    APPS, CREATE_NO_WINDOW, LINKS, MEDIA_VIRTUAL_KEYS, WM_CLOSE,
)

log = logging.getLogger(__name__)


REPEAT_COOLDOWN_SEC = 4.0  # the same command is not run twice in a row within this time


def allowed_commands():
    """The one list a command may come from.

    Imported when it is needed rather than at the top, because the list is assembled in
    `voice_commands`, which in turn uses everything in this file.
    """
    from .voice_commands import COMMANDS

    return COMMANDS


class CommandRunner:
    """Runs a command from `COMMANDS`; anything else is refused."""

    def __init__(self, app_action=None, launcher=None, closer=None, key_presser=None, media_controller=None,
                 link_opener=None, url_opener=None, folder_opener=None, program_starter=None,
                 file_opener=None, typist=None, enter_presser=None):
        """`app_action(target)` handles EchoSub's own controls; the others exist for the tests."""
        self.app_action = app_action or (lambda target: False)
        self.link_opener = link_opener or open_link
        self.url_opener = url_opener or open_url
        self.folder_opener = folder_opener or open_folder
        self.file_opener = file_opener or open_file
        self.program_starter = program_starter or start_command_line
        self.typist = typist or voice_typing.type_text
        self.enter_presser = enter_presser or voice_typing.press_enter
        self.launcher = launcher or start_program
        self.closer = closer or close_program
        self.key_presser = key_presser or press_keys
        self.media_controller = media_controller or send_media_key
        self._last = (None, 0.0)

    def run(self, command_entry, now=None):
        """Returns what to tell the user, or None when the command was refused or repeated."""
        now = time.monotonic() if now is None else now
        action_of = command_entry.get("action") if isinstance(command_entry, dict) else None
        is_press = action_of == "press_keys"
        if (command_entry not in allowed_commands() and not (is_press and _valid_press_command(command_entry))
                and not (action_of == "reply" and isinstance(command_entry.get("target"), str))
                and not _valid_destination_command(command_entry)
                and not _valid_run_command(command_entry)
                and not _valid_typing_command(command_entry)):
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
        elif action == "open_link":
            self.link_opener(LINKS[target]["url"])
        elif action == "type_text":
            self.typist(target)
        elif action == "press_enter":
            self.enter_presser()
        elif action == "run":
            self.program_starter(target)
        elif action == "open_url":
            self.url_opener(target)
        elif action == "open_folder":
            if not self.folder_opener(target):
                return "That folder is not on this PC any more"
        elif action == "open_file":
            if not self.file_opener(target):
                return "That file is not on this PC any more"
        elif action == "app":
            if not self.app_action(target):
                return None
        elif action == "reply":
            return command_entry["label"]  # the app writes it in the caption box
        elif action == "help":
            return command_entry["label"]
        elif action == "press_keys":
            self.key_presser(target)
        elif action == "media":
            self.media_controller(target)
        else:
            log.warning("Refused an unknown action: %r", action)
            return None
        log.info("Voice command: %s", command_entry["key"])
        return command_entry["label"]


def _valid_destination_command(entry):
    """A "go to" command is built while listening, so it is checked again here, not just trusted."""
    if not isinstance(entry, dict):
        return False
    action, target = entry.get("action"), entry.get("target")
    if action == "open_url":
        return isinstance(target, str) and voice_destinations.spoken_url(target) == target
    if action == "open_folder":
        return isinstance(target, str) and os.path.isdir(target)
    if action == "open_file":
        return isinstance(target, str) and os.path.isfile(target)
    return False


def _valid_typing_command(entry):
    """Typed text is built while listening, so it is cleaned and checked again right here."""
    return (isinstance(entry, dict) and entry.get("action") == "type_text" and
            isinstance(entry.get("target"), str) and
            voice_typing.safe_text(entry["target"]) == entry["target"] != "")


def _valid_run_command(entry):
    """A saved program line, checked again here: it must be text that names something to start."""
    return (isinstance(entry, dict) and entry.get("action") == "run" and
            isinstance(entry.get("target"), str) and bool(split_command_line(entry["target"])))


def _valid_press_command(entry):
    """Checked again here: every word has to name a key, and only modifiers may be held."""
    keys = entry.get("target")
    return (isinstance(keys, (tuple, list)) and all(isinstance(key, str) for key in keys)
            and voice_keys.resolve(keys) is not None)


def open_link(url):
    """Open one of the fixed addresses in the user's own browser. Nothing else may be opened."""
    if url not in {link["url"] for link in LINKS.values()}:
        raise ValueError("that address is not on the list")
    webbrowser.open(url)


def split_command_line(command_line):
    """A typed line into program plus arguments, the way Windows quotes them.

    No shell is involved, so a backslash stays a path separator rather than an escape, and the
    shell's own punctuation (pipes, redirection, `&&`, variables) has no special meaning at all:
    every part here becomes one argument to one program and nothing more.
    """
    lexer = shlex.shlex(str(command_line), posix=True)
    lexer.escape = ""
    lexer.whitespace_split = True
    return [part for part in lexer if part]


def start_command_line(command_line):
    """Start what the user wrote into the settings: a program with arguments, or just a file.

    Only ever a line from the settings file: nothing from a transcript is added to it, so speech
    can pick one of these but can never build one. No shell is involved, which is why the two
    everyday shapes are handled here instead:

    - a line that is only a path to a file — a song, a document — is opened with the program
      Windows normally uses for it, the way double-clicking it would;
    - a leading `start`, which is a command-shell word rather than a program, is what people write
      to mean exactly that, so it is taken off and the rest is opened the same way.
    """
    parts = split_command_line(command_line) if isinstance(command_line, str) else []
    if parts and parts[0].lower() == "start":
        parts = parts[1:]
    if not parts:
        raise ValueError("there is no program or file to start")
    if len(parts) == 1 and os.path.isfile(parts[0]):
        log.info("Opening a saved file with its usual program")
        os.startfile(os.path.abspath(parts[0]))  # noqa: S606 (a file the user chose in the settings)
        return
    log.info("Starting a saved program line")
    try:
        subprocess.Popen(parts, shell=False, creationflags=CREATE_NO_WINDOW)
    except FileNotFoundError:
        raise FileNotFoundError(f"there is no program called {parts[0]!r} on this PC") from None


def open_url(url):
    """Open a web address in the user's own browser, and only if it is still a plain http/https site."""
    if voice_destinations.spoken_url(url) != url:
        raise ValueError("that is not a plain web address")
    webbrowser.open(url)


def open_folder(path):
    """Show a folder in File Explorer. Only a folder: a file is opened by `open_file` instead."""
    if not isinstance(path, str) or not os.path.isdir(path):
        return False
    os.startfile(os.path.abspath(path))  # noqa: S606 (a directory, checked just above)
    return True


def open_file(path):
    """Open one file the way double-clicking it would, with the program Windows uses for it.

    Only a file the user picked in the settings ever reaches here; a name that was said chooses
    between those saved paths and can never spell one out.
    """
    if not isinstance(path, str) or not os.path.isfile(path):
        return False
    os.startfile(os.path.abspath(path))  # noqa: S606 (a file the user chose in the settings)
    return True


def press_keys(keys):
    """Press one key or a combination, by name. Only words naming a key are ever accepted."""
    if not _valid_press_command({"target": tuple(keys)}):
        raise ValueError("those are not keys I can press")
    voice_keys.press(keys)


def send_media_key(target):
    """Send one standard Windows media key to the active system media session."""
    code = MEDIA_VIRTUAL_KEYS.get(target)
    if code is None:
        raise ValueError("Unsupported media action")
    user32 = ctypes.windll.user32
    user32.keybd_event(code, 0, 0, 0)
    user32.keybd_event(code, 0, 0x0002, 0)


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
