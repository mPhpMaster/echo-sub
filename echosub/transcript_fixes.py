# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Two small passes over a finished caption: your own spellings, and words you want to be told about.

Speech recognition has no idea how a game, a guild or a friend of yours is spelled, so it writes
something that sounds close. Rather than a bigger model, this is a list you keep: heard this, write
that. It is a plain word swap — nothing is guessed, and a word you did not write is never touched.

The second pass looks for words you want flagged, so something said while you are busy can reach
you. It only reports; it never changes the caption.
"""
import re

MAX_FIXES = 60
MAX_ALERTS = 30
MAX_CHARS = 80


def _clean(value):
    return " ".join(str(value).split())[:MAX_CHARS]


def valid_fixes(entries):
    """Normalize the "heard this, write that" list; a row missing either half is dropped."""
    fixes, seen = [], set()
    for entry in entries or ():
        if not isinstance(entry, dict):
            continue
        heard, write = _clean(entry.get("heard", "")), _clean(entry.get("write", ""))
        key = heard.lower()
        if not heard or not write or key in seen:
            continue
        seen.add(key)
        fixes.append({"heard": heard, "write": write})
        if len(fixes) >= MAX_FIXES:
            break
    return fixes


def valid_alerts(entries):
    """Normalize the list of words to be told about."""
    words, seen = [], set()
    for entry in entries or ():
        word = _clean(entry)
        if not word or word.lower() in seen:
            continue
        seen.add(word.lower())
        words.append(word)
        if len(words) >= MAX_ALERTS:
            break
    return words


def _pattern(phrase):
    """Match `phrase` as whole words, with any spacing, ignoring case.

    Languages written without spaces have no word boundaries to use, so there the phrase is matched
    as plain text.
    """
    parts = [re.escape(part) for part in phrase.split()]
    body = r"\s+".join(parts)
    if re.search(r"\w", phrase, re.UNICODE) and phrase.isascii():
        body = rf"(?<!\w){body}(?!\w)"
    return re.compile(body, re.IGNORECASE | re.UNICODE)


def apply_fixes(text, fixes):
    """Put your own spellings into a caption. Longest phrases first, so they win over shorter ones."""
    if not text:
        return text
    for fix in sorted(valid_fixes(fixes), key=lambda f: len(f["heard"]), reverse=True):
        text = _pattern(fix["heard"]).sub(fix["write"].replace("\\", r"\\"), text)
    return text


def alerts_in(text, words):
    """The watched words this caption contains, in the order they were listed."""
    if not text:
        return []
    return [word for word in valid_alerts(words) if _pattern(word).search(text)]
