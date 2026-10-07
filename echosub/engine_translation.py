# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Translating finished captions and live text, and Arabic diacritics, off the recognition thread.

The recognition loop hands work over and never waits: the translation thread keeps the queue short,
shows the oldest captions untranslated rather than falling minutes behind, and translates only the
newest live text.
"""
import logging
import queue
import threading
import time

from . import downloads, tashkeel, translate

MAX_PENDING_TRANSLATIONS = 6  # captions waiting for translation before the oldest are shown untranslated

log = logging.getLogger(__name__)


class TranslationMixin:
    """The translation and diacritics half of CaptionEngine."""

    # ---- translation ------------------------------------------------------
    def _queue_translation(self, seg_id, text, lang):
        """Queue a caption for translation, keeping the queue short.

        When the translator is slower than the speaker the queue would grow for ever and
        translations would arrive minutes late. The oldest captions are shown with their
        original text instead, which keeps the captions in step with what is being said.
        """
        while self._translations.qsize() >= MAX_PENDING_TRANSLATIONS:
            try:
                old_id, old_text, old_lang = self._translations.get_nowait()
            except queue.Empty:
                break
            log.warning("Translation is behind: showing caption %s untranslated", old_id)
            self.on_translation(old_id, self._diacritize(old_text, old_lang, "translation"))
            now = time.monotonic()
            if now - self._behind_warned > 20:
                self._behind_warned = now
                self.on_status("Translation is behind — showing some captions in their original language")
        self._translations.put((seg_id, text, lang))

    def _clear_pending_partial(self):
        with self._partial_lock:
            self._partial_seq += 1
            self._pending_partial = None

    def _take_pending_partial(self):
        with self._partial_lock:
            pending, self._pending_partial = self._pending_partial, None
            return pending

    def _translation_worker(self):
        while not self._stop.is_set():
            try:
                seg_id, text, lang = self._translations.get(timeout=0.05)
            except queue.Empty:
                self._translate_pending_partial()
                continue
            translated = self._translate(text, lang)
            self.on_translation(seg_id, self._diacritize(translated, self.cfg["target_lang"], "translation"))

    def _translate_pending_partial(self):
        """Translate the newest live text, if finished captions aren't waiting for the translator."""
        pending = self._take_pending_partial()
        if pending is None:
            return
        seq, text, lang, source = pending
        translated = self._translate(text, lang)
        with self._partial_lock:
            current = seq == self._partial_seq
        if current and not self._stop.is_set():
            self.on_partial(text, self._diacritize(translated, self.cfg["target_lang"], "translation"),
                            lang, source)

    def _should_translate(self, lang):
        if isinstance(self.translator, translate.NoTranslator):
            return False
        # Same language: translating still rewrites dialect/casual speech into the standard language
        return lang != self.cfg["target_lang"] or self.cfg["translate_same_language"]

    def translate_text(self, text, lang):
        """Translate one line of text the way a caption would be, for code outside the engine.

        Follows the same settings as captions (including whether to translate at all) and takes the
        same lock, so it can be called from another thread while captions are being translated.
        """
        return self._translate(text, lang)

    def _translate(self, text, lang):
        tgt = self.cfg["target_lang"]
        if not self._should_translate(lang):
            return text
        try:
            with self._translator_lock:
                return self.translator.translate(text, lang, tgt)
        except translate.RateLimited as e:
            log.warning("%s", e)
            self.on_status(f"{e} — showing the original text meanwhile")
            return text
        except Exception as e:
            log.exception("Translation failed")
            message = str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__
            self.on_status(f"Translation error: {message[:140]}")
            return text

    # ---- Arabic diacritics ------------------------------------------------------
    def _prepare_diacritizer(self):
        """Download/load the diacritics model in the background the first time the option is on."""
        if self.cfg.get("arabic_diacritics", "off") == "off" or self.diacritizer or self._diacritizer_loading:
            return
        self._diacritizer_loading = True

        def load():
            self._cancel_download.clear()  # an earlier canceled download must not cancel this one
            try:
                downloader = downloads.ModelDownloader(
                    on_event=self.on_download,
                    should_cancel=lambda: self._cancel_download.is_set() or self._stop.is_set())
                model_dir = downloader.tashkeel()
                self.diacritizer = tashkeel.Diacritizer(model_dir)
                log.info("Arabic diacritics model loaded")
            except downloads.DownloadCanceled:
                self.on_status("Arabic diacritics model download canceled — captions are shown without diacritics")
            except Exception as e:
                log.exception("Arabic diacritics model failed to load")
                self.on_error(f"Could not load the Arabic diacritics model: {e}")
            finally:
                self._diacritizer_loading = False

        threading.Thread(target=load, name="diacritics-loader", daemon=True).start()

    def _diacritize(self, text, lang, *which):
        """Add harakat if the option covers this text (`which`: "original" and/or "translation")."""
        option = self.cfg.get("arabic_diacritics", "off")
        if (not text or self.diacritizer is None or lang not in tashkeel.ARABIC_LANGUAGES
                or not (option == "both" or option in which)):
            return text
        try:
            with self._diacritizer_lock:
                return self.diacritizer.diacritize(text)
        except Exception:
            log.exception("Diacritization failed")
            return text
