# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Making sense of the model list a service sends back.

A service lists everything it has: models that answer questions, but also ones that only draw
pictures, speak, transcribe or turn text into numbers, and older models it still names but no
longer lets new users call. These helpers keep the ones that can answer, put the newest first,
and pick a sensible one when the user has not chosen — a fast, current, non-preview model.
"""
import re

# Words in a model's name that mean it cannot hold a conversation
NOT_FOR_CHAT = ("embed", "tts", "whisper", "dall-e", "imagen", "veo", "image", "audio", "realtime",
                "transcribe", "moderation", "aqa", "search", "davinci", "babbage", "computer-use", "lyria",
                "sora", "speech", "vision-only")
# Fast, inexpensive models: the right default for a short answer read off a caption box
FAST = ("flash", "mini", "chat", "haiku")
# Not meant to be relied on, or a slower, thinking-only variant
UNSTEADY = ("preview", "exp", "experimental", "thinking", "beta", "alpha", "latest")
DATED = re.compile(r"(19|20)\d{2}-?\d{2}-?\d{2}|-\d{3,4}$")
VERSION = re.compile(r"(\d+(?:\.\d+)*)")
SEPARATORS = re.compile(r"[-_./: ]+")


def words(name):
    """The words of a model's name — whole words, so "gemini" is never read as "mini"."""
    return set(SEPARATORS.split(str(name).lower()))


def can_chat(name):
    lowered = str(name).lower()
    return not any(word in lowered for word in NOT_FOR_CHAT)


def version(name):
    """The model's version as numbers, e.g. "gemini-3.8-flash" → (3, 8); () when it has none."""
    found = VERSION.search(DATED.sub("", str(name)))
    return tuple(int(part) for part in found.group(1).split(".")) if found else ()


def newest_first(names):
    """The models that can answer, newest version first, then by name."""
    chat = {str(name) for name in names if name and can_chat(name)}
    return sorted(sorted(chat), key=version, reverse=True)


def best(names):
    """The model to use when none was chosen: current, fast and steady. None if nothing can chat."""
    def score(name):
        named = words(name)
        return (not named & set(UNSTEADY),                        # a released model before a preview
                bool(named & set(FAST)),                          # a fast one: answers come quickly
                version(name),                                    # the newest of those
                not named & {"lite", "nano"},                     # but not the cut-down version
                not DATED.search(name),                           # the name that follows updates
                -len(name))                                       # and the plainest name
    candidates = newest_first(names)
    return max(candidates, key=score) if candidates else None
