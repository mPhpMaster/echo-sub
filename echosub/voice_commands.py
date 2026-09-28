# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Spoken commands, limited to a fixed list of harmless actions.

Safety rules, in order of importance:

1. **A closed list.** Only the actions in `COMMANDS` and the apps in `APPS` can ever run. Nothing
   from the transcript is passed to a shell, used as a file name, or turned into a command line:
   what is heard only ever *selects* one of the entries written in this file.
2. **Nothing destructive.** The list holds only: opening or closing ordinary Windows apps and
   EchoSub's own caption controls. An optional setting permits only up to six individual A-Z or
   0-9 key presses; shortcuts, Enter, navigation, terminal access, and system keys remain absent.
   Shutting down or restarting the PC, deleting or moving files, changing Windows settings, and
   running any program by transcript are deliberately absent, and must stay absent.
3. **Closing is as gentle as the app allows.** Notepad can hold text you have not saved, so it is
   asked to close the way the X button does, and it may still ask you to save. Calculator keeps
   nothing, and it ignores a polite request (it is a Store app), so it is closed outright.
4. **A wake word.** EchoSub listens to whatever the PC plays, so a video saying "open the
   calculator" must not open it. A command only counts when the wake word comes first and the
   command follows within a few words. The one exception is an on-screen answer, which does
   nothing but write a line the user wrote into the user's own caption box, and so is recognized
   wherever the phrase is heard.
5. **Off unless asked for.** The feature is disabled by default, and a command is ignored while the
   engine is paused.
"""
import logging
import re

from . import screen_replies, voice_vocabulary as vocabulary
from .voice_actions import (  # noqa: F401 (kept where callers and tests expect them)
    AppNotInstalled, CommandRunner, REPEAT_COOLDOWN_SEC, close_program, open_link, press_keys,
    resolve_program, send_media_key, start_program,
)
from .voice_registry import (
    APPS, CLOSE_WORDS, LINKS, MAX_PRESS_KEYS, MEDIA_ACTIONS, MEDIA_NOUNS, OPEN_WORDS, SAFE_PRESS_KEY,
)

log = logging.getLogger(__name__)

DEFAULT_WAKE_WORDS = (
    "echo sub", "echosub", "إيكو صب", "ايكو صب", "pc", "computer", "بي سي", "alexa", "اليكسا",
)
MAX_WORDS_AFTER_WAKE = 8   # the command must follow the wake word closely
MAX_WINDOW_CHARS = 60      # ...and in languages written without spaces, this many characters
PREFIX_MATCH_MIN_CHARS = 5  # from this length a word may carry a grammatical ending
CREATE_NO_WINDOW = 0x08000000
WM_CLOSE = 0x0010

HELP_WORDS = ("help", "commands", "اوامر", "الأوامر", "مساعده", "مساعدة")
PRESS_WORDS = ("press", "اضغط", "اكبس")
CAPTION_COMMANDS = (
    {"key": "voice_help", "action": "help", "target": "help", "label": "Voice command help"},
    {"key": "toggle_captions", "action": "app", "target": "toggle", "label": "Captions switched"},
    {"key": "pause_captions", "action": "app", "target": "pause", "label": "Captions paused"},
    {"key": "resume_captions", "action": "app", "target": "resume", "label": "Captions resumed"},
    {"key": "hide_captions", "action": "app", "target": "hide", "label": "Caption box hidden"},
    {"key": "show_captions", "action": "app", "target": "show", "label": "Caption box shown"},
    {"key": "clear_captions", "action": "app", "target": "clear", "label": "Captions cleared"},
)

MEDIA_COMMANDS = tuple(
    {"key": key, "action": "media", "target": target, "label": label}
    for key, target, label, _words in MEDIA_ACTIONS
)

LINK_COMMANDS = tuple(
    {"key": f"open_{name}", "action": "open_link", "target": name, "label": f"{link['title']} opened"}
    for name, link in LINKS.items()
)

APP_COMMANDS = tuple(
    {"key": f"{verb}_{name}", "action": f"{verb}_app", "target": name,
     "label": f"{name.title()} {'opened' if verb == 'open' else 'closed'}"}
    for name in APPS for verb in ("open", "close")
)

COMMANDS = CAPTION_COMMANDS + MEDIA_COMMANDS + LINK_COMMANDS + APP_COMMANDS

_ARABIC_MARKS = re.compile(r"[ً-ْـ]")
_PUNCTUATION = re.compile(r"[^\w\s؀-ۿ]+", re.UNICODE)


def normalize(text):
    """Lower-case, drop punctuation and Arabic diacritics, and even out spacing, alifs and taa."""
    text = _ARABIC_MARKS.sub("", str(text).lower())
    text = _PUNCTUATION.sub(" ", text)
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ة", "ه").replace("ى", "ي")
    return re.sub(r"\s+", " ", text).strip()


def command(key):
    return next(c for c in COMMANDS if c["key"] == key)


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


def _app_command(window):
    """An app command is 'a word for open/close' plus 'a word for the app', in any order."""
    for name, app in APPS.items():
        if _first_position(window, app["words"]) < 0:
            continue
        opening = _first_position(window, OPEN_WORDS)
        closing = _first_position(window, CLOSE_WORDS)
        if opening < 0 and closing < 0:
            continue
        wants_close = closing >= 0 and (opening < 0 or closing < opening)
        return command(f"{'close' if wants_close else 'open'}_{name}")
    return None


def _echosub_command(window):
    """A caption command is 'a word for the action', with or without a word for captions.

    "pause the captions" and a bare "pause" both mean the captions: nothing else here is paused.
    A word that also belongs to a media phrase ("stop the music") is left to the media commands.
    """
    named = _first_position(window, vocabulary.CAPTION_WORDS) >= 0
    if not named and _first_position(window, MEDIA_NOUNS) >= 0:
        return None
    best, best_at = None, -1
    for key, words in vocabulary.CAPTION_ACTIONS:
        at = _first_position(window, words)
        if at >= 0 and (best_at < 0 or at < best_at):
            best, best_at = key, at
    if best is None or (not named and best_at > 0):
        return None  # a bare action word only counts when it comes first
    return command(best)


def _link_command(window):
    """Opening one of the fixed websites: the name is recognized, the address is written in code."""
    if _first_position(window, OPEN_WORDS) < 0:
        return None
    for name, link in LINKS.items():
        if _first_position(window, link["words"]) >= 0:
            return command(f"open_{name}")
    return None


def _help_command(window):
    return command("voice_help") if _first_position(window, HELP_WORDS) >= 0 else None


def _press_command(window):
    """Return a short, explicitly safe key sequence, never a shortcut or system key."""
    parts = window.split()
    if not parts or parts[0] not in PRESS_WORDS:
        return None
    keys = tuple(part.upper() for part in parts[1:])
    if not keys or len(keys) > MAX_PRESS_KEYS or not all(SAFE_PRESS_KEY.fullmatch(key.lower()) for key in keys):
        return None
    return {"key": f"press:{''.join(keys)}", "action": "press_keys", "target": keys,
            "label": f"Pressed {' '.join(keys)}"}


def _media_command(window):
    """Recognize fixed Windows media keys; never target or automate a specific application."""
    for key, target, label, words in MEDIA_ACTIONS:
        if _first_position(window, words) < 0:
            continue
        if target in ("play_pause", "stop") and _first_position(window, MEDIA_NOUNS) < 0:
            continue
        # The wake word already scopes this to EchoSub. Allow short, natural phrases such as
        # “Maya stop” and “مايا ارفع الصوت” without requiring the word "music".
        return command(key)
    return None


def valid_custom_commands(entries):
    """Normalize stored mappings; custom speech can select only an approved built-in action."""
    approved = {item["key"] for item in COMMANDS if item["action"] != "help"}
    result, seen = [], set()
    for entry in entries if isinstance(entries, list) else ():
        if not isinstance(entry, dict):
            continue
        phrase = normalize(entry.get("phrase", ""))
        key = entry.get("command")
        if not phrase or key not in approved or phrase in seen:
            continue
        if len(phrase) > MAX_WINDOW_CHARS or len(phrase.split()) > MAX_WORDS_AFTER_WAKE:
            continue
        seen.add(phrase)
        result.append({"phrase": phrase, "command": key})
    return result[:20]


def _custom_command(window, entries):
    """Exact phrase matching prevents ordinary speech from triggering a custom mapping."""
    for entry in valid_custom_commands(entries):
        if window == entry["phrase"]:
            return command(entry["command"])
    return None


def help_text(custom_commands=()):
    """Brief, local-only help shown after the wake word; no sensitive data is included."""
    app_names = ", ".join(sorted(APPS))
    phrases = [entry["phrase"] for entry in valid_custom_commands(custom_commands)]
    custom = f" Custom: {', '.join(phrases)}." if phrases else ""
    sites = ", ".join(link["title"] for link in LINKS.values())
    return ("Say open or close followed by an approved app: " + app_names +
            ". Open a site with: " + sites +
            ". You can also pause, resume, hide, show, or clear captions; say the wake word on its own to "
            "switch captions off or back on; control media with play, stop, next, previous, mute, volume up, "
            "or volume down." + custom)


def find(text, wake_words=DEFAULT_WAKE_WORDS, **options):
    """The command in `text`, or None. The wake word must come first, then the command."""
    return find_detail(text, wake_words, **options)[0]


def find_detail(text, wake_words=DEFAULT_WAKE_WORDS, custom_commands=(), allow_key_presses=False,
                reply_pairs=()):
    """(command, what was said after the wake word).

    The second value lets the app say "I heard you but that was not a command", which is very
    different from not having been spoken to at all.

    One exception to the wake word: a phrase the user wrote in the on-screen answers is recognized
    on its own, because the only thing it can do is show that user's own text.
    """
    spoken = normalize(text)
    # Your own phrases need no wake word: an answer only ever writes a line you wrote yourself into
    # your own caption box, so hearing it anywhere in the sentence is safe. Case, punctuation and
    # Arabic spelling are already evened out by `normalize`, on both sides of the comparison.
    reply = screen_replies.find_reply(spoken, reply_pairs, position_of)
    if reply is not None:
        return screen_replies.reply_command(reply), reply["phrase"]
    heard = None
    for wake in wake_words:
        wake = normalize(wake)
        if not wake:
            continue
        if spoken == wake:
            # Just the name, nothing else: switch the captions off, or back on. A name inside an
            # ordinary sentence is not this, which is why the whole caption has to be the name.
            return command("toggle_captions"), wake
        # Whole words only: a short wake word such as "da" must not fire inside "today"
        for match in re.finditer(rf"(?<!\w){re.escape(wake)}(?!\w)", spoken):
            tail = spoken[match.end():].strip()
            if not tail:
                continue
            window = " ".join(tail.split()[:MAX_WORDS_AFTER_WAKE])[:MAX_WINDOW_CHARS]
            found = (_help_command(window) or _custom_command(window, custom_commands) or
                     _echosub_command(window) or _link_command(window) or _app_command(window) or
                     _media_command(window))
            if found is None and allow_key_presses:
                found = _press_command(window)
            if found is not None:
                return found, window
            heard = heard or window
            log.info("Heard the wake word but no command in %r", window)
    return None, heard
