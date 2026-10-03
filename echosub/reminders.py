# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Reminders you set by speaking: "remind me in five minutes to check the oven".

What is understood, and nothing beyond it, so that a reminder is never set at a time nobody meant:

- **A delay** — "in / after <number> <minutes | hours | days>", where the number may be written out
  ("five") or spoken as digits, and "half an hour" and "a quarter of an hour" are understood.
- **A time of day** — "at 5", "at 5:30", "at 5 pm", optionally with "today" or "tomorrow". Without
  am/pm, a time that has already passed today is taken to mean tomorrow.

Anything else is refused rather than guessed at. The reminder itself is whatever was said after
"to" — or the rest of the sentence, when there is no "to".
"""
import datetime
import re

MAX_TEXT = 200
MAX_REMINDERS = 200
MAX_FINISHED = 100
MAX_DAYS = 365

LIST_WORDS = (
    "my reminders", "the reminders", "list reminders", "show reminders", "show my reminders",
    "what are my reminders", "reminders list",
    "تذكيراتي", "التذكيرات", "قائمة التذكيرات", "اعرض التذكيرات",
)

REMIND_WORDS = (
    "remind me", "remind", "reminder",
    "ذكرني", "ذكّرني", "تذكير",
)
IN_WORDS = ("in", "after", "within", "بعد", "خلال")
AT_WORDS = ("at", "الساعة", "الساعه", "عند")
TOMORROW_WORDS = ("tomorrow", "غدا", "بكرة", "بكره")
TODAY_WORDS = ("today", "اليوم")
ABOUT_WORDS = ("to", "that", "ان", "أن", "بأن", "بان")

MINUTES = ("minute", "minutes", "min", "mins", "دقيقة", "دقائق", "دقيقه")
HOURS = ("hour", "hours", "hr", "hrs", "ساعة", "ساعات", "ساعه")
DAYS = ("day", "days", "يوم", "ايام", "أيام")
SECONDS = ("second", "seconds", "sec", "secs", "ثانية", "ثواني", "ثانيه")

WORD_NUMBERS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20,
    "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "ninety": 90,
    "واحد": 1, "دقيقة": 1, "اثنين": 2, "ثلاث": 3, "ثلاثة": 3,
    "اربع": 4, "أربع": 4, "خمس": 5, "خمسة": 5, "ست": 6, "سبع": 7,
    "ثمان": 8, "تسع": 9, "عشر": 10, "عشرة": 10, "عشرين": 20, "ثلاثين": 30,
}
HALF_WORDS = ("half", "نص", "نصف")
QUARTER_WORDS = ("quarter", "ربع")


def _number_before(words, index):
    """The count written just before a unit word, as digits or a word. None when there is none."""
    if index <= 0:
        return None
    # "a" and "an" mean one, but only if nothing better is behind them: in "half an hour" the
    # number that matters is the "half", one word further back.
    weak = None
    for back in range(1, min(4, index + 1)):
        word = words[index - back]
        if word.isdigit():
            return int(word)
        if word in HALF_WORDS:
            return 0.5
        if word in QUARTER_WORDS:
            return 0.25
        if word in ("a", "an"):
            weak = 1
            continue
        if word in WORD_NUMBERS:
            return WORD_NUMBERS[word]
        if word not in ("of", "من"):
            break
    return weak


def _delay(words):
    """Seconds asked for by "in five minutes", or None when no delay was named."""
    for index, word in enumerate(words):
        for unit, seconds in ((SECONDS, 1), (MINUTES, 60), (HOURS, 3600), (DAYS, 86400)):
            if word not in unit:
                continue
            count = _number_before(words, index)
            if count is None:
                count = 1  # "in an hour", "remind me in a minute"
            total = count * seconds
            if 0 < total <= MAX_DAYS * 86400:
                return total
    return None


_TIME = re.compile(r"^(\d{1,2})(?::(\d{2}))?$")


def _time_of_day(words, now, tomorrow):
    """A datetime asked for by "at 5" or "at 5:30 pm", or None."""
    for index, word in enumerate(words):
        if word not in AT_WORDS or index + 1 >= len(words):
            continue
        match = _TIME.match(words[index + 1])
        if not match:
            continue
        hour, minute = int(match.group(1)), int(match.group(2) or 0)
        rest = words[index + 2:index + 4]
        said_pm = any(w in ("pm", "مساء", "مساءا") for w in rest)
        said_am = any(w in ("am", "صباحا", "صباح") for w in rest)
        if said_pm and hour < 12:
            hour += 12
        elif said_am and hour == 12:
            hour = 0
        if hour > 23 or minute > 59:
            return None
        when = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if tomorrow:
            return when + datetime.timedelta(days=1)
        if when > now:
            return when
        # Neither morning nor evening was said, so "at 5" means the next five o'clock there is —
        # this afternoon rather than tomorrow morning, which is what people mean by it.
        if not said_am and not said_pm and hour < 12:
            later = when + datetime.timedelta(hours=12)
            if later > now:
                return later
        return when + datetime.timedelta(days=1)
    return None


def _what_about(words):
    """What the reminder is about: whatever followed "to", else what is left of the sentence."""
    for index, word in enumerate(words):
        if word in ABOUT_WORDS and index + 1 < len(words):
            return " ".join(words[index + 1:])
    skip = set(IN_WORDS) | set(AT_WORDS) | set(TOMORROW_WORDS) | set(TODAY_WORDS)
    skip |= set(MINUTES) | set(HOURS) | set(DAYS) | set(SECONDS) | set(WORD_NUMBERS)
    skip |= set(HALF_WORDS) | set(QUARTER_WORDS) | {"a", "an", "of", "pm", "am", "me"}
    left = [w for w in words if w not in skip and not w.isdigit()]
    return " ".join(left)


def parse(said, now=None):
    """(when, what) for a spoken reminder, or None when no time was named.

    `said` is everything after the word "remind"; the caller has already matched that.
    """
    now = now or datetime.datetime.now()
    words = [w for w in re.split(r"[^\w:]+", str(said).lower()) if w]
    if not words:
        return None
    tomorrow = any(w in TOMORROW_WORDS for w in words)
    seconds = _delay(words)
    if seconds is not None:
        when = now + datetime.timedelta(seconds=seconds)
    else:
        when = _time_of_day(words, now, tomorrow)
        if when is None and tomorrow:
            when = (now + datetime.timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    if when is None:
        return None
    what = _what_about(words).strip()[:MAX_TEXT]
    return when, what


def valid(entries):
    """Stored reminders, soonest first, with anything unreadable dropped.

    One that has already been shown keeps a `done` time rather than being thrown away, so the list
    in the settings can show what happened as well as what is still coming.
    """
    out = []
    for entry in entries or ():
        if not isinstance(entry, dict):
            continue
        what = " ".join(str(entry.get("what", "")).split())[:MAX_TEXT]
        try:
            when = datetime.datetime.fromisoformat(str(entry.get("when", "")))
        except ValueError:
            continue
        kept = {"when": when.isoformat(timespec="seconds"), "what": what}
        try:
            kept["done"] = datetime.datetime.fromisoformat(str(entry["done"])).isoformat(timespec="seconds")
        except (KeyError, TypeError, ValueError):
            pass
        out.append(kept)
    out.sort(key=lambda e: e["when"])
    waiting = [e for e in out if "done" not in e]
    finished = [e for e in out if "done" in e]
    # Keep every reminder still to come; only the finished ones are forgotten once there are many.
    return sorted(waiting + finished[-MAX_FINISHED:], key=lambda e: e["when"])[:MAX_REMINDERS]


def waiting(entries):
    """The ones still to come."""
    return [e for e in valid(entries) if "done" not in e]


def finished(entries):
    """The ones already shown, newest last."""
    return [e for e in valid(entries) if "done" in e]


def due(entries, now=None):
    """(the ones that have just come round, every reminder with those marked done)."""
    moment = (now or datetime.datetime.now()).isoformat(timespec="seconds")
    entries = valid(entries)
    ready = [e for e in entries if "done" not in e and e["when"] <= moment]
    marked = [dict(e, done=moment) if e in ready else e for e in entries]
    return ready, valid(marked)


def describe(when, now=None):
    """"in 5 minutes" or "tomorrow at 09:00", for telling the user what was understood."""
    now = now or datetime.datetime.now()
    if isinstance(when, str):
        when = datetime.datetime.fromisoformat(when)
    seconds = (when - now).total_seconds()
    if seconds < 90:
        return f"in {max(1, round(seconds))} seconds"
    if seconds < 3600:
        return f"in {round(seconds / 60)} minutes"
    if when.date() == now.date():
        return f"at {when:%H:%M}"
    if when.date() == (now + datetime.timedelta(days=1)).date():
        return f"tomorrow at {when:%H:%M}"
    return f"{when:%d %b at %H:%M}"
