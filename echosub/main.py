# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
import ctypes
import logging
import os
import sys
import threading

from . import cuda_setup, logging_setup

cuda_setup.setup()
LOG_PATH = logging_setup.setup()

from PySide6.QtCore import QObject, QTimer, Signal  # noqa: E402
from PySide6.QtGui import QColor, QIcon, QPainter  # noqa: E402
from PySide6.QtNetwork import QLocalServer, QLocalSocket  # noqa: E402
from PySide6.QtWidgets import QApplication, QSystemTrayIcon  # noqa: E402

from . import APP_NAME, AUTHOR, __version__, config, history, hotkeys, transcript_fixes  # noqa: E402
from .overlay import CaptionOverlay  # noqa: E402
from .tray_menu import TrayMenuMixin  # noqa: E402
from .update_ui import UpdateCheckMixin  # noqa: E402
from .voice_command_ui import VoiceCommandMixin  # noqa: E402
from .settings_dialog import SettingsDialog  # noqa: E402

log = logging.getLogger("echosub")

INSTANCE_KEY = "EchoSub-single-instance"
MUTEX_NAME = "EchoSubAppMutex"  # the installer checks it to ask the user to close EchoSub first

STATE_COLORS = {
    "loading": "#F9A825",     # amber
    "listening": "#1E88E5",   # blue
    "paused": "#757575",      # grey
    "recovering": "#F9A825",
    "error": "#E53935",       # red
    "canceled": "#757575",
    "downloading": "#F9A825",
}
STATE_LABELS = {
    "loading": "loading models",
    "listening": "listening",
    "paused": "paused",
    "recovering": "reconnecting audio",
    "error": "error",
    "canceled": "model download canceled",
    "downloading": "downloading models",
}


class Bridge(QObject):
    """Carries engine callbacks (worker threads) to the Qt main thread."""
    partial = Signal(int, str, str, str, str)
    final = Signal(int, int, str, object, str, int, str)
    translation = Signal(int, int, str)
    activity = Signal(int)
    status = Signal(int, str)
    error = Signal(int, str)
    state = Signal(int, str)
    download = Signal(int, object)
    update_result = Signal(object, bool)


def app_icon():
    return QIcon(os.path.join(config.ASSETS_DIR, "echosub.ico"))


def make_icon(color):
    """App icon with a status dot (loading / listening / paused / error) for the tray."""
    pm = app_icon().pixmap(64, 64)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QColor(15, 23, 42))
    p.setBrush(QColor(color))
    p.drawEllipse(40, 40, 22, 22)
    p.end()
    return QIcon(pm)


class App(TrayMenuMixin, UpdateCheckMixin, VoiceCommandMixin):
    def __init__(self, qt):
        self.qt = qt
        self.qt.setQuitOnLastWindowClosed(False)
        self.cfg = config.load()
        self.engine = None
        self.generation = 0
        self.engine_state = "loading"
        self.history = history.History()
        self.history.save_to_file = self.cfg["save_transcripts"]
        self.history_window = None
        self.settings_dialog = None
        self._placement_override = None  # box moved by hand while Settings was open
        self.hotkeys = hotkeys.GlobalHotkeys()

        self.save_timer = QTimer()
        self.save_timer.setSingleShot(True)
        self.save_timer.timeout.connect(lambda: config.save(self.cfg))

        self.bridge = Bridge()
        self.bridge.partial.connect(self._on_partial)
        self.bridge.final.connect(self._on_final)
        self.bridge.translation.connect(self._on_translation)
        self.bridge.status.connect(self._on_status)
        self.bridge.error.connect(self._on_error)
        self.bridge.activity.connect(self._on_activity)
        self.bridge.state.connect(self._on_state)
        self.bridge.download.connect(self._on_download)
        self.bridge.update_result.connect(self._on_update_result)
        self.download_dialog = None
        self._update_check_running = False
        self._voice_runner = None

        self.overlay = CaptionOverlay(self.cfg, self._show_menu_at, self._geometry_changed,
                                      self._placement_changed, self._raise_app_windows)
        self.menu = self._build_menu()
        self.tray = QSystemTrayIcon(make_icon(STATE_COLORS["loading"]))
        self.tray.setToolTip(APP_NAME)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.messageClicked.connect(self._notice_clicked)
        self.reminder_timer = QTimer()
        self.reminder_timer.timeout.connect(self.check_reminders)
        self.reminder_timer.start(10_000)  # a reminder is never more than ten seconds late
        self.check_reminders()  # anything that fell due while EchoSub was closed
        self.tray.show()
        self._apply_hotkeys()
        self._start_engine()
        self._schedule_update_check()

    # ---- menu --------------------------------------------------------------
    def _apply_hotkeys(self):
        if not self.cfg["global_hotkeys"]:
            self.hotkeys.disable()
            return
        failed = self.hotkeys.enable(self.qt, {
            "toggle_captions": self.act_show.toggle,
            "pause": self.act_pause.toggle,
            "lock": self.act_lock.toggle,
        })
        if failed:
            self.tray.showMessage(APP_NAME, "These hotkeys are used by another program: " + ", ".join(failed),
                                  QSystemTrayIcon.Warning, 5000)

    def _show_menu_at(self, pos):
        self.menu.popup(pos)

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self._open_settings()
        elif reason == QSystemTrayIcon.Trigger:
            self.act_show.setChecked(not self.cfg["overlay_enabled"])

    def _set_overlay_enabled(self, enabled):
        self.cfg["overlay_enabled"] = enabled
        self.overlay.refresh()
        self._save()

    def _set_lock(self, locked):
        self.overlay.set_click_through(locked)
        self._save()
        if locked:
            unlock = f"press {hotkeys.label('lock')} or use" if self.cfg["global_hotkeys"] else "use"
            self.tray.showMessage(APP_NAME, f"Caption window locked. To unlock, {unlock} the {APP_NAME} tray icon.",
                                  QSystemTrayIcon.Information, 3000)

    def _set_light_mode(self, enabled):
        if enabled != self.cfg.get("light_mode", False):
            self._apply({"light_mode": enabled})  # an engine setting: reloads the speech model

    def _set_paused(self, paused):
        self._paused = paused
        if self.engine:
            self.engine.paused = paused
        self.overlay.clear()
        self.overlay.set_status("Paused" if paused else "", 0 if paused else 1)
        self._update_tray()

    def _open_settings(self, add_phrase=None):
        # Menu actions pass their checked state, which is not a phrase.
        add_phrase = add_phrase if isinstance(add_phrase, str) else None
        if self.settings_dialog is not None:
            self.settings_dialog.raise_()
            self.settings_dialog.activateWindow()
            return
        backup = dict(self.cfg)
        dlg = SettingsDialog(self.cfg, add_phrase=add_phrase)
        self.settings_dialog = dlg
        self._placement_override = None

        def preview(values):
            # Display-only preview; engine settings are applied on save
            self.cfg.update({k: v for k, v in values.items() if k not in config.ENGINE_KEYS})
            self.overlay.refresh()

        dlg.preview.connect(preview)
        was_positioning = self.overlay.positioning
        self.overlay.set_positioning(True)
        accepted = dlg.exec()
        self.settings_dialog = None
        self.cfg.clear()
        self.cfg.update(backup)
        if self._placement_override:
            self.cfg.update(self._placement_override)  # keep where the box was dragged during preview
        self.overlay.set_positioning(was_positioning)
        if accepted and dlg.restore_requested:
            defaults = {k: v for k, v in config.DEFAULTS.items() if k not in config.KEEP_ON_RESET}
            self._apply(defaults)
            QTimer.singleShot(0, self._open_settings)
        elif accepted:
            self._apply(dlg.values())
        else:
            self.overlay.refresh()

    def _apply(self, values):
        restart = any(values.get(k, self.cfg[k]) != self.cfg[k] for k in config.ENGINE_KEYS)
        hotkeys_changed = values.get("global_hotkeys", self.cfg["global_hotkeys"]) != self.cfg["global_hotkeys"]
        self.cfg.update(values)
        self._save()
        self.history.save_to_file = self.cfg["save_transcripts"]
        self.act_light.setChecked(self.cfg.get("light_mode", False))
        if self.cfg["target_lang"] in self.lang_actions:
            self.lang_actions[self.cfg["target_lang"]].setChecked(True)
        if hotkeys_changed:
            self._apply_hotkeys()
            self._update_hotkey_labels()
        self.overlay.entries = self.overlay.entries[-self.cfg["max_lines"]:]
        self.overlay.refresh()
        if restart:
            self._start_engine()
        elif self.engine:
            self.engine.update_live_settings(self.cfg)

    def _raise_app_windows(self):
        """Settings and history stay above the caption box, which re-shows itself on top as captions come and go."""
        for window in (self.settings_dialog, self.history_window, getattr(self, "about_dialog", None),
                       getattr(self, "download_dialog", None)):
            if window is not None and window.isVisible():
                window.raise_()

    def _open_history(self):
        if self.history_window is None or not self.history_window.isVisible():
            self.history_window = history.HistoryWindow(self.history, self.cfg)
        self.history_window.show()
        self.history_window.raise_()
        self.history_window.activateWindow()

    def _open_log(self):
        os.startfile(LOG_PATH)

    def _open_about(self):
        from .about import AboutDialog

        if getattr(self, "about_dialog", None) is not None and self.about_dialog.isVisible():
            self.about_dialog.raise_()
            self.about_dialog.activateWindow()
            return
        self.about_dialog = AboutDialog()
        self.about_dialog.show()

    def _geometry_changed(self, geo):
        self.cfg["geometry"] = geo
        self._save()

    def _placement_changed(self):
        """The caption box was dragged, resized or zoomed (Shift + wheel) by hand."""
        keys = ("geometry", "box_position", "box_screen", "box_width_pct", "box_scale")
        if self.settings_dialog is not None:
            self._placement_override = {k: self.cfg.get(k) for k in keys}
            self.settings_dialog.sync_placement(self.cfg)
        self._save()

    def _save(self):
        self.save_timer.start(800)

    # ---- engine ------------------------------------------------------------
    def _start_engine(self):
        from .engine import CaptionEngine

        self.history.flush_pending()
        self.generation += 1
        gen = self.generation
        old = self.engine
        b = self.bridge
        self.engine = CaptionEngine(
            self.cfg,
            on_partial=lambda text, tr, lang, src="system": b.partial.emit(gen, text, tr or "", lang, src),
            on_final=lambda sid, text, tr, lang, spk, src="system": b.final.emit(
                gen, sid, text, tr, lang, -1 if spk is None else spk, src),
            on_translation=lambda sid, t: b.translation.emit(gen, sid, t),
            on_status=lambda s: b.status.emit(gen, s),
            on_error=lambda s: b.error.emit(gen, s),
            on_activity=lambda: b.activity.emit(gen),
            on_state=lambda s: b.state.emit(gen, s),
            on_download=lambda event: b.download.emit(gen, event),
        )
        self.engine.paused = self.act_pause.isChecked()
        new = self.engine
        self.overlay.clear()
        self.overlay.set_status("Starting…")

        def swap():
            if old is not None:
                old.stop()
            new.start()

        threading.Thread(target=swap, name="engine-swap", daemon=True).start()

    def _on_partial(self, gen, original, translated, lang, source="system"):
        if gen == self.generation:
            self.heard_a_refusal(original)  # "no" should stop a countdown without waiting
        if gen == self.generation and not (source == "mic" and self.mic_muted()):
            self.overlay.set_partial(original, translated or None, lang, source)

    def _on_final(self, gen, seg_id, original, translated, lang, speaker, source="system"):
        if gen != self.generation:
            return
        original = transcript_fixes.apply_fixes(original, self.cfg.get("transcript_fixes"))
        translated = transcript_fixes.apply_fixes(translated, self.cfg.get("transcript_fixes"))
        if not (source == "mic" and self.mic_muted()):
            spk = None if speaker < 0 else speaker
            self.overlay.add_final(seg_id, original, translated, lang, spk, source)
            self.history.add((gen, seg_id), original, translated, lang, spk)
            self._report_alerts(original)
        # Still offered to the commands, so a muted microphone can hear itself being unmuted.
        self._handle_voice_command(original, source)

    def _report_alerts(self, text):
        """Say so when a caption contains one of the words being watched for."""
        words = transcript_fixes.alerts_in(text, self.cfg.get("alert_words"))
        if not words or not self.cfg.get("alert_sound", True):
            return
        message = "Heard: " + ", ".join(words) + "\n" + text[:120]
        self.tray.showMessage(APP_NAME, message, QSystemTrayIcon.Information, 5000)

    def _on_translation(self, gen, seg_id, translated):
        if gen == self.generation:
            self.overlay.set_translation(seg_id, translated)
            self.history.set_translation((gen, seg_id), translated)

    def _on_activity(self, gen):
        if gen == self.generation:
            self.overlay.speech_activity()

    def _on_state(self, gen, state):
        if gen == self.generation:
            self.engine_state = state
            self._update_tray()

    def _on_download(self, gen, event):
        if gen != self.generation:
            return
        from .download_dialog import DownloadDialog, percent, summary

        if self.download_dialog is None:
            self.download_dialog = DownloadDialog()
            self.download_dialog.cancel_requested.connect(lambda: self.engine and self.engine.cancel_download())
            self.download_dialog.retry_requested.connect(self._start_engine)
        self.download_dialog.update_event(event)
        state = event["state"]
        if state in ("start", "progress"):
            self.engine_state = "downloading"
            text = f"Downloading {event['title'].lower()}: {percent(event)} % — {summary(event)}"
            self.overlay.set_status(text)
            self._update_tray(text)
        elif state == "failed":
            self.engine_state = "error"
            self._update_tray(f"Download failed: {event.get('error', '')}")

    def _update_tray(self, detail=None):
        state = "paused" if self.act_pause.isChecked() and self.engine_state == "listening" else self.engine_state
        self.tray.setIcon(make_icon(STATE_COLORS[state]))
        text = f"{APP_NAME} — {STATE_LABELS[state]}"
        if detail:
            text += f"\n{detail}"
        self.tray.setToolTip(text[:120])

    def _on_status(self, gen, text):
        if gen != self.generation:
            return
        log.info("Status: %s", text)
        transient = text.startswith(("Ready", "Switched", "Recovered", "Translation error", "Google Translate"))
        self.overlay.set_status(text, 4000 if transient else 0)
        self._update_tray(text)

    def _on_error(self, gen, text):
        if gen != self.generation:
            return
        log.error("Error shown to user: %s", text)
        self.overlay.set_status("Error: " + text)
        self.tray.showMessage(APP_NAME, text, QSystemTrayIcon.Critical, 6000)

    def activate_from_second_instance(self):
        self.tray.showMessage(APP_NAME, f"{APP_NAME} is already running — opening Settings.",
                              QSystemTrayIcon.Information, 2500)
        self._open_settings()

    def _quit(self):
        config.save(self.cfg)
        self.history.flush_pending()
        self.hotkeys.disable()
        self.tray.hide()
        if self.engine:
            threading.Thread(target=self.engine.stop, daemon=True).start()
        QTimer.singleShot(300, self.qt.quit)

    def run(self):
        return self.qt.exec()


def claim_single_instance(qt):
    """Returns a QLocalServer if this is the only running copy, else pings the running copy and returns None."""
    probe = QLocalSocket()
    probe.connectToServer(INSTANCE_KEY)
    if probe.waitForConnected(300):
        probe.write(b"activate")
        probe.waitForBytesWritten(300)
        probe.disconnectFromServer()
        return None
    QLocalServer.removeServer(INSTANCE_KEY)  # stale socket left by a crash
    server = QLocalServer(qt)
    server.listen(INSTANCE_KEY)
    return server


def main():
    if "--self-test" in sys.argv:
        from . import selftest

        args = sys.argv[sys.argv.index("--self-test") + 1:]
        return selftest.run(args[0] if args else None)
    if sys.platform == "win32":
        # Own taskbar identity (not "python.exe") and a mutex the installer can detect
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"{APP_NAME}.{__version__}")
        main.mutex = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    qt = QApplication(sys.argv)
    qt.setApplicationName(APP_NAME)
    qt.setApplicationVersion(__version__)
    qt.setOrganizationName(AUTHOR)
    qt.setWindowIcon(app_icon())
    server = claim_single_instance(qt)
    if server is None:
        log.info("Another instance is already running; asked it to open Settings")
        return 0
    log.info("%s %s starting (data: %s)", APP_NAME, __version__, config.DATA_DIR)
    app = App(qt)

    def on_connection():
        conn = server.nextPendingConnection()

        def on_ready_read():
            conn.readAll()
            app.activate_from_second_instance()

        conn.readyRead.connect(on_ready_read)

    server.newConnection.connect(on_connection)
    code = app.run()
    log.info("%s exited", APP_NAME)
    return code


if __name__ == "__main__":
    sys.exit(main())
