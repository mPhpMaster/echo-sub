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

from . import asr, audio, downloads, languages, speaker, tashkeel, translate

SR = audio.SAMPLE_RATE
PROMPT_MAX_AGE_SEC = 10.0   # previous sentence is used as Whisper context only if this recent
PROMPT_MAX_CHARS = 200
CHARS_PER_SEC = 15.0        # rough speaking rate, used to spot Whisper repeating its context
HEALTH_CHECK_SEC = 2.0

log = logging.getLogger(__name__)


class AudioStreamLost(RuntimeError):
    pass


class CaptionEngine:
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
        self._ids = itertools.count(1)
        self._sticky_lang = None
        self._sticky_time = 0.0
        self._asr_time = 0.0  # moving average of seconds per Whisper call
        self._last_text = ""
        self._last_lang = None
        self._last_time = 0.0
        self._last_speaker = None

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
                delay = min(10, 2 ** min(failures, 3))
                self.on_state("recovering")
                self.on_status(f"Audio problem ({e}) — retrying in {delay} s…")
                self._stop.wait(delay)
        self._close_capture()

    def _load(self):
        cfg = self.cfg
        downloader = downloads.ModelDownloader(
            on_event=self.on_download,
            should_cancel=lambda: self._cancel_download.is_set() or self._stop.is_set())
        self.on_status(f"Loading speech recognition model ({cfg['whisper_model']})…")
        whisper_path = downloader.whisper(cfg["whisper_model"])
        try:
            self.asr = asr.Transcriber(whisper_path, cfg["device"])
        except Exception as e:
            if cfg["device"] != "cuda":
                raise
            log.exception("GPU load failed, falling back to CPU")
            self.on_status(f"Could not use the GPU ({e}) — switching to CPU")
            self.asr = asr.Transcriber(whisper_path, "cpu")
        log.info("Whisper %s on %s/%s", cfg["whisper_model"], self.asr.device, self.asr.compute_type)

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

    def _open_capture(self):
        self._capture = audio.LoopbackCapture(self.cfg["audio_device"])
        try:
            self._capture.start()
        except Exception:
            self._capture = None
            raise
        log.info("Listening to %s", self._capture.device_name)
        self.on_status(
            f"Ready — listening to: {self._capture.device_name} "
            f"[{self.asr.device.upper()} / {self.asr.compute_type}]"
        )

    def _close_capture(self):
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
        cap = self._capture
        buf = np.zeros(0, dtype=np.float32)
        speech, vad_dirty = [], True  # VAD only reruns when the buffer changed
        last_partial_len = 0
        last_device_check = last_health_check = time.monotonic()
        last_activity = 0.0

        while not self._stop.is_set():
            chunks = []
            while not cap.queue.empty():
                chunks.append(cap.queue.get_nowait())
            if self.paused:
                buf, vad_dirty = buf[:0], True
                time.sleep(0.1)
                continue
            if chunks:
                buf, vad_dirty = np.concatenate([buf] + chunks), True

            now = time.monotonic()
            if now - last_health_check > HEALTH_CHECK_SEC:
                last_health_check = now
                if not cap.is_healthy():
                    raise AudioStreamLost(f"stream on '{cap.device_name}' stopped")
            if self.cfg["audio_device"] == "default" and now - last_device_check > 4:
                last_device_check = now
                if self._default_device_changed():
                    self._close_capture()
                    self._open_capture()
                    cap = self._capture
                    buf, vad_dirty = buf[:0], True
                    self.on_status(f"Switched audio device to: {cap.device_name}")
                    continue

            if len(buf) < SR * 0.4:
                time.sleep(0.05)
                continue

            if vad_dirty:
                speech, vad_dirty = self._vad(buf), False
            idle = max(0.0, now - cap.last_audio_time - 0.15)  # loopback sends nothing while silent

            if not speech:
                if len(buf) > SR * 2:
                    buf, vad_dirty = buf[-int(SR * 0.5):], True
                elif idle > 1.0:
                    buf, vad_dirty = buf[:0], True
                last_partial_len = 0
                time.sleep(0.1)
                continue

            if now - last_activity > 0.3:
                last_activity = now
                self.on_activity()

            start = max(0, speech[0]["start"] - int(SR * 0.2))
            last_end = speech[-1]["end"]
            tail_silence = (len(buf) - last_end) / SR + idle
            duration = (len(buf) - start) / SR

            if tail_silence >= self.cfg["silence_sec"]:
                cut = min(len(buf), last_end + int(SR * 0.2))
                self._finalize(buf[start:cut], speech, start)
                buf, vad_dirty, last_partial_len = buf[cut:], True, 0
            elif duration >= self.cfg["max_segment_sec"]:
                cut = self._best_cut(speech, len(buf), start)
                self._finalize(buf[start:cut], speech, start)
                buf, vad_dirty, last_partial_len = buf[cut:], True, 0
            elif (self.cfg["show_partial"] and self._asr_time < 1.5
                  and len(buf) - last_partial_len >= SR * max(0.7, self._asr_time)):
                # Live partial text only when the GPU keeps up; otherwise it just delays final captions
                last_partial_len = len(buf)
                self._partial(buf[start:])
            else:
                time.sleep(0.05)

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

    def _context_prompt(self, spk):
        """The previous sentence, if it was recent and said by the same voice."""
        if (self._last_text and time.monotonic() - self._last_time < PROMPT_MAX_AGE_SEC
                and (spk is None or spk == self._last_speaker)):
            return self._last_text[-PROMPT_MAX_CHARS:]
        return None

    def _partial(self, seg):
        text, lang, _, _ = self._transcribe(seg, self._language_hint(), False)
        if not text:
            return
        if self.cfg["source_lang"] != "auto":
            lang = self.cfg["source_lang"]
        translated = None
        # Translate live text only when the translator is idle, so final captions never wait for it
        if self.translator.streaming and self._translations.empty():
            translated = self._translate(text, lang)
        self.on_partial(text, translated, lang)

    def _finalize(self, seg, speech, offset):
        if len(seg) < SR * 0.3:
            return
        regions = [(max(0, r["start"] - offset), min(len(seg), r["end"] - offset)) for r in speech]
        regions = [(a, b) for a, b in regions if b - a > 0]
        for a, b, spk in self._speaker_runs(seg, regions):
            self._finalize_one(seg[a:b], spk)

    def _speaker_runs(self, seg, regions):
        """Split an utterance where the voice changes -> [(start, end, speaker_id)]."""
        if self.speakers is None:
            return [(0, len(seg), None)]
        try:
            long_regions = [r for r in regions if r[1] - r[0] >= SR * 1.0]
            if len(long_regions) < 2:
                return [(0, len(seg), self.speakers.identify(seg))]

            labels = []
            for a, b in regions:
                labels.append(self.speakers.identify(seg[a:b]) if b - a >= SR * 1.0 else None)
            # Short regions inherit the voice of the preceding (or following) region
            for k in range(len(labels)):
                if labels[k] is None:
                    labels[k] = labels[k - 1] if k and labels[k - 1] is not None else None
            for k in reversed(range(len(labels))):
                if labels[k] is None and k + 1 < len(labels):
                    labels[k] = labels[k + 1]

            runs = []
            for (a, b), spk in zip(regions, labels):
                if runs and runs[-1][2] == spk:
                    runs[-1][1] = b
                else:
                    runs.append([a, b, spk])
            # Cut halfway through the pauses; first/last run reach the segment edges
            for k in range(len(runs) - 1):
                mid = (runs[k][1] + runs[k + 1][0]) // 2
                runs[k][1], runs[k + 1][0] = mid, mid
            runs[0][0], runs[-1][1] = 0, len(seg)
            return [tuple(r) for r in runs]
        except Exception:
            log.exception("Speaker detection failed for a segment")
            return [(0, len(seg), None)]

    def _finalize_one(self, seg, spk):
        if len(seg) < SR * 0.3:
            return
        src = self.cfg["source_lang"]
        forced = languages.whisper_code(src) if src != "auto" else None
        prompt = self._context_prompt(spk)
        text, lang, prob, probs = self._transcribe(seg, forced, True, prompt)
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
        if not text:
            self.on_partial("", "", lang)
            return

        self._last_text, self._last_lang, self._last_time, self._last_speaker = text, lang, time.monotonic(), spk
        seg_id = next(self._ids)
        if not self._should_translate(lang):
            shown = self._diacritize(text, lang, "original", "translation")
            self.on_final(seg_id, shown, shown, lang, spk)
        else:
            self.on_final(seg_id, self._diacritize(text, lang, "original"), None, lang, spk)
            self._translations.put((seg_id, text, lang))

    # ---- translation ------------------------------------------------------
    def _translation_worker(self):
        while not self._stop.is_set():
            try:
                seg_id, text, lang = self._translations.get(timeout=0.2)
            except queue.Empty:
                continue
            translated = self._translate(text, lang)
            self.on_translation(seg_id, self._diacritize(translated, self.cfg["target_lang"], "translation"))

    def _should_translate(self, lang):
        if isinstance(self.translator, translate.NoTranslator):
            return False
        # Same language: translating still rewrites dialect/casual speech into the standard language
        return lang != self.cfg["target_lang"] or self.cfg["translate_same_language"]

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

    def _default_device_changed(self):
        name = audio.default_output_name()
        return name is not None and not self._capture.device_name.startswith(name)
