# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Telling the user about a new EchoSub release. Installing it happens only when they choose to."""
import logging
import threading
import time

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox, QSystemTrayIcon

from . import APP_NAME, __version__, config, updates
from .update_install import InstallMixin

log = logging.getLogger("echosub")

CHECK_INTERVAL_SEC = 24 * 60 * 60
FIRST_CHECK_DELAY_MS = 7000  # let the caption engine finish starting first


def is_due(last_check, now=None, interval=CHECK_INTERVAL_SEC):
    """True when the daily check should run again (also right after a clock change)."""
    now = time.time() if now is None else now
    try:
        last = float(last_check or 0)
    except (TypeError, ValueError):
        return True  # a settings file written by hand: check rather than never check again
    if last <= 0:
        return True  # never checked
    return not 0 <= now - last < interval  # a clock set backwards must not block checks for ever


class UpdateCheckMixin(InstallMixin):
    """Adds the update check to the tray app.

    Only the installed build checks, once a day, on its own thread; the user is shown a message
    with a button that opens the official installer's page. Nothing is ever downloaded or run.
    """

    def _schedule_update_check(self):
        if config.FROZEN and self.cfg.get("update_checks", True) and is_due(self.cfg.get("last_update_check", 0)):
            QTimer.singleShot(FIRST_CHECK_DELAY_MS, self._check_updates_async)

    def _check_updates_async(self, manual=False):
        if self._update_check_running:
            return
        self._update_check_running = True

        def worker():
            try:
                payload = (updates.check(__version__), None)
            except Exception as e:
                log.info("Update check failed: %s", e)
                payload = (None, str(e))
            self.bridge.update_result.emit(payload, manual)

        threading.Thread(target=worker, name="update-check", daemon=True).start()

    def _on_update_result(self, payload, manual):
        self._update_check_running = False
        update, error = payload
        self.cfg["last_update_check"] = int(time.time())
        self._save()
        if error:
            if manual:
                self.tray.showMessage(APP_NAME, "Could not check for updates. Check your internet connection.",
                                      QSystemTrayIcon.Warning, 5000)
            return
        if update is None:
            if manual:
                self.tray.showMessage(APP_NAME, "You already have the latest version.",
                                      QSystemTrayIcon.Information, 4000)
            return
        self._show_update_message(update)

    def _show_update_message(self, update):
        box = QMessageBox()
        box.setWindowTitle(f"{APP_NAME} update available")
        box.setText(f"{APP_NAME} {update.version} is available. You have {__version__}.")
        offer_install = bool(self.cfg.get("update_install", True)) and config.FROZEN
        box.setInformativeText(f"{APP_NAME} never installs anything by itself."
                               + (" Download and install fetches the official installer, checks it, and runs it."
                                  if offer_install else
                                  " The button below opens the official installer's download page in your browser."))
        install = box.addButton("Download and install", QMessageBox.AcceptRole) if offer_install else None
        download = box.addButton("Open download page", QMessageBox.ActionRole)
        box.addButton("Later", QMessageBox.RejectRole)
        box.exec()
        if install is not None and box.clickedButton() is install:
            self.install_update(update)
        elif box.clickedButton() is download:
            QDesktopServices.openUrl(QUrl(update.download_url))
