# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""EchoSub Lens: translates the text in an area of the screen, or a whole screen, in place.

A tool of its own, beside EchoSub: its own icon by the clock, its own settings (lens.json) and its
own process, so it runs with or without the captions. `EchoSub.exe --lens` or `python -m echosub --lens`.
"""
import ctypes
import json
import logging
import os
import sys

from . import cuda_setup, logging_setup

LENS_NAME = "EchoSub Lens"
INSTANCE_KEY = "EchoSub-Lens-single-instance"
MUTEX_NAME = "EchoSubLensMutex"  # the installer checks it too
VK_CONTROL = 0x11

DEFAULTS = {
    "mode": "screen",            # screen | area | mouse (a lens that follows the pointer)
    "mode_before_mouse": "screen",
    "lens_size": [480, 180],     # the lens around the mouse, logical pixels
    "lens_frame": True,          # a thin frame shows where the lens is
    "screen": "",                # screen name ("" = the main screen)
    "area": None,                # [x, y, w, h] relative to that screen, for mode "area"
    "target_lang": None,         # None = EchoSub's caption language
    "ocr_language": "auto",
    "translator": "same",
    "style": None,               # how translations look: lens_style.DEFAULT_STYLE, changed in Appearance
    "capture_visible": True,     # translations show in screenshots and screen sharing (Discord, OBS)
    "peek_seconds": 5,           # how often Lens looks at the page under its translations; 0: never
    "select_mode": False,        # translations take the mouse even without Ctrl
    "interval_ms": 700,
    "shortcuts": None,           # {action: key}, see lens_shortcuts.ACTIONS; None = the default keys
    "last_folder": "",           # where "Translate a file" opens
}


def config_path():
    from . import config
    return os.path.join(config.DATA_DIR, "lens.json")


def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(config_path(), encoding="utf-8") as f:
            cfg.update({k: v for k, v in json.load(f).items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    from .lens_style import merged

    cfg["style"] = merged(cfg["style"])
    return cfg


def save_config(cfg):
    with open(config_path(), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def launch_command(frozen=None, executable=None):
    """The command that starts Lens in a process of its own (used by EchoSub's tray menu)."""
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    executable = executable or sys.executable
    if frozen:
        return executable, ["--lens"]
    folder, name = os.path.split(executable)
    windowless = os.path.join(folder, "pythonw.exe")
    if name.lower() == "python.exe" and os.path.exists(windowless):
        executable = windowless
    return executable, ["-m", "echosub", "--lens"]


def launch():
    from PySide6.QtCore import QProcess

    program, args = launch_command()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return QProcess.startDetached(program, args, root)[0]


def ctrl_held():
    if sys.platform != "win32":
        return False
    return bool(ctypes.windll.user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)


def open_standalone_instead(argv=None):
    """`EchoSub.exe --lens` (the Start menu's "EchoSub Lens") opens the standalone EchoSub Lens when it is
    installed, passing on the files to translate. True when it did, so this built-in copy does not start."""
    from . import lens_standalone

    argv = sys.argv[1:] if argv is None else argv
    if lens_standalone.BUILTIN_FLAG in argv:
        return False
    started = lens_standalone.open_lens(lambda: False, files_to_open(argv))
    return started == "standalone"


def main():
    cuda_setup.setup()
    logging_setup.setup("lens.log")
    log = logging.getLogger("echosub.lens")
    if open_standalone_instead():
        return 0
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from . import __version__, config
    from .single_instance import claim_mutex, claim_server

    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"EchoSub.Lens.{__version__}")
        main.mutex, first = claim_mutex(MUTEX_NAME)
        if not first:
            _wake_running_copy()
            return 0
    qt = QApplication(sys.argv)
    qt.setApplicationName(LENS_NAME)
    qt.setWindowIcon(QIcon(os.path.join(config.ASSETS_DIR, "echosub.ico")))
    qt.setQuitOnLastWindowClosed(False)
    server = claim_server(qt, INSTANCE_KEY)
    if server is None:
        _wake_running_copy()
        return 0
    from .lens_ui import LensApp

    log.info("%s %s starting", LENS_NAME, __version__)
    lens = LensApp(qt, load_config(), save_config)
    for path in files_to_open(sys.argv[1:]):  # "EchoSub.exe --lens report.pdf"
        lens.open_file(path)
    server.newConnection.connect(lambda: (server.nextPendingConnection(), lens.already_running()))
    main.server = server
    code = qt.exec()
    log.info("%s exited", LENS_NAME)
    return code


def files_to_open(args):
    return [a for a in args if not a.startswith("-") and os.path.isfile(a)]


def _wake_running_copy():
    """Opened again while running: tell the running copy, which says where its icon is."""
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtNetwork import QLocalSocket

    QCoreApplication.instance() or QCoreApplication(sys.argv)
    probe = QLocalSocket()
    probe.connectToServer(INSTANCE_KEY)
    if probe.waitForConnected(500):
        probe.write(b"show")
        probe.waitForBytesWritten(300)
        probe.disconnectFromServer()


if __name__ == "__main__":
    sys.exit(main())
