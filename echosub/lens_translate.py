# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""EchoSub Lens: translating many short texts at once, remembering what was already translated.

The screen is read again every second, and most of it has not changed: a cache keeps every text it
has seen, so only new text is sent to the translator. Google gets one request for many lines.
"""
import logging
import threading
from collections import OrderedDict

from . import config, languages, translate

log = logging.getLogger(__name__)

CACHE_SIZE = 5000
GOOGLE_CHUNK = 4000      # characters per Google request (its limit is 5000)
SAME = "same"            # use the translator chosen in EchoSub's own settings
CHOICES = {
    SAME: "Same as EchoSub",
    "google": config.TRANSLATORS["google"],
    "nllb-600m": config.TRANSLATORS["nllb-600m"],
    "nllb-1.3b": config.TRANSLATORS["nllb-1.3b"],
}


def resolve(choice, echosub_cfg):
    """The translator key to load: the Lens choice, or EchoSub's own (never "none": Lens must translate)."""
    key = echosub_cfg.get("translator", "google") if choice == SAME else choice
    return key if key in CHOICES and key != SAME else "google"


def already_in(text, target):
    """True when `text` is clearly written in the target language's alphabet (Arabic shown to an Arabic reader)."""
    script = languages.text_script(text)
    expected = languages.LANGUAGE_SCRIPTS.get(target)
    if script is None or not expected:
        return False
    return script in expected


class LensTranslator:
    """`translate_many(texts, target)` -> translations in the same order. Thread-safe, loads lazily."""

    def __init__(self, key, device="cuda", factory=translate.create):
        self.key = key
        self._device = device
        self._factory = factory
        self._backend = None
        self._lock = threading.Lock()
        self._cache = OrderedDict()

    def _get_backend(self):
        if self._backend is None:
            device = self._device
            if device == "vulkan":
                device = "cuda"
            self._backend = self._factory(self.key, device)
        return self._backend

    def cached(self, text, target):
        return self._cache.get((target, text))

    def translate_many(self, texts, target):
        with self._lock:
            todo = [t for t in dict.fromkeys(texts) if (target, t) not in self._cache]
            if todo:
                backend = self._get_backend()
                if isinstance(backend, translate.GoogleTranslator):
                    results = self._google(backend, todo, target)
                elif hasattr(backend, "translate_many"):  # NLLB: one pass for the whole screen
                    results = backend.translate_many(todo, "auto", target)
                else:
                    results = [backend.translate(t, "auto", target) for t in todo]
                for text, result in zip(todo, results):
                    self._remember((target, text), result or text)
            return [self._cache.get((target, t), t) for t in texts]

    def _remember(self, key, value):
        self._cache[key] = value
        self._cache.move_to_end(key)
        while len(self._cache) > CACHE_SIZE:
            self._cache.popitem(last=False)

    @staticmethod
    def _google(backend, texts, target):
        """Many lines in one request: Google keeps line breaks, so the answer splits back line by line."""
        results = []
        for chunk in _chunks(texts, GOOGLE_CHUNK):
            joined = "\n".join(t.replace("\n", " ") for t in chunk)
            answer = backend.translate(joined, "auto", target)
            parts = [p.strip() for p in (answer or "").split("\n")]
            if len(parts) != len(chunk):  # lines merged or split: ask for each one on its own
                parts = [backend.translate(t, "auto", target) for t in chunk]
            results.extend(parts)
        return results


def _chunks(texts, limit):
    chunk, size = [], 0
    for text in texts:
        if chunk and size + len(text) + 1 > limit:
            yield chunk
            chunk, size = [], 0
        chunk.append(text)
        size += len(text) + 1
    if chunk:
        yield chunk
