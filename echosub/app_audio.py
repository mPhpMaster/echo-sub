# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Listening to one program only — Discord, say, without the game's sound or the music — or to the
program behind one window (app_windows).

Windows 10 (2004) and later can capture what one program plays, with the programs it started
(Process Loopback). Python cannot reach that directly, so a small helper that ships with EchoSub,
app-audio.exe, does it and hands the sound over through a pipe. Everything after that is the same
as for the whole PC: the same catch-up buffer, the same speech detection.

If the program is not running, EchoSub listens to everything the PC plays instead, says so, and
goes back to the program by itself once it starts.
"""
import logging
import os
import subprocess
import sys
import threading

import psutil
import soxr

from . import app_windows, audio, config

log = logging.getLogger(__name__)

HELPER = "app-audio.exe"
RATE = 48000
FRAME_BYTES = 4                # 16-bit stereo
READ_BYTES = RATE * FRAME_BYTES // 20   # 50 ms
MIN_WINDOWS_BUILD = 19041      # Windows 10 2004


class AppNotRunning(Exception):
    pass


def helper_path():
    candidates = []
    if config.FROZEN:
        candidates.append(os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)), "app-audio"))
    candidates.append(os.path.join(os.path.dirname(config.PACKAGE_DIR), "vendor", "app-audio"))
    for folder in candidates:
        path = os.path.join(folder, HELPER)
        if os.path.isfile(path):
            return path
    return None


def available():
    """This copy ships the helper, and this Windows can capture one program."""
    build = getattr(sys.getwindowsversion(), "build", 0) if sys.platform == "win32" else 0
    return build >= MIN_WINDOWS_BUILD and helper_path() is not None


def programs_with_sound():
    """Names of the programs that have opened sound right now (from Windows' volume mixer), sorted."""
    try:
        from pycaw.pycaw import AudioUtilities

        names = {session.Process.name() for session in AudioUtilities.GetAllSessions() if session.Process}
    except Exception as e:
        log.info("Could not list the programs playing sound: %s", e)
        return []
    own = os.path.basename(sys.executable).lower()
    return sorted((n for n in names if n.lower() not in (own, "python.exe", "pythonw.exe")), key=str.lower)


def find_root_pid(name):
    """The top process of a program by its file name (e.g. "Discord.exe"), so its helpers count too."""
    wanted = str(name or "").lower()
    if not wanted:
        return None
    matches = []
    for proc in psutil.process_iter(["pid", "name", "ppid"]):
        if (proc.info.get("name") or "").lower() == wanted:
            matches.append(proc.info)
    if not matches:
        return None
    pids = {m["pid"] for m in matches}
    roots = [m for m in matches if m["ppid"] not in pids]
    return (roots or matches)[0]["pid"]


def chosen(cfg):
    """(program, window title, the window's process when it was picked); empty for the whole PC."""
    try:
        window_pid = int(cfg.get("audio_window_pid") or 0)
    except (TypeError, ValueError):
        window_pid = 0
    return str(cfg.get("audio_app") or "").strip(), str(cfg.get("audio_window") or "").strip(), window_pid


def label(app, window=""):
    return f"\u201c{window}\u201d" if window else app


def target_pid(app, window="", window_pid=0):
    """The process to capture: the program copy behind the window, or the program; None if not open."""
    if window:
        pid = app_windows.find_pid(window, app, window_pid)
        return None if pid is None else app_windows.instance_root(pid)
    return find_root_pid(app)


class AppCapture(audio.LoopbackCapture):
    """The same as LoopbackCapture, but fed by app-audio.exe for one program (or one window's program)."""

    def __init__(self, app_name, backlog_seconds=audio.DEFAULT_BACKLOG_SEC, backlog_dir=None, window="",
                 window_pid=0):
        super().__init__("default", backlog_seconds, backlog_dir)
        self.app_name = app_name
        self.window = window
        self.window_pid = window_pid
        self._process = None
        self._reader = None

    def start(self):
        pid = target_pid(self.app_name, self.window, self.window_pid)
        if pid is None:
            raise AppNotRunning(label(self.app_name, self.window))
        path = helper_path()
        self._channels = 2
        self._resampler = soxr.ResampleStream(RATE, audio.SAMPLE_RATE, 1, dtype="float32")
        self._process = subprocess.Popen([path, str(pid)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                         stdin=subprocess.DEVNULL,
                                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.device_name = f"{label(self.app_name, self.window)} only"
        self._reader = threading.Thread(target=self._read, name="app-audio", daemon=True)
        self._reader.start()
        if self._backlog is not None:
            self._spill_stop.clear()
            self._spill_thread = threading.Thread(target=self._spill_worker, name="audio-spill", daemon=True)
            self._spill_thread.start()
        log.info("Listening to %s only (process %s)", label(self.app_name, self.window), pid)

    def _read(self):
        process = self._process
        leftover = b""
        while process is not None:
            data = process.stdout.read1(READ_BYTES) if hasattr(process.stdout, "read1") else process.stdout.read(
                READ_BYTES)
            if not data:
                break
            data = leftover + data
            usable = len(data) // FRAME_BYTES * FRAME_BYTES
            data, leftover = data[:usable], data[usable:]
            if data:
                self._callback(data, usable // FRAME_BYTES, None, None)

    def is_healthy(self):
        return self._process is not None and self._process.poll() is None

    def _release(self, pa):
        process, self._process = self._process, None
        if process is not None:
            try:
                process.kill()
                process.wait(3)
            except Exception:
                log.debug("Stopping app-audio failed", exc_info=True)
            if process.returncode not in (None, 0, 7, 1, -9) and process.stderr is not None:
                log.info("app-audio: %s", process.stderr.read().decode(errors="replace").strip()[:200])
        super()._release(pa)


def make_capture(cfg, on_status=None):
    """The capture to listen with: one program or window if chosen and open, otherwise the whole PC."""
    on_status = on_status or (lambda text: None)
    app, window, window_pid = chosen(cfg)
    name = label(app, window)
    backlog = cfg.get("audio_backlog_sec", audio.DEFAULT_BACKLOG_SEC), cfg.get("audio_backlog_dir", "")
    if (app or window) and available():
        capture = AppCapture(app, *backlog, window=window, window_pid=window_pid)
        try:
            capture.start()
            return capture
        except AppNotRunning:
            on_status(f"The window {name} is not open — listening to everything until it opens" if window
                      else f"{app} is not running — listening to everything until it starts")
        except Exception as e:
            log.warning("Could not listen to %s only: %s", name, e)
            on_status(f"Could not listen to {name} only ({e}) — listening to everything")
        capture.stop()
    capture = audio.LoopbackCapture(cfg["audio_device"], *backlog)
    capture.start()
    capture.waiting_for = (app, window) if (app or window) and available() else None
    return capture


def should_switch(capture, cfg):
    """None to let the usual device checks decide; True/False when one program or window is in play."""
    app, window, window_pid = chosen(cfg)
    if isinstance(capture, AppCapture):
        return False  # its own health check notices the program closing
    waiting = getattr(capture, "waiting_for", None)
    if waiting and waiting == (app, window):
        return target_pid(app, window, window_pid) is not None  # it opened: go back to it
    return None
