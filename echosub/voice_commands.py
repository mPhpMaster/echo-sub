# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Spoken commands, limited to a fixed list of harmless actions.

Safety rules, in order of importance:

1. **A closed list.** Only the actions in `COMMANDS` and the apps in `APPS` can ever run. Nothing
   from the transcript is passed to a shell, used as a file name, or turned into a command line:
   what is heard only ever *selects* one of the entries written in this file.
2. **Nothing destructive by itself.** The list holds only: opening or closing ordinary Windows
   apps and EchoSub's own caption controls. Shutting down or restarting the PC, deleting or moving
   files, changing Windows settings, and running any program named in a transcript are absent, and
   must stay absent.

   Three settings widen this, each off by default and each asked for deliberately: typing what was
   said, starting a program line written in the settings, and pressing named keys, which does
   include the Windows key, Escape and combinations such as Windows+R. Taken together those three
   can reach a great deal of Windows, which is why each is its own switch, why the PC's own sound
   must still say the wake word first, and why every command is shown with a countdown that one
   click calls off.
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

from . import (
    reminders, screen_replies, voice_destinations, voice_keys, voice_typing,
    voice_vocabulary as vocabulary,
)
from .voice_actions import (  # noqa: F401 (kept where callers and tests expect them)
    AppNotInstalled, CommandRunner, REPEAT_COOLDOWN_SEC, close_program, open_link, press_keys,
    resolve_program, send_media_key, start_program,
)
from .voice_registry import (
    APPS, CLOSE_WORDS, LINKS, MEDIA_ACTIONS, MEDIA_NOUNS, OPEN_WORDS,
)  # noqa: F401 (MEDIA_ACTIONS is used by command_starters)

log = logging.getLogger(__name__)

DEFAULT_WAKE_WORDS = (
    "echo sub", "echosub", "إيكو صب", "ايكو صب", "pc", "computer", "بي سي", "alexa", "اليكسا",
)
MAX_WORDS_AFTER_WAKE = 8   # the command must follow the wake word closely
MAX_WINDOW_CHARS = 60      # ...and in languages written without spaces, this many characters
PREFIX_MATCH_MIN_CHARS = 5  # from this length a word may carry a grammatical ending
MAX_RUN_CHARS = 500         # a program and its arguments, typed by you in the settings
CREATE_NO_WINDOW = 0x08000000
WM_CLOSE = 0x0010

HELP_WORDS = ("help", "commands", "اوامر", "الأوامر", "مساعده", "مساعدة")
PRESS_WORDS = ("press", "اضغط", "اكبس")
CAPTION_COMMANDS = (
    {"key": "voice_help", "action": "help", "target": "help", "label": "Voice command help"},
    {"key": "toggle_captions", "action": "app", "target": "toggle", "label": "Captions switched"},
    {"key": "press_enter", "action": "press_enter", "target": "enter", "label": "Pressed Enter"},
    # Only your own microphone may say this, so nobody on a call can switch your microphone for you.
    {"key": "show_reminders", "action": "app", "target": "reminders", "label": "Reminders"},
    {"key": "toggle_mic", "action": "app", "target": "mic", "label": "Microphone switched", "mic_only": True},
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
    """An app command is 'a word for open/close' plus 'a word for the app', in any order.

    The name on its own opens it too — "echo sub, paint" — but only when that is the whole of what
    was said after the wake word, so talking about Paint does not start it.
    """
    for name, app in APPS.items():
        if _first_position(window, app["words"]) < 0:
            continue
        opening = _first_position(window, OPEN_WORDS)
        closing = _first_position(window, CLOSE_WORDS)
        if opening < 0 and closing < 0:
            if any(window == normalize(word) for word in app["words"]):
                return command(f"open_{name}")
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


def _reminder_command(window, raw_text):
    """"Remind me in five minutes to ..." — the time must be said, or nothing is set.

    "My reminders" opens the list instead, since that asks about them rather than setting one.
    """
    if _first_position(window, reminders.LIST_WORDS) >= 0:
        return command("show_reminders")
    at = _first_position(window, reminders.REMIND_WORDS)
    if at < 0:
        return None
    said = _spoken_tail(raw_text, reminders.REMIND_WORDS)
    parsed = reminders.parse(said) if said else None
    if parsed is None:
        return None
    when, what = parsed
    return {"key": "set_reminder", "action": "reminder", "target": when.isoformat(timespec="seconds"),
            "label": f"Reminder {reminders.describe(when)}" + (f": {what}" if what else ""),
            "what": what}


def _ask_command(window, raw_text, words):
    """"Ask ..." — everything after the trigger word is the question, exactly as it was heard."""
    if _first_position(window, words) < 0:
        return None
    question = " ".join(_spoken_tail(raw_text, words).split())
    if not question:
        return None
    return {"key": "ask_ai", "action": "ask_ai", "target": question[:500], "label": f"Ask AI: {question[:80]}"}


def _typing_command(window, raw_text):
    """"Type ..." — everything after that word becomes the text, exactly as it was heard."""
    if _first_position(window, vocabulary.TYPE_WORDS) < 0:
        return None
    said = voice_typing.safe_text(_spoken_tail(raw_text, vocabulary.TYPE_WORDS))
    if not said:
        return None
    return {"key": "type_text", "action": "type_text", "target": said, "label": f"Typed {said}"}


def _enter_command(window):
    """"Press enter" — the one key that typed text is never allowed to contain by itself."""
    if _first_position(window, PRESS_WORDS) < 0 or _first_position(window, vocabulary.ENTER_WORDS) < 0:
        return None
    return command("press_enter")


def _go_command(window, raw_text, folders):
    """"Go to ..." or "play ..." — one of your places, or a web address read out of what followed.

    Nothing happens unless what followed names a place you saved or a real web address, so "play"
    with anything else after it falls through to the media keys, where it still means play.
    """
    if _first_position(window, vocabulary.GO_WORDS) >= 0:
        said = _spoken_tail(raw_text, vocabulary.GO_WORDS)
        found = voice_destinations.destination_command(said, folders) if said else None
        if found is not None:
            return found
    if _first_position(window, vocabulary.PLAY_WORDS) >= 0:
        # "Play ..." reaches only the places you added yourself: "play music" means press play,
        # not open your Music folder, and a web address is not something one plays.
        said = _spoken_tail(raw_text, vocabulary.PLAY_WORDS)
        if said:
            return voice_destinations.destination_command(said, folders, windows_too=False, allow_url=False)
    return None


# Words common enough in ordinary speech that using one as a wake word means EchoSub will think
# it is being spoken to all day long. "PC" is the one that catches people out: it is in every
# other sentence of a technology video.
RISKY_WAKE_WORDS = {
    "pc", "computer", "laptop", "windows", "ok", "okay", "hey", "yes", "no", "now", "stop", "go",
    "app", "game", "video", "sound", "audio", "music", "screen", "phone", "mic", "test", "one",
    "بي سي", "بيسي", "كمبيوتر", "لاب توب", "نعم", "لا", "الان", "شاشه", "صوت",
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
        parts.append("“" + "”, “".join(risky) +
                     "” turns up in ordinary speech, so anything your PC plays will set it off often")
    if short:
        parts.append("“" + "”, “".join(short) + "” is very short, which is easily misheard")
    return ". ".join(parts) + ". Something two words long and unusual is heard far less by accident."


def is_cancel(text):
    """Did someone just say "no"? Only at the start of what was said, so a sentence that merely
    contains the word does not call off a command that is waiting.
    """
    spoken = normalize(text)
    return any(spoken == word or spoken.startswith(word + " ")
               for word in (normalize(w) for w in vocabulary.CANCEL_WORDS) if word)


def _mic_command(window):
    """"Mute my microphone", and the same words again to bring it back."""
    if _first_position(window, vocabulary.MIC_WORDS) < 0:
        return None
    if _first_position(window, vocabulary.MIC_ACTION_WORDS) < 0:
        return None
    return command("toggle_mic")


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
    """"Press <keys>" — one key or a combination, and only words that name a key."""
    parts = window.split()
    if not parts or parts[0] not in PRESS_WORDS:
        return None
    words = tuple(parts[1:])
    if voice_keys.resolve(words) is None:
        return None  # something that is not a key was said; press nothing at all
    return {"key": f"press:{'+'.join(words)}", "action": "press_keys", "target": words,
            "label": f"Pressed {voice_keys.label(words)}"}


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
    """Normalize stored mappings: a phrase picks an approved action, or a program you wrote down.

    The program line is only ever the text typed in the settings. Nothing that was *said* reaches
    it: speech chooses which of your own saved lines to start, and can never compose one.
    """
    approved = {item["key"] for item in COMMANDS if item["action"] != "help"}
    result, seen = [], set()
    for entry in entries if isinstance(entries, list) else ():
        if not isinstance(entry, dict):
            continue
        phrase = normalize(entry.get("phrase", ""))
        key = entry.get("command")
        run = " ".join(str(entry.get("run", "")).split())[:MAX_RUN_CHARS]
        if not phrase or phrase in seen or (not run and key not in approved):
            continue
        if len(phrase) > MAX_WINDOW_CHARS or len(phrase.split()) > MAX_WORDS_AFTER_WAKE:
            continue
        seen.add(phrase)
        result.append({"phrase": phrase, "run": run} if run else {"phrase": phrase, "command": key})
    return result[:20]


def run_command(entry):
    """A command that starts one of the program lines saved in the settings."""
    return {"key": f"run:{entry['phrase']}", "action": "run", "target": entry["run"],
            "label": f"Started {entry['run']}"}


def _custom_command(window, entries):
    """Your own phrase, said anywhere after the wake word.

    It used to have to be the whole sentence and nothing else, which meant "run music" missed a
    phrase saved as "music" — the commonest way these were lost. Whole words still, so a phrase
    saved as "music" is not found inside "musical".
    """
    for entry in valid_custom_commands(entries):
        if window == entry["phrase"] or _without_a_starting_word(window) == entry["phrase"]:
            return run_command(entry) if "run" in entry else command(entry["command"])
    return None


def _without_a_starting_word(window):
    """The sentence with a leading "open", "run" or "play" taken off, if it has one.

    Only those: "close music" and "go to music" mean something else entirely, and must not be
    read as a request to start the thing again.
    """
    for word in sorted(set(OPEN_WORDS) | set(vocabulary.PLAY_WORDS), key=len, reverse=True):
        start = normalize(word) + " "
        if window.startswith(start):
            return window[len(start):].strip()
    return window


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


def command_starters():
    """Every word that may *begin* a spoken command: the doing words, in all the languages."""
    words = set(OPEN_WORDS) | set(CLOSE_WORDS) | set(HELP_WORDS) | set(PRESS_WORDS)
    from .ai_assistant import ASK_WORDS

    words |= set(vocabulary.GO_WORDS) | set(vocabulary.TYPE_WORDS) | set(ASK_WORDS)
    for _key, action_words in vocabulary.CAPTION_ACTIONS:
        words |= set(action_words)
    for _key, _target, _label, action_words in MEDIA_ACTIONS:
        words |= set(action_words)
    return tuple(words)


def _match(window, text, custom_commands, allow_key_presses, folders, allow_typing=False, allow_ai=False):
    """The command in one window of speech, or None. The order decides what wins a tie.

    Typing comes early on purpose: "type open the calculator" is a sentence to write down, not a
    program to start, so the word "type" claims everything after it.
    """
    found = (_help_command(window) or _custom_command(window, custom_commands)
             or _reminder_command(window, text))
    if found is None and allow_ai:
        # Like "type", the trigger word claims everything after it. `allow_ai` may carry the user's
        # own trigger words; True means the built-in ones.
        from .ai_assistant import ASK_WORDS

        words = tuple(allow_ai) if isinstance(allow_ai, (tuple, list)) and allow_ai else ASK_WORDS
        found = _ask_command(window, text, words)
    if found is None and allow_typing:
        # Typing is tried first, so "type ... and press enter" writes that whole sentence out.
        # Enter on its own is a separate thing to say, which is the point of it being separate.
        found = _typing_command(window, text) or _enter_command(window)
    found = (found or _mic_command(window) or _echosub_command(window) or _link_command(window) or
             _go_command(window, text, folders) or _app_command(window) or
             _media_command(window))
    if found is None and allow_key_presses:
        found = _press_command(window)
    return found


def find_detail(text, wake_words=DEFAULT_WAKE_WORDS, custom_commands=(), allow_key_presses=False,
                reply_pairs=(), folders=(), require_wake=True, allow_typing=False, allow_ai=False):
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
            found = _match(window, text, custom_commands, allow_key_presses, folders, allow_typing, allow_ai)
            if found is not None:
                return found, window
            heard = heard or window
            log.info("Heard the wake word but no command in %r", window)
    if not require_wake and heard is None:
        # Your own microphone, where the name is optional. Said without one, a command has to
        # *begin* the sentence: "open the calculator" is an order, while "we could open the
        # calculator later" is you talking, and telling those apart is the whole job here.
        window = " ".join(spoken.split()[:MAX_WORDS_AFTER_WAKE])[:MAX_WINDOW_CHARS]
        found = _custom_command(window, custom_commands)  # one of your own phrases, matched in full
        starters = command_starters()
        if isinstance(allow_ai, (tuple, list)):
            starters += tuple(allow_ai)  # the user's own trigger words begin a command as well
        if found is None and _first_position(window, starters) == 0:
            found = _match(window, text, custom_commands, allow_key_presses, folders, allow_typing, allow_ai)
        # Nothing is reported as "heard but not understood": that would fire on every sentence.
        return found, None
    return None, heard
