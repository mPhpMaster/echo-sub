# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Spoken text made comparable, words found in it, and the warning about a wake word heard by accident."""
import re

from . import voice_vocabulary as vocabulary

PREFIX_MATCH_MIN_CHARS = 5  # from this length a word may carry a grammatical ending


_ARABIC_MARKS = re.compile(r"[ً-ْـ]")
_PUNCTUATION = re.compile(r"[^\w\s؀-ۿ]+", re.UNICODE)


def normalize(text):
    """Lower-case, drop punctuation and Arabic diacritics, and even out spacing, alifs and taa."""
    text = _ARABIC_MARKS.sub("", str(text).lower())
    text = _PUNCTUATION.sub(" ", text)
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ة", "ه").replace("ى", "ي")
    return re.sub(r"\s+", " ", text).strip()


# Words common enough in ordinary speech that using one as a wake word means EchoSub will think
# it is being spoken to all day long. "PC" is the one that catches people out: it is in every
# other sentence of a technology video.
RISKY_WAKE_WORDS = {
    "pc", "computer", "laptop", "windows", "ok", "okay", "hey", "yes", "no", "now", "stop", "go",
    "app", "game", "video", "sound", "audio", "music", "screen", "phone", "mic", "test", "one",
    "بي سي", "بيسي", "كمبيوتر", "لاب توب", "نعم", "لا", "الان", "شاشه", "صوت",
    # other assistants: videos and calls name them all the time
    "alexa", "siri", "google", "hey google", "ok google", "cortana", "copilot", "chatgpt", "gemini",
    "اليكسا", "سيري", "جوجل",
    # what people call each other in a call or a game
    "daddy", "dad", "mom", "mommy", "baby", "bro", "dude", "man", "guys", "buddy", "sir",
    "بابا", "ماما", "اخوي", "حبيبي", "يا رجال",
}
WAKE_WORD_MIN_CHARS = 4


def wake_word_warning(wake_words):
    """Why a wake word is likely to be heard by accident, or None when it looks sound.

    EchoSub listens to everything the PC plays, so a wake word that turns up in ordinary speech
    costs far more here than it would on a phone: every stray match is a sentence it tries to obey.
    """
    risky, short = [], []
    for raw in str(wake_words).split(","):
        word = normalize(raw)
        if not word:
            continue
        if word in RISKY_WAKE_WORDS:
            risky.append(raw.strip())
        elif len(word.replace(" ", "")) < WAKE_WORD_MIN_CHARS:
            short.append(raw.strip())
    if not risky and not short:
        return None
    parts = []
    if risky:
        parts.append("“" + "”, “".join(risky) + ("” turn up" if len(risky) > 1 else "” turns up") +
                     " in ordinary speech, so anything your PC plays will set it off often")
    if short:
        parts.append("“" + "”, “".join(short) + "” is very short, which is easily misheard")
    return ". ".join(parts) + ". Something two words long and unusual is heard far less by accident."


def _needs_word_boundary(word):
    """Chinese, Japanese, Korean and Thai are written without spaces, so they match as plain text."""
    return not any(low <= ord(ch) <= high for ch in word for low, high in vocabulary.NO_SPACE_RANGES)


def position_of(window, word):
    """Where `word` appears in the sentence, or -1. Whole words, except for space-less scripts."""
    word = normalize(word)
    if not word:
        return -1
    if not _needs_word_boundary(word):
        return window.find(word)
    # Turkish, Arabic, Hindi and others glue endings onto a word ("altyazi" -> "altyazilari"),
    # so a long word may be the start of the spoken one; a short one must match exactly.
    tail = "" if len(word) >= PREFIX_MATCH_MIN_CHARS else r"(?!\w)"
    match = re.search(rf"(?<!\w){re.escape(word)}{tail}", window)
    return match.start() if match else -1


def _first_position(window, words):
    found = [position_of(window, word) for word in words]
    found = [index for index in found if index >= 0]
    return min(found) if found else -1


def _spoken_tail(raw_text, words):
    """What was said after one of `words`, taken from the text as spoken rather than normalized.

    A web address has to come from the raw text: normalizing would turn "a.com" into "a com".
    The earliest of those words wins, and at that spot the longest one ("go to" over "go").
    """
    lowered = str(raw_text).lower()
    found = []
    for word in words:
        for match in re.finditer(rf"(?<!\w){re.escape(word.lower())}(?!\w)", lowered):
            found.append((match.start(), -match.end()))
    if not found:
        return ""
    start, negative_end = min(found)
    return str(raw_text)[-negative_end:].strip()


def is_cancel(text):
    """Did someone just say "no"? Only at the start of what was said, so a sentence that merely
    contains the word does not call off a command that is waiting.
    """
    spoken = normalize(text)
    return any(spoken == word or spoken.startswith(word + " ")
               for word in (normalize(w) for w in vocabulary.CANCEL_WORDS) if word)
