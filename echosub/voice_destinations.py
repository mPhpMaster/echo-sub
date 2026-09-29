# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Where "go to ..." is allowed to lead: a web address, or a folder from a list you control.

This is the one command that reads something out of what was said rather than picking an entry
from a list, so it is kept narrow on purpose:

- **A web address only opens in your browser.** It has to look like a real domain, and only
  `http`/`https` survive; `file:`, `javascript:`, a user:password in front of the host and anything
  else are refused before Windows ever sees the text. Nothing is downloaded or run.
- **A folder only opens in File Explorer**, and only if it is one of your own Windows folders or
  one you added yourself in the settings, with the name you want to say for it. A spoken word never
  becomes a path: it only picks a path that is already written down.
- **A file opens the way double-clicking it would**, with whatever program Windows normally uses
  for it, and again only if you chose that exact file in the settings yourself.
"""
import ctypes
import os
import re

MAX_FOLDERS = 20
MAX_NAME_CHARS = 40

# The user's own Windows folders, by the id Windows itself uses, so a folder moved to OneDrive or to
# another drive is still found where it really is.
_KNOWN_IDS = {
    "desktop": "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
    "documents": "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}",
    "downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
    "music": "{4BD8D571-6D19-48D3-BE97-422220080E43}",
    "pictures": "{33E28130-4E1E-4676-835A-98395C3BC3BB}",
    "videos": "{18989B1D-99B5-455B-841C-AB7C74E4DDFC}",
}
HOME = "home"

_DOMAIN = re.compile(
    r"^(?:(?P<scheme>https?)://)?"
    r"(?P<host>(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24})"
    r"(?::(?P<port>\d{1,5}))?"
    r"(?P<path>/[^\s]*)?$"
)
# "www dot example dot com" is how a dictated address often arrives
_SPOKEN_DOT = re.compile(r"\s*(?:\bdot\b|\bpoint\b|نقطة|دوت)\s*", re.IGNORECASE)


class _GUID(ctypes.Structure):
    _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16), ("c", ctypes.c_uint16),
                ("d", ctypes.c_ubyte * 8)]


def _known_folder(folder_id):
    """Ask Windows where one of the user's folders really is; None when it cannot be resolved."""
    guid = _GUID()
    if ctypes.windll.ole32.CLSIDFromString(ctypes.c_wchar_p(folder_id), ctypes.byref(guid)) != 0:
        return None
    out = ctypes.c_wchar_p()
    if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(out)) != 0:
        return None
    path = out.value
    ctypes.windll.ole32.CoTaskMemFree(out)
    return path


def windows_folders():
    """The user's own folders that "go to" may open, as {name: path}."""
    found = {}
    for name, folder_id in _KNOWN_IDS.items():
        try:
            path = _known_folder(folder_id)
        except (AttributeError, OSError):  # not Windows, or the call is unavailable
            path = os.path.join(os.path.expanduser("~"), name.title())
        if path and os.path.isdir(path):
            found[name] = path
    home = os.path.expanduser("~")
    if os.path.isdir(home):
        found[HOME] = home
    return found


def valid_folders(entries):
    """Places the user added: a name to say and the folder or file it stands for."""
    folders, seen = [], set()
    for entry in entries or ():
        if not isinstance(entry, dict):
            continue
        name = re.sub(r"\s+", " ", str(entry.get("name", ""))).strip()[:MAX_NAME_CHARS]
        path = str(entry.get("path", "")).strip().strip('"')
        key = name.lower()
        if not name or not path or key in seen:
            continue
        seen.add(key)
        folders.append({"name": name, "path": path})
        if len(folders) >= MAX_FOLDERS:
            break
    return folders


def spoken_url(text):
    """A web address out of what was said, or None. Only a plain http/https site survives."""
    said = _SPOKEN_DOT.sub(".", str(text).strip()).strip()
    said = said.rstrip(".,;:!?،؟").replace(" ", "")
    if not said or len(said) > 300 or "@" in said or "\\" in said:
        return None
    match = _DOMAIN.match(said.lower())
    if not match:
        return None
    scheme = match.group("scheme") or "https"
    rest = said[len(match.group("scheme")) + 3:] if match.group("scheme") else said
    return f"{scheme}://{rest}"


def find_folder(said, folders, windows_too=True):
    """The place one of the spoken words names, or None. The path is never taken from speech.

    `windows_too` is off for "play …", where only the places you added yourself are meant: "play
    music" should press play, not open your Music folder.
    """
    wanted = re.sub(r"\s+", " ", str(said)).strip().lower().rstrip(".,;:!?،؟")
    if not wanted:
        return None
    for entry in valid_folders(folders):
        if entry["name"].lower() == wanted:
            return {"name": entry["name"], "path": entry["path"]}
    if not windows_too:
        return None
    from . import voice_vocabulary as vocabulary

    for name, words in vocabulary.FOLDER_WORDS.items():
        if any(wanted == word.lower() for word in words):
            path = windows_folders().get(name)
            if path:
                return {"name": name, "path": path}
    return None


def destination_command(said, folders, windows_too=True, allow_url=True):
    """A command for what followed "go to" or "play", or None when it names nothing known."""
    folder = find_folder(said, folders, windows_too)
    if folder is not None:
        # A folder is shown in Explorer; a file is opened with the program Windows uses for it, the
        # way double-clicking it would. Which of the two it is, is decided by the path on disk.
        a_file = os.path.isfile(folder["path"])
        return {"key": f"go_{'file' if a_file else 'folder'}:{folder['name'].lower()}",
                "action": "open_file" if a_file else "open_folder",
                "target": folder["path"], "label": f"Opened {folder['name']}"}
    url = spoken_url(said) if allow_url else None
    if url is not None:
        return {"key": f"go_url:{url.lower()}", "action": "open_url", "target": url,
                "label": f"Opened {url}"}
    return None
