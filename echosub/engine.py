# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Audio -> VAD segmentation -> speaker id -> Whisper -> translation, on worker threads.

The recognition loop never waits for translation: a final caption is emitted with its original
text right away, and a separate translation thread fills in the translated text afterwards.
"""
import itertools
import logging
import queue
import threading
import time

import numpy as np
from faster_whisper.vad import VadOptions, get_speech_timestamps

from . import asr, audio, downloads, languages, speaker, translate  # noqa: F401
from . import segmentation
from .engine_sources import MICROPHONE, SYSTEM, AudioStream
from .engine_translation import MAX_PENDING_TRANSLATIONS, TranslationMixin
from .transcript_quality import is_unreliable_live_text

SR = audio.SAMPLE_RATE
PROMPT_MAX_AGE_SEC = 10.0   # previous sentence is used as Whisper context only if this recent
PROMPT_MAX_CHARS = 200
CHARS_PER_SEC = 15.0        # rough speaking rate, used to spot Whisper repeating its context
HEALTH_CHECK_SEC = 2.0
RECONNECT_MAX_DELAY_SEC = 5  # a card that is unplugged and plugged back in should be picked up quickly
VAD_INTERVAL_SEC = 0.15     # how often speech detection may rerun; it costs more the longer the buffer
VAD_MAX_INTERVAL_SEC = 0.5  # ...and the longest it may wait, so a long buffer isn't scanned constantly
LIGHT_WHISPER_MODEL = "small"  # light mode uses this instead of a large model
HEAVY_WHISPER_MODELS = ("large-v3", "large-v3-turbo", "medium")

log = logging.getLogger(__name__)


class AudioStreamLost(RuntimeError):
    pass


def effective_whisper_model(cfg):
    """The speech model actually used: light mode swaps a heavy model for a faster one."""
    model = cfg["whisper_model"]
    if cfg.get("light_mode") and model in HEAVY_WHISPER_MODELS:
        return LIGHT_WHISPER_MODEL
    return model


class CaptionEngine(TranslationMixin):
    def __init__(self, cfg, on_partial, on_final, on_status, on_error, on_activity=None,
                 on_translation=None, on_state=None, on_download=None):
        """Callbacks (all called from worker threads):

        on_partial(original, translated_or_None, lang)
        on_final(segment_id, original, translated_or_None, lang, speaker_id_or_None)
            translated is None while the translation is still being computed
        on_translation(segment_id, translated)
        on_state(state) with state in "loading" | "listening" | "recovering" | "error" | "canceled"
        on_download(event) model download progress, see downloads.ModelDownloader
        """
        self.cfg = dict(cfg)
        self.on_partial = on_partial
        self.on_final = on_final
        self.on_status = on_status
        self.on_error = on_error
        self.on_activity = on_activity or (lambda: None)
        self.on_translation = on_translation or (lambda seg_id, text: None)
        self.on_state = on_state or (lambda state: None)
        self.on_download = on_download or (lambda event: None)
        self._cancel_download = threading.Event()
        self.diacritizer = None
        self._diacritizer_lock = threading.Lock()
        self._diacritizer_loading = False
        self.speakers = None
        self.translator = translate.NoTranslator()
        self.paused = False
        self._stop = threading.Event()
        self._thread = None
        self._translation_thread = None
        self._translations = queue.Queue()
        self._translator_lock = threading.Lock()
        self._capture = None
        self._mic_capture = None
        self._ids = itertools.count(1)
        self._sticky_lang = None
        self._sticky_time = 0.0
        self._asr_time = 0.0  # moving average of seconds per Whisper call
        self._last_text = ""
        self._last_lang = None
        self._last_time = 0.0
        self._last_speaker = None
        self._partial_lock = threading.Lock()
        self._pending_partial = None  # newest live text waiting to be translated: (seq, text, lang)
        self._partial_seq = 0         # bumped for every new live text, so stale translations are dropped
        self._behind_warned = 0.0     # last time the user was told captions are behind

    # ---- public -----------------------------------------------------------
    def start(self):
        self._thread = threading.Thread(target=self._run, name="caption-engine", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        for t in (self._thread, self._translation_thread):
            if t is not None:
                t.join(timeout=10)

    def cancel_download(self):
        self._cancel_download.set()

    def update_live_settings(self, cfg):
        """Settings that take effect without reloading models."""
        self.cfg.update(cfg)
        self._prepare_diacritizer()
        if self.speakers is not None:
            self.speakers.threshold = cfg.get("speaker_threshold", self.speakers.threshold)

    def whisper_model(self):
        return effective_whisper_model(self.cfg)

    def _live_text_enabled(self):
        return self.cfg["show_partial"] and not self.cfg.get("light_mode")

    # ---- lifecycle --------------------------------------------------------
    def _run(self):
        self.on_state("loading")
        try:
            self._load()
        except downloads.DownloadCanceled:
            if self._stop.is_set():
                return
            self.on_state("canceled")
            self.on_status("Model download canceled — choose Retry, or Restart engine from the menu, to continue")
            return
        except Exception as e:
            log.exception("Engine failed to load")
            self.on_state("error")
            self.on_error(f"{type(e).__name__}: {e}")
            return
        if self._stop.is_set():
            return

        self._translation_thread = threading.Thread(
            target=self._translation_worker, name="caption-translation", daemon=True)
        self._translation_thread.start()
        self._prepare_diacritizer()

        failures = 0
        while not self._stop.is_set():
            try:
                if self._capture is None:
                    self._open_capture()
                    if failures:
                        self.on_status(f"Recovered — listening to: {self._capture.device_name}")
                    failures = 0
                self.on_state("listening")
                self._loop()
            except Exception as e:
                failures += 1
                if isinstance(e, AudioStreamLost):
                    log.warning("Audio stream lost: %s", e)
                else:
                    log.exception("Engine loop failed")
                self._close_capture()
                delay = min(RECONNECT_MAX_DELAY_SEC, 2 ** min(failures, 2))
                self.on_state("recovering")
                self.on_status(f"Sound device problem — reconnecting in {delay} s… ({e})")
                self._stop.wait(delay)
        self._close_capture()

    def _load(self):
        cfg = self.cfg
        downloader = downloads.ModelDownloader(
            on_event=self.on_download,
            should_cancel=lambda: self._cancel_download.is_set() or self._stop.is_set())
        model = self.whisper_model()
        self.on_status(f"Loading speech recognition model ({model})…")
        whisper_path = downloader.whisper(model)
        try:
            self.asr = asr.Transcriber(whisper_path, cfg["device"])
        except Exception as e:
            if cfg["device"] != "cuda":
                raise
            log.exception("GPU load failed, falling back to CPU")
            self.on_status(f"Could not use the GPU ({e}) — switching to CPU")
            self.asr = asr.Transcriber(whisper_path, "cpu")
        log.info("Whisper %s on %s/%s", model, self.asr.device, self.asr.compute_type)

        if cfg["translator"] != "none":
            self.on_status("Loading translation model…")
        try:
            self.translator = translate.create(cfg["translator"], self.asr.device, downloader)
            if hasattr(self.translator, "notify"):
                self.translator.notify = self.on_status
        except downloads.DownloadCanceled:
            raise
        except Exception as e:
            log.exception("Translator failed to load")
            self.on_error(f"Could not load the translator: {e}")
            self.translator = translate.NoTranslator()

        if cfg["speaker_detection"]:
            self.on_status("Loading speaker detection model…")
            try:
                self.speakers = speaker.SpeakerTracker(cfg["speaker_threshold"], downloader.speaker())
            except downloads.DownloadCanceled:
                raise
            except Exception as e:
                log.exception("Speaker detection failed to load")
                self.on_error(f"Could not load speaker detection: {e}")

    def _open_microphone(self):
        """Open the microphone, if the user turned it on. Its failure never stops the captions."""
        self._close_microphone()
        if not self.cfg.get("mic_enabled", False):
            return
        try:
            self._mic_capture = audio.LoopbackCapture(
                self.cfg.get("mic_device", "default"), self.cfg.get("audio_backlog_sec", audio.DEFAULT_BACKLOG_SEC),
                self.cfg.get("audio_backlog_dir", ""), kind="input")
            self._mic_capture.start()
            log.info("Listening to the microphone: %s", self._mic_capture.device_name)
        except Exception as e:
            self._mic_capture = None
            log.warning("Microphone could not be opened: %s", e)
            self.on_status(f"The microphone could not be opened ({e}) — captions continue without it")

    def _close_microphone(self):
        if self._mic_capture is not None:
            try:
                self._mic_capture.stop()
            except Exception:
                log.exception("Closing the microphone failed")
            self._mic_capture = None

    def _open_capture(self):
        self._capture = audio.LoopbackCapture(
            self.cfg["audio_device"], self.cfg.get("audio_backlog_sec", audio.DEFAULT_BACKLOG_SEC),
            self.cfg.get("audio_backlog_dir", ""))
        try:
            self._capture.start()
        except Exception:
            self._capture = None
            raise
        self._open_microphone()
        log.info("Listening to %s", self._capture.device_name)
        backlog = self._capture.backlog
        if backlog is not None and backlog.using_fallback:
            self.on_status(f"Cannot write the catch-up buffer to '{self.cfg.get('audio_backlog_dir')}' — "
                           f"using {backlog.directory} instead")
        if self._capture.using_fallback:
            self.on_status(f"'{self.cfg['audio_device']}' is not connected — listening to "
                           f"{self._capture.device_name} until it comes back")
            return
        self.on_status(
            f"Ready — listening to: {self._capture.device_name} "
            f"[{self.asr.device.upper()} / {self.asr.compute_type}]"
        )

    def _close_capture(self):
        self._close_microphone()
        if self._capture is not None:
            try:
                self._capture.stop()
            except Exception:
                log.exception("Closing audio stream failed")
            self._capture = None

    # ---- recognition loop -------------------------------------------------
    def _vad(self, buf):
        opts = VadOptions(
            threshold=self.cfg["vad_threshold"],
            min_speech_duration_ms=200,
            min_silence_duration_ms=int(self.cfg["silence_sec"] * 1000 * 0.6),
            speech_pad_ms=100,
        )
        return get_speech_timestamps(buf, vad_options=opts, sampling_rate=SR)

    def _loop(self):
        streams = [AudioStream(self, self._capture, SYSTEM)]
        if self._mic_capture is not None:
            streams.append(AudioStream(self, self._mic_capture, MICROPHONE))
        last_device_check = last_health_check = time.monotonic()

        while not self._stop.is_set():
            for stream in streams:
                stream.pull()
            if self.paused:
                for stream in streams:
                    stream.clear()
                self._clear_pending_partial()
                time.sleep(0.1)
                continue

            now = time.monotonic()
            if now - last_health_check > HEALTH_CHECK_SEC:
                last_health_check = now
                if not self._capture.is_healthy():
                    raise AudioStreamLost(f"stream on '{self._capture.device_name}' stopped")
                if self._mic_capture is not None and not self._mic_capture.is_healthy():
                    self.on_status("The microphone stopped — reconnecting…")
                    self._open_microphone()
                    streams = [s for s in streams if s.name != MICROPHONE]
                    if self._mic_capture is not None:
                        streams.append(AudioStream(self, self._mic_capture, MICROPHONE))
            if now - last_device_check > 4:
                last_device_check = now
                if self._should_switch_device():
                    self._close_capture()
                    self._open_capture()
                    self.on_status(f"Switched audio device to: {self._capture.device_name}")
                    return  # the loop restarts with the new device

            for stream in streams:
                if stream.dropped() >= 1 and now - self._behind_warned > 20:
                    self._behind_warned = now
                    self.on_status("Captions are behind — the catch-up buffer is full and some audio was "
                                   "skipped (try Light mode or a smaller speech model)")

            if not any(stream.step(now) for stream in streams):
                time.sleep(0.05)

    @staticmethod
    def _take_audio(cap, room_seconds):
        """Fetch only as much waiting audio as the engine's buffer has room for."""
        return cap.take(room_seconds) if room_seconds > 0 else []

    @staticmethod
    def _vad_interval(samples):
        """Speech detection costs about 5 ms per second of buffer, so scan long buffers less often."""
        return min(VAD_MAX_INTERVAL_SEC, max(VAD_INTERVAL_SEC, 0.02 * samples / SR))

    @staticmethod
    def _best_cut(speech, length, start):
        """Cut a too-long utterance at the widest pause in its later half."""
        best, best_gap = length, 0
        for a, b in zip(speech, speech[1:]):
            if a["end"] - start < SR * 3:
                continue
            gap = b["start"] - a["end"]
            if gap >= best_gap:
                best, best_gap = (a["end"] + b["start"]) // 2, gap
        return best

    def _transcribe(self, seg, language, final, prompt=None):
        t = time.monotonic()
        result = self.asr.transcribe(seg, language=language, final=final, prompt=prompt)
        elapsed = time.monotonic() - t
        self._asr_time = elapsed if not self._asr_time else 0.7 * self._asr_time + 0.3 * elapsed
        return result

    def _language_hint(self):
        src = self.cfg["source_lang"]
        if src != "auto":
            return languages.whisper_code(src)
        if self._sticky_lang and time.monotonic() - self._sticky_time < 20:
            return self._sticky_lang
        return None

    def _context_prompt(self, spk, lang=None):
        """The previous sentence, if it was recent and said by the same voice.

        A prompt in another alphabet makes Whisper write this segment in that alphabet too
        (English spelled out in Russian letters, for example), so it is only used for the
        language it belongs to.
        """
        if (self._last_text and time.monotonic() - self._last_time < PROMPT_MAX_AGE_SEC
                and (spk is None or spk == self._last_speaker)
                and (lang is None or self._last_lang == lang or languages.fits_script(self._last_text, lang))):
            return self._last_text[-PROMPT_MAX_CHARS:]
        return None

    def _partial(self, seg, source=SYSTEM):
        text, lang, prob, _ = self._transcribe(seg, self._language_hint(), False)
        if text and not languages.fits_script(text, lang):
            return  # wrong alphabet: wait for the final transcript, which repairs itself
        if not text or is_unreliable_live_text(text, len(seg) / SR, prob):
            return  # live text is never trusted as much as the finished caption
        if self.cfg["source_lang"] != "auto":
            lang = self.cfg["source_lang"]
        self.on_partial(text, None, lang, source)
        # The translation of live text is done on the translation thread; the recognition loop
        # must never wait for it. Only the newest live text is translated, older ones are dropped.
        if self.translator.streaming and self._should_translate(lang):
            with self._partial_lock:
                self._partial_seq += 1
                self._pending_partial = (self._partial_seq, text, lang, source)

    def _finalize(self, seg, speech, offset, source=SYSTEM):
        if len(seg) < SR * 0.3:
            return
        self._clear_pending_partial()  # the live text is replaced by the caption(s) below
        regions = [(max(0, r["start"] - offset), min(len(seg), r["end"] - offset)) for r in speech]
        regions = [(a, b) for a, b in regions if b - a > 0]
        if source == MICROPHONE:
            # It is the person at this PC talking, so there is nobody to tell apart.
            self._finalize_one(seg, None, source)
            return
        for a, b, spk in self._speaker_runs(seg, regions):
            self._finalize_one(seg[a:b], spk, source)

    def _speaker_runs(self, seg, regions):
        return segmentation.speaker_runs(self.speakers, seg, regions)

    def _finalize_one(self, seg, spk, source=SYSTEM):
        if len(seg) < SR * 0.3:
            return
        src = self.cfg["source_lang"]
        forced = languages.whisper_code(src) if src != "auto" else None
        prompt = self._context_prompt(spk, forced or self._sticky_lang)
        text, lang, prob, probs = self._transcribe(seg, forced, True, prompt)
        if text and prompt and not languages.fits_script(text, lang):
            # The context sentence dragged this one into another alphabet: transcribe it on its own
            log.info("Transcript in the wrong alphabet for %s, retrying without context", lang)
            self._last_text = ""
            prompt = None
            text, lang, prob, probs = self._transcribe(seg, forced, True, None)
        if forced is not None:
            lang = src  # e.g. Darija: recognized as Arabic, translated from Moroccan Arabic

        if forced is None:
            # Short clips are often mis-detected; prefer the recent language if plausible
            sticky = self._sticky_lang
            if sticky and lang != sticky and prob < 0.6 and time.monotonic() - self._sticky_time < 30:
                sticky_prob = dict(probs or []).get(sticky, 0.0)
                if sticky_prob > 0.1:
                    text, lang, prob, _ = self._transcribe(seg, sticky, True, prompt)
            if prob >= 0.6 or not self._sticky_lang:
                self._sticky_lang = lang
            if lang == self._sticky_lang:
                self._sticky_time = time.monotonic()

        if (prompt and text.strip().lower() == prompt.strip().lower()
                and len(seg) / SR < 0.5 * len(text) / CHARS_PER_SEC):
            text = ""  # too little audio for that sentence: Whisper echoed its context
        if text and not languages.fits_script(text, lang):
            log.info("Dropping a transcript written in the wrong alphabet for %s: %r", lang, text[:60])
            text = ""
            self._last_text, self._sticky_lang = "", None
        if not text:
            self._clear_pending_partial()
            self.on_partial("", "", lang, source)
            return

        self._last_text, self._last_lang, self._last_time, self._last_speaker = text, lang, time.monotonic(), spk
        seg_id = next(self._ids)
        if not self._should_translate(lang):
            shown = self._diacritize(text, lang, "original", "translation")
            self.on_final(seg_id, shown, shown, lang, spk, source)
        else:
            self.on_final(seg_id, self._diacritize(text, lang, "original"), None, lang, spk, source)
            self._queue_translation(seg_id, text, lang)

    def _should_switch_device(self):
        """The default device changed, or the one the user picked is plugged back in."""
        if self.cfg["audio_device"] == "default":
            return self._default_device_changed()
        return self._capture.using_fallback and audio.device_available(self.cfg["audio_device"])

    def _default_device_changed(self):
        name = audio.default_output_name()
        return name is not None and not self._capture.device_name.startswith(name)
