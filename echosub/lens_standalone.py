# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""The standalone EchoSub Lens (EchoSubLens.exe), when it is installed, is opened instead of the built-in one.

The standalone app is the same screen translator, released on its own and newer than the copy inside EchoSub.
Both claim the mutex "EchoSubLensMutex", so only one Lens runs at a time; starting EchoSubLens.exe while it
already runs just shows the running copy. Its folder is read from its installer's uninstall key (per user,
then per machine), with the usual install folders as a fallback.
"""
import logging
import os
import subprocess
import sys

log = logging.getLogger("echosub.lens")

STANDALONE_NAME = "EchoSub Lens"
STANDALONE_EXE = "EchoSubLens.exe"
STANDALONE_APP_ID = "{B3D7A1E4-5C2F-4F6B-9E8A-7D1C0B4E2F63}"  # the AppId in EchoSubLens.iss
UNINSTALL_KEY = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{STANDALONE_APP_ID}_is1"
BUILTIN_FLAG = "--builtin-lens"  # "EchoSub.exe --lens --builtin-lens" always opens the built-in Lens

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200


def registry_folders():
    """InstallLocation from the standalone installer's uninstall key: per user first, then per machine."""
    try:
        import winreg
    except ImportError:  # not Windows
        return []
    views = (getattr(winreg, "KEY_WOW64_64KEY", 0), getattr(winreg, "KEY_WOW64_32KEY", 0))
    folders = []
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in views:
            try:
                with winreg.OpenKey(hive, UNINSTALL_KEY, 0, winreg.KEY_READ | view) as key:
                    value, _ = winreg.QueryValueEx(key, "InstallLocation")
            except OSError:
                continue
            if isinstance(value, str) and value.strip() and value not in folders:
                folders.append(value.strip())
    return folders


def fallback_folders(environ=None):
    """Where the installer puts it by default, for an install whose uninstall key is missing."""
    environ = os.environ if environ is None else environ
    folders = []
    local = environ.get("LOCALAPPDATA")
    if local:
        folders.append(os.path.join(local, "Programs", STANDALONE_NAME))
    folders.append(os.path.join("D:\\", "Programs", STANDALONE_NAME))
    return folders


def find_standalone(registry=registry_folders, fallbacks=fallback_folders, exists=os.path.isfile):
    """Full path of EchoSubLens.exe, or None when the standalone EchoSub Lens is not installed."""
    for folder in [*registry(), *fallbacks()]:
        exe = os.path.join(folder, STANDALONE_EXE)
        if exists(exe):
            return exe
    return None


def is_this_program(exe, executable=None):
    """True when exe is the program running now, so it never starts itself in a loop."""
    executable = executable or sys.executable
    return os.path.normcase(os.path.abspath(exe)) == os.path.normcase(os.path.abspath(executable))


def launch_standalone(exe, args=(), popen=subprocess.Popen):
    """Starts EchoSubLens.exe on its own, without a console and outliving EchoSub. True if it started."""
    flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    try:
        popen([exe, *args], cwd=os.path.dirname(exe), creationflags=flags, close_fds=True,
              stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        log.warning("Could not start %s (%s): %s", STANDALONE_NAME, exe, e)
        return False
    log.info("Opened the standalone %s: %s", STANDALONE_NAME, exe)
    return True


def open_lens(builtin, args=(), find=None, launch=None):
    """Opens the standalone Lens when it is installed, else calls builtin(). Returns "standalone",
    "builtin" or None when neither started."""
    exe = (find or find_standalone)()  # looked up at call time, so tests can patch the module's functions
    if exe and not is_this_program(exe) and (launch or launch_standalone)(exe, args):
        return "standalone"
    return "builtin" if builtin() else None


def menu_text(find=None):
    """The tray menu item names the Lens that will open."""
    if (find or find_standalone)():
        return f"Screen translation ({STANDALONE_NAME})…"
    return f"{STANDALONE_NAME}: translate the screen…"
