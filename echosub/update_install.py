# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Downloading a new EchoSub installer, checking it, and running it — only when the user says so.

The installer is only ever fetched from this project's own GitHub releases, at an address built
here from the version number rather than taken from anything the network sent. It is checked
against the release's published SHA-256 before it runs, and a file that does not match is deleted.
"""
import hashlib
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
from collections import deque

import requests
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QMessageBox, QProgressDialog

from . import APP_NAME, REPOSITORY_URL

log = logging.getLogger(__name__)

CHUNK = 1024 * 1024
TIMEOUT = 30
SPACE_MARGIN = 1.2  # room for the installer and a little more


class UpdateFailed(Exception):
    pass


class UpdateCanceled(Exception):
    pass


def valid_version(version):
    return bool(re.fullmatch(r"\d+(\.\d+){1,3}", str(version or "")))


def asset_urls(version):
    """(installer URL, checksum URL) on the project's own releases; never anything else."""
    if not valid_version(version):
        raise UpdateFailed(f"not a version number: {version!r}")
    name = f"EchoSub-Setup-{version}.exe"
    base = f"{REPOSITORY_URL}/releases/download/v{version}/"
    return base + name, base + name + ".sha256"


def parse_sha256(text):
    """The hash in a .sha256 file ("<64 hex>  name" or just the hash), lower-cased; None if there is none."""
    found = re.search(r"\b[0-9a-fA-F]{64}\b", str(text or ""))
    return found.group(0).lower() if found else None


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def download_folder(chosen=""):
    folder = chosen or os.path.join(tempfile.gettempdir(), "EchoSub-update")
    os.makedirs(folder, exist_ok=True)
    return folder


def download(version, folder, on_progress=None, should_cancel=None, session=None):
    """Fetch and check the installer for `version`; returns its path. Raises UpdateFailed/UpdateCanceled."""
    on_progress = on_progress or (lambda done, total: None)
    should_cancel = should_cancel or (lambda: False)
    session = session or requests.Session()
    url, sha_url = asset_urls(version)
    reply = session.get(sha_url, timeout=TIMEOUT)
    reply.raise_for_status()
    expected = parse_sha256(reply.text)
    if not expected:
        raise UpdateFailed("the release has no checksum to check the installer against")
    path = os.path.join(folder, url.rsplit("/", 1)[1])
    part = path + ".part"
    with session.get(url, stream=True, timeout=TIMEOUT) as reply:
        reply.raise_for_status()
        total = int(reply.headers.get("Content-Length") or 0)
        if total and shutil.disk_usage(folder).free < total * SPACE_MARGIN:
            raise UpdateFailed(f"not enough free space in {folder} (about {total // 2**20} MB is needed)")
        done = 0
        with open(part, "wb") as out:
            for block in reply.iter_content(CHUNK):
                if should_cancel():
                    raise UpdateCanceled()
                out.write(block)
                done += len(block)
                on_progress(done, total)
    if file_sha256(part) != expected:
        os.remove(part)
        raise UpdateFailed("the downloaded installer did not match its published checksum, so it was deleted")
    os.replace(part, path)
    return path


def installer_command(path):
    """Install over the current copy without questions, then start EchoSub again."""
    return [path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", "/RELAUNCH=1"]


class InstallMixin:
    """For the App: "Download and install" on the update message."""

    def install_update(self, update):
        folder = download_folder(self.cfg.get("update_dir", ""))
        answer = QMessageBox.question(
            None, f"{APP_NAME} update",
            f"Download {APP_NAME} {update.version} (about 1 GB) to {folder} and install it?\n\n"
            f"It comes from {APP_NAME}'s own GitHub releases and is checked before it runs. "
            f"{APP_NAME} closes while it installs and starts again afterwards.")
        if answer != QMessageBox.Yes:
            return False
        dialog = QProgressDialog(f"Downloading {APP_NAME} {update.version}…", "Cancel", 0, 100)
        dialog.setWindowTitle(f"{APP_NAME} update")
        dialog.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        events = deque()
        canceled = threading.Event()
        dialog.canceled.connect(canceled.set)

        def work():
            try:
                path = download(update.version, folder, lambda done, total: events.append(("progress", done, total)),
                                canceled.is_set)
                events.append(("done", path, None))
            except UpdateCanceled:
                events.append(("canceled", None, None))
            except Exception as e:
                log.warning("Update download failed: %s", e)
                events.append(("failed", str(e), None))

        timer = QTimer(dialog)  # dies with the dialog, so nothing reaches it once it is gone

        def drain():
            while events:
                kind, a, b = events.popleft()
                if kind == "progress":
                    dialog.setValue(int(100 * a / b) if b else 0)
                    dialog.setLabelText(f"Downloading {APP_NAME} {update.version}… {a // 2**20} of {b // 2**20} MB")
                    continue
                timer.stop()
                dialog.close()
                if kind == "done":
                    self._run_installer(a)
                elif kind == "failed":
                    QMessageBox.warning(None, f"{APP_NAME} update", f"The update was not installed: {a}")

        timer.timeout.connect(drain)
        timer.start(200)
        dialog.show()
        threading.Thread(target=work, name="update-download", daemon=True).start()
        return True

    def _run_installer(self, path):
        log.info("Starting the installer %s", path)
        try:
            subprocess.Popen(installer_command(path), close_fds=True)
        except OSError as e:
            QMessageBox.warning(None, f"{APP_NAME} update", f"The installer could not be started: {e}")
            return
        self._quit()
