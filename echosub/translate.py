# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Translation backends: local NLLB-200 (CTranslate2) or Google Translate."""
import logging
import os
import re
import threading
import time

from . import config, languages

log = logging.getLogger(__name__)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?。！？؟])\s+")


class NoTranslator:
    streaming = True

    def translate(self, text, src, tgt):
        return text


class NLLBTranslator:
    streaming = True

    def __init__(self, path, device="cuda"):
        import ctranslate2
        import sentencepiece as spm

        if device == "cuda" and ctranslate2.get_cuda_device_count() == 0:
            device = "cpu"
        supported = ctranslate2.get_supported_compute_types(device)
        compute_type = "int8_float16" if "int8_float16" in supported else "int8"
        self.translator = ctranslate2.Translator(
            path, device=device, compute_type=compute_type, intra_threads=4
        )
        self.sp = spm.SentencePieceProcessor(model_file=os.path.join(path, "sentencepiece.bpe.model"))

    def translate(self, text, src, tgt):
        src_code, tgt_code = languages.nllb_code(src), languages.nllb_code(tgt)
        if not text or not tgt_code:
            return text
        if not src_code:
            src_code = "eng_Latn"
        sentences = [s for s in _SENTENCE_SPLIT.split(text) if s.strip()]
        batch = [[src_code] + self.sp.encode(s, out_type=str) + ["</s>"] for s in sentences]
        results = self.translator.translate_batch(
            batch,
            target_prefix=[[tgt_code]] * len(batch),
            beam_size=2,
            max_decoding_length=200,
            repetition_penalty=1.1,
            no_repeat_ngram_size=4,
        )
        out = []
        for r in results:
            tokens = r.hypotheses[0]
            if tokens and tokens[0] == tgt_code:
                tokens = tokens[1:]
            out.append(self.sp.decode(tokens).strip().lstrip("-–— ").strip())
        return " ".join(out).strip()


class RateLimited(Exception):
    """Google Translate refuses requests for a while; `retry_in` is how long EchoSub waits before asking again."""

    def __init__(self, retry_in):
        super().__init__(f"Google Translate is limiting requests; retrying in {round(retry_in)} s")
        self.retry_in = retry_in


class GoogleTranslator:
    streaming = False  # avoid hammering the web API with partial results
    MIN_INTERVAL = 0.35          # s between requests (Google allows about 5 per second)
    RETRY_DELAYS = (1.0, 3.0)    # s to wait before retrying a request Google refused
    COOLDOWN = (20.0, 300.0)     # s to pause after the retries fail: first time, maximum (doubles each time)

    def __init__(self, fallback=None):
        """`fallback`: (name, factory) of an offline translator used while Google refuses requests."""
        from deep_translator import GoogleTranslator as _GT
        from deep_translator.exceptions import TooManyRequests

        self._cls = _GT
        self._too_many = TooManyRequests
        self._cache = {}
        self._lock = threading.Lock()
        self._last_request = 0.0
        self._paused_until = 0.0
        self._cooldown = self.COOLDOWN[0]
        self._fallback_spec = fallback
        self._fallback = None
        self._offline = False
        self.notify = lambda message: None  # set by the engine: shows a short status message

    def translate(self, text, src, tgt):
        if not text:
            return text
        try:
            result = self._google(text, tgt)
        except RateLimited:
            offline = self._offline_translator()
            if offline is None:
                raise
            if not self._offline:
                self._offline = True
                self.notify(f"Google Translate is limiting requests — translating offline with "
                            f"{self._fallback_spec[0]} for now")
            return offline.translate(text, src, tgt)
        if self._offline:
            self._offline = False
            self.notify("Google Translate is available again")
        return result

    def _offline_translator(self):
        if self._fallback is None and self._fallback_spec is not None:
            try:
                self._fallback = self._fallback_spec[1]()
            except Exception:
                log.exception("Could not load the offline translation model")
                self._fallback_spec = None
        return self._fallback

    def _google(self, text, tgt):
        key = languages.google_code(tgt)
        if key not in self._cache:
            self._cache[key] = self._cls(source="auto", target=key)
        with self._lock:
            now = time.monotonic()
            if now < self._paused_until:
                raise RateLimited(self._paused_until - now)
            # While already translating offline, one try is enough to see whether Google is back
            for delay in (0.0,) + (() if self._offline else self.RETRY_DELAYS):
                time.sleep(max(delay, self._last_request + self.MIN_INTERVAL - time.monotonic(), 0.0))
                self._last_request = time.monotonic()
                try:
                    result = self._cache[key].translate(text) or text
                except self._too_many:
                    continue
                self._cooldown = self.COOLDOWN[0]
                return result
            # Still refused: stop asking for a while, longer each time it happens again
            self._paused_until = time.monotonic() + self._cooldown
            retry_in, self._cooldown = self._cooldown, min(self._cooldown * 2, self.COOLDOWN[1])
            raise RateLimited(retry_in)


def offline_fallback(device, downloader=None):
    """(name, factory) for an NLLB model that is already downloaded, or None."""
    from .downloads import ModelDownloader

    downloader = downloader or ModelDownloader()
    for key in config.NLLB_REPOS:
        path = downloader.nllb_local(key)
        if path:
            return key.upper(), lambda: NLLBTranslator(path, device)
    return None


def create(key, device, downloader=None):
    if key == "google":
        return GoogleTranslator(offline_fallback(device, downloader))
    if key in config.NLLB_REPOS:
        from .downloads import ModelDownloader

        return NLLBTranslator((downloader or ModelDownloader()).nllb(key), device)
    return NoTranslator()
