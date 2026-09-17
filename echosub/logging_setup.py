# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Log to logs/echosub.log (rotated) and to the console, and capture uncaught exceptions."""
import logging
import logging.handlers
import os
import sys
import threading

from . import config

LOG_DIR = os.path.join(config.DATA_DIR, "logs")
LOG_PATH = os.path.join(LOG_DIR, "echosub.log")


def setup():
    # pythonw (run.bat) has no console: sys.stdout/stderr are None and any library that prints
    # (e.g. Hugging Face download progress bars) would crash. Give them somewhere harmless to write.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
        has_console = False
    else:
        has_console = True
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

    os.makedirs(LOG_DIR, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(threadName)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if os.environ.get("ECHOSUB_DEBUG") else logging.INFO)

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    if has_console:
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(fmt)
        root.addHandler(console)

    for noisy in ("faster_whisper", "httpx", "httpcore", "urllib3", "huggingface_hub", "comtypes"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    def excepthook(exc_type, exc, tb):
        logging.getLogger("uncaught").critical("Uncaught exception", exc_info=(exc_type, exc, tb))

    def thread_excepthook(args):
        logging.getLogger("uncaught").critical(
            "Uncaught exception in thread %s", args.thread.name if args.thread else "?",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    sys.excepthook = excepthook
    threading.excepthook = thread_excepthook
    return LOG_PATH
