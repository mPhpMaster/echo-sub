# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Cheap quality gates that reject common Whisper hallucinations before translation."""
import re

HALLUCINATIONS = [
    "thank you for watching", "thanks for watching", "subscribe", "amara.org",
    "subtitles by", "ترجمة نانسي قنقر", "اشتركوا في القناة", "شكرا للمشاهدة",
    "شكراً للمشاهدة", "ご視聴ありがとうございました", "字幕", "продолжение следует",
]
MAX_CHARS_PER_SECOND = 32       # above normal fast speech; usually music/noise hallucination
LIVE_MAX_CHARS_PER_SECOND = 24  # live text is half a sentence, so judge its density more strictly
LIVE_MIN_LANGUAGE_PROB = 0.5    # live text from an unsure language guess is usually noise
LIVE_MIN_CHARS = 2


def is_hallucination(text):
    """Identify known filler, empty captions, and exact repeating loops."""
    normalized = text.lower().strip(" .!?,،")
    if not normalized:
        return True
    if len(normalized) < 40 and any(phrase in normalized for phrase in HALLUCINATIONS):
        return True
    words = re.findall(r"\w+", normalized, flags=re.UNICODE)
    if not words:
        return True
    return len(words) >= 6 and any(
        words == words[:size] * (len(words) // size)
        for size in range(1, min(5, len(words) // 2) + 1)
        if len(words) % size == 0
    )


def is_unreliable_live_text(text, seconds, language_probability):
    """Live text is a guess at half a sentence, so it is held to a stricter standard than a caption.

    It is only shown while speaking and is replaced by the finished caption, so rejecting it costs
    nothing but a moment without live text, while showing noise as words is confusing.
    """
    stripped = text.strip()
    if len(stripped) < LIVE_MIN_CHARS or is_hallucination(stripped):
        return True
    if language_probability is not None and language_probability < LIVE_MIN_LANGUAGE_PROB:
        return True
    return is_implausibly_fast(stripped, seconds, LIVE_MAX_CHARS_PER_SECOND)


def is_implausibly_fast(text, seconds, max_chars_per_second=MAX_CHARS_PER_SECOND):
    """Reject text density that cannot reasonably fit the supplied audio window."""
    if seconds < 0.8:
        return False
    characters = len(re.sub(r"\s+", "", text))
    return characters / seconds > max_chars_per_second
