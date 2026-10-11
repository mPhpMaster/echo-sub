# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Spoken text made comparable, and the warning about a wake word that will be heard by accident."""
import re


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
