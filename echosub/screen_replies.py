# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Short written answers shown in the caption box when someone says a phrase you chose.

This is for a shared screen: a person in a Discord call says the wake word and one of your phrases,
and EchoSub writes your own prepared line in the caption box for everyone watching to read.

What it is not, on purpose:

- **Nothing is sent anywhere.** No message to Discord, no bot, no typing into another program, no
  audio, no network request of any kind. The only thing that happens is text on your own screen.
- **Nothing is generated.** Every answer is written by you in the settings; there is no AI here and
  no web lookup, so the same phrase always produces the same line.
- **Off unless you switch it on.** Unlike the other commands, no wake word is needed: the phrase
  is recognized wherever it is said, because showing your own line on your own screen cannot do
  any harm. Upper and lower case, punctuation and Arabic spelling are all evened out first.
"""
import re

MAX_PAIRS = 20
MAX_PHRASE_CHARS = 60
MAX_REPLY_CHARS = 200
DEFAULT_SECONDS = 8

EXAMPLES = (
    {"phrase": "who are you", "reply": "EchoSub — live captions and translation for whatever this PC plays."},
    {"phrase": "what is this", "reply": "These captions are made on this PC by EchoSub. Nothing is uploaded."},
    {"phrase": "من انت", "reply": "أنا إيكو سب — ترجمة فورية لكل ما يُشغَّل على هذا الجهاز."},
)


def valid_pairs(entries):
    """Keep only sound phrase/answer pairs; anything else is dropped rather than guessed at."""
    pairs, seen = [], set()
    for entry in entries or ():
        if not isinstance(entry, dict):
            continue
        phrase = re.sub(r"\s+", " ", str(entry.get("phrase", ""))).strip()[:MAX_PHRASE_CHARS]
        reply = re.sub(r"\s+", " ", str(entry.get("reply", ""))).strip()[:MAX_REPLY_CHARS]
        key = phrase.lower()
        if not phrase or not reply or key in seen:
            continue
        seen.add(key)
        pairs.append({"phrase": phrase, "reply": reply})
        if len(pairs) >= MAX_PAIRS:
            break
    return pairs


def find_reply(window, entries, position_of):
    """The answer for the phrase heard after the wake word, or None.

    `position_of` is the caller's word matching, so a phrase is recognized the same way commands
    are (whole words, Arabic endings, languages written without spaces).
    """
    best, best_at = None, -1
    for entry in valid_pairs(entries):
        at = position_of(window, entry["phrase"])
        if at >= 0 and (best_at < 0 or at < best_at):
            best, best_at = entry, at
    return best


def reply_command(entry):
    """A command entry for the runner: it only ever carries text to show."""
    return {"key": f"reply:{entry['phrase'].lower()}", "action": "reply", "target": entry["reply"],
            "label": entry["reply"]}
