# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Saving a session's captions as a subtitle file.

A caption is recorded with the moment it was finished, not the span of audio it came from, so the
start of each subtitle is that moment and the end is where the next one begins — capped, so a long
silence does not leave one line stretched across it. That makes this a faithful record of when each
line appeared on screen rather than a frame-accurate subtitle track, which is the honest claim.
"""
MIN_SECONDS = 1.2
MAX_SECONDS = 7.0


def _stamp(seconds):
    seconds = max(0.0, seconds)
    whole = int(seconds)
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{int(round((seconds - whole) * 1000)):03d}"


def spans(records):
    """(start, end, record) in seconds from the first caption, with sane lengths."""
    if not records:
        return []
    first = records[0]["time"]
    starts = [(r["time"] - first).total_seconds() for r in records]
    out = []
    for index, record in enumerate(records):
        start = starts[index]
        following = starts[index + 1] if index + 1 < len(starts) else start + MAX_SECONDS
        end = min(max(following, start + MIN_SECONDS), start + MAX_SECONDS)
        out.append((start, end, record))
    return out


def to_srt(records, which="both"):
    """A SubRip file as text. `which` picks the original, the translation, or one above the other."""
    blocks = []
    for number, (start, end, record) in enumerate(spans(records), start=1):
        original = (record.get("original") or "").strip()
        translated = (record.get("translated") or "").strip()
        if which == "original":
            lines = [original]
        elif which == "translation":
            lines = [translated or original]
        else:
            lines = [line for line in (original, translated if translated != original else "") if line]
        text = "\n".join(lines).strip()
        if not text:
            continue
        blocks.append(f"{number}\n{_stamp(start)} --> {_stamp(end)}\n{text}\n")
    return "\n".join(blocks)
