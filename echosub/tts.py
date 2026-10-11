# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Reading the captions aloud with the voices Windows already has (SAPI), on this PC, offline.

Off by default. Each finished caption is spoken once — its translation, or the original — in a
voice for that language, from a thread of its own so nothing on screen waits for it.

What it says comes out of the speakers EchoSub is listening to, so while a voice is speaking the
engine is told to ignore what the PC plays (your microphone still counts). Otherwise EchoSub would
caption its own voice and read that out again, for ever.
"""
import collections
import logging
import threading
import time

log = logging.getLogger(__name__)

MAX_WAITING = 2          # if captions come faster than they can be read, the oldest are skipped
ECHO_TAIL = 0.6          # seconds after a voice stops during which the PC's sound is still ignored
SVSF_DEFAULT = 0
SVSF_PURGE = 2

# Windows identifies a voice's language by a number; the low ten bits are the language itself.
PRIMARY_LANGUAGE = {
    "ar": 0x01, "bg": 0x02, "ca": 0x03, "zh": 0x04, "cs": 0x05, "da": 0x06, "de": 0x07, "el": 0x08,
    "en": 0x09, "es": 0x0A, "fi": 0x0B, "fr": 0x0C, "he": 0x0D, "hu": 0x0E, "it": 0x10, "ja": 0x11,
    "ko": 0x12, "nl": 0x13, "no": 0x14, "nb": 0x14, "pl": 0x15, "pt": 0x16, "ro": 0x18, "ru": 0x19,
    "hr": 0x1A, "sk": 0x1B, "sv": 0x1D, "th": 0x1E, "tr": 0x1F, "ur": 0x20, "id": 0x21, "uk": 0x22,
    "sl": 0x24, "et": 0x25, "lv": 0x26, "lt": 0x27, "fa": 0x29, "vi": 0x2A, "hi": 0x39, "ms": 0x3E,
    "ta": 0x49, "te": 0x4A, "bn": 0x45,
}


def language_of(attribute):
    """The primary language numbers a voice's "Language" attribute names ("401;9" → {0x01, 0x09})."""
    found = set()
    for part in str(attribute or "").replace(",", ";").split(";"):
        try:
            found.add(int(part.strip(), 16) & 0x3FF)
        except ValueError:
            continue
    return found


def pick_voice(voices, lang, wanted=""):
    """The voice to use: the one chosen by name if it is there, else the first for this language."""
    if wanted:
        for voice in voices:
            if voice["name"] == wanted:
                return voice
    primary = PRIMARY_LANGUAGE.get(str(lang or "").split("-")[0].lower())
    for voice in voices:
        if primary is not None and primary in voice["languages"]:
            return voice
    return None


def _sapi():
    import comtypes.client  # loaded only when a voice is first needed

    return comtypes.client.CreateObject("SAPI.SpVoice")


# The newer "OneCore" voices (Arabic among them on most PCs) live apart from the older SAPI ones.
ONECORE_VOICES = r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore\Voices"


def _tokens(sapi):
    """Every voice token: the newer OneCore ones first (they sound better), then the classic ones."""
    import comtypes.client

    found = []
    try:
        category = comtypes.client.CreateObject("SAPI.SpObjectTokenCategory")
        category.SetId(ONECORE_VOICES, False)
        found.append(category.EnumerateTokens())
    except Exception as e:  # an older Windows without them
        log.info("No OneCore voices: %s", e)
    found.append(sapi.GetVoices())
    for tokens in found:
        for index in range(tokens.Count):
            yield tokens.Item(index)


def list_voices(sapi=None):
    """[{"name", "languages", "token"}] for every voice on this PC; [] if there is no speech."""
    try:
        sapi = sapi or _sapi()
        voices, seen = [], set()
        for token in _tokens(sapi):
            name = token.GetDescription()
            if name in seen:
                continue
            seen.add(name)
            voices.append({"name": name, "languages": language_of(token.GetAttribute("Language")), "token": token})
        return voices
    except Exception as e:  # no speech engine, or COM not available here
        log.info("Windows voices are not available: %s", e)
        return []


class Speaker:
    """Speaks one caption at a time on a thread of its own. `settings()` is read for every caption."""

    def __init__(self, settings, on_speaking=None, on_missing_voice=None):
        self.settings = settings
        self.on_speaking = on_speaking or (lambda speaking: None)
        self.on_missing_voice = on_missing_voice or (lambda lang: None)
        self._waiting = collections.deque()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = None
        self._missing = set()

    def say(self, text, lang):
        text = " ".join(str(text or "").split())
        if not text:
            return
        while len(self._waiting) >= MAX_WAITING:
            self._waiting.popleft()
        self._waiting.append((text, lang))
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="tts", daemon=True)
            self._thread.start()
        self._wake.set()

    def stop(self):
        self._stop.set()
        self._waiting.clear()
        self._wake.set()

    def _run(self):
        try:
            import comtypes

            comtypes.CoInitialize()
            sapi = _sapi()
            voices = list_voices(sapi)
        except Exception as e:
            log.warning("Could not start the Windows voice: %s", e)
            return
        while not self._stop.is_set():
            self._wake.wait(0.5)
            self._wake.clear()
            while self._waiting and not self._stop.is_set():
                text, lang = self._waiting.popleft()
                self._speak(sapi, voices, text, lang)

    def _speak(self, sapi, voices, text, lang):
        cfg = self.settings()
        voice = pick_voice(voices, lang, cfg.get("tts_voice", ""))
        if voice is None:
            if lang not in self._missing:
                self._missing.add(lang)
                self.on_missing_voice(lang)
            return
        try:
            sapi.Voice = voice["token"]
            sapi.Rate = max(-10, min(10, int(cfg.get("tts_rate", 0))))
            sapi.Volume = max(0, min(100, int(cfg.get("tts_volume", 100))))
            self.on_speaking(True)
            sapi.Speak(text, SVSF_DEFAULT)  # waits until it has been said
        except Exception as e:
            log.info("Could not read a caption aloud: %s", e)
        finally:
            self.on_speaking(False)


class SpeechMixin:
    """For the App: read finished captions aloud when the settings say so."""

    def _speaker(self):
        if getattr(self, "_tts", None) is None:
            self._tts = Speaker(lambda: self.cfg, self._tts_speaking, self._tts_missing_voice)
        return self._tts

    def _tts_wanted(self, source):
        if not self.cfg.get("tts_enabled", False):
            return False
        return source != "mic" or self.cfg.get("tts_who", "others") == "everyone"

    def speak_final(self, seg_id, original, translated, lang, source):
        """A finished caption: read now, or keep its place until its translation arrives."""
        missing, self._tts_note = getattr(self, "_tts_note", None), None
        if missing:  # noticed on the voice's thread; said here, on the screen's
            from PySide6.QtWidgets import QSystemTrayIcon

            from . import APP_NAME, languages

            self.tray.showMessage(APP_NAME, f"Windows has no voice for {languages.name(missing) or missing}. Add "
                                  "one in Windows Settings → Time & language → Speech.",
                                  QSystemTrayIcon.Information, 6000)
        if not self._tts_wanted(source):
            return
        if self.cfg.get("tts_what", "translation") == "original":
            self._speaker().say(original, lang)
        elif translated is not None:  # nothing to translate: the caption is already in that language
            self._speaker().say(translated, self.cfg.get("target_lang", "en"))
        else:
            waiting = getattr(self, "_tts_waiting", None)
            if waiting is None:
                waiting = self._tts_waiting = collections.OrderedDict()
            waiting[seg_id] = True
            while len(waiting) > 20:
                waiting.popitem(last=False)

    def speak_translation(self, seg_id, translated):
        waiting = getattr(self, "_tts_waiting", None)
        if waiting and waiting.pop(seg_id, None):
            self._speaker().say(translated, self.cfg.get("target_lang", "en"))

    def _tts_speaking(self, speaking):
        """From the voice's thread: keep the engine from captioning the voice itself."""
        engine = getattr(self, "engine", None)
        if engine is not None:
            engine.mute_system_until = float("inf") if speaking else time.monotonic() + ECHO_TAIL

    def _tts_missing_voice(self, lang):
        log.info("No Windows voice for %s", lang)
        self._tts_note = lang  # shown with the next caption, on the screen's thread

    def stop_speaking(self):
        if getattr(self, "_tts", None) is not None:
            self._tts.stop()
            self._tts = None
