# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
import json
import os
import sys

from . import APP_ID

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(PACKAGE_DIR, "assets")
FROZEN = getattr(sys, "frozen", False)  # running from the PyInstaller build / installed app


def _data_dir():
    """Where settings, models, logs and transcripts live.

    ECHOSUB_DATA_DIR overrides it. The installed app uses %LOCALAPPDATA%\\EchoSub (Program Files is
    read-only); running from source keeps everything in the project folder.
    """
    override = os.environ.get("ECHOSUB_DATA_DIR")
    if override:
        return os.path.abspath(override)
    if FROZEN:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, APP_ID)
    return os.path.dirname(PACKAGE_DIR)


DATA_DIR = _data_dir()
ROOT = DATA_DIR  # kept for older imports
os.makedirs(DATA_DIR, exist_ok=True)
CONFIG_PATH = os.path.join(DATA_DIR, "settings.json")
MODELS_DIR = os.environ.get("ECHOSUB_MODELS_DIR") or os.path.join(DATA_DIR, "models")

WHISPER_MODELS = {
    "large-v3-turbo": "Large v3 Turbo — best balance (recommended for GTX 1060)",
    "large-v3": "Large v3 — most accurate, slower",
    "medium": "Medium — good accuracy",
    "small": "Small — fast",
    "base": "Base — very fast, less accurate",
}

TRANSLATORS = {
    "nllb-600m": "NLLB 600M — offline (fast)",
    "nllb-1.3b": "NLLB 1.3B — offline (more accurate)",
    "google": "Google Translate — needs internet",
    "none": "No translation (original text only)",
}

NLLB_REPOS = {
    "nllb-600m": "JustFrederik/nllb-200-distilled-600M-ct2-int8",
    "nllb-1.3b": "JustFrederik/nllb-200-distilled-1.3B-ct2-int8",
}

DEFAULTS = {
    "target_lang": "ar",
    "source_lang": "auto",
    "whisper_model": "large-v3-turbo",
    "device": "cuda",
    "translator": "nllb-600m",
    "translate_same_language": True,      # also translate when speech is already in the caption language
    "arabic_diacritics": "off",           # off | translation | original | both — add harakat to Arabic text
    "audio_device": "default",
    "show_original": True,
    "show_partial": True,
    "light_mode": False,                  # faster on a busy PC: a smaller speech model, no live text
    "light_model": "small",               # which model light mode uses
    "mic_enabled": False,                 # also caption what your microphone hears
    "mic_device": "default",              # microphone to use; "default" follows Windows
    "mic_label": "You",                   # shown on the microphone's captions
    "mic_color": "#8AD7FF",               # their colour in the caption box
    "mic_commands": True,                 # spoken commands may come from the microphone too
    "font_family": "Segoe UI",
    # translation text
    "font_size": 28,
    "text_color": "#FFFFFF",
    "translation_bold": True,
    "translation_label": "flag_code",     # same choices as original_label
    "translation_label_position": "before",
    "label_separator": True,               # a dot between a language label and the words it labels
    "translation_label_size": 100,         # % of the translation's own text size; flag scales with it
    # original-language text
    "original_font_size": 17,
    "original_color": "#FFD966",
    "original_bold": False,
    "original_label": "flag_code",        # none | code | name | flag | flag_code | flag_name
    "original_label_position": "before",  # before | after | above | below (before/after follow reading direction)
    "original_label_size": 100,            # % of the original text's size
    # layout
    "text_align": "center",               # center | left | right | reading
    "box_position": "bottom-center",      # <top|middle|bottom>-<left|center|right>, or custom (dragged)
    "box_screen": "",                     # screen name; empty = primary screen
    "box_margin": 60,                     # px from the screen edge(s) the box is anchored to
    "box_width_pct": 70,                  # box width as % of the screen width (the maximum when autosizing)
    "box_autosize": False,                # shrink/grow the box to fit its text
    "box_radius": 14,                     # px, rounded corners of the box background (0 = square)
    "box_padding_x": 24,                  # px between the box edge and the text, left/right
    "box_padding_y": 12,                  # px, top/bottom
    "copy_buttons": True,                 # a copy button on each caption row while the mouse is over the box
    "box_scale": 100,                     # %, size (zoom) of the box and its text; Shift + wheel over the box
    "caption_animation": "slide",         # slide | fade | none
    "caption_animation_ms": 250,
    # spacing
    "line_height": 115,        # % line height inside wrapped text
    "entry_spacing": 10,       # px between caption lines
    "original_gap": 2,         # px between original and its translation
    # speakers
    "speaker_detection": True,
    "speaker_threshold": 0.55,
    "speaker_color_target": "both",  # translation | original | both
    "speaker_colors": ["#FFFFFF", "#7FDBFF", "#FFD966", "#9CFF9C", "#FF9EC4", "#C9A7FF", "#FFB066", "#A0E0D0"],
    "bg_opacity": 150,
    "max_lines": 2,
    "clear_after_sec": 3,
    "vad_threshold": 0.45,
    "silence_sec": 0.6,
    "max_segment_sec": 10.0,
    "audio_backlog_sec": 600,           # temporary disk buffer used to catch up after slow recognition
    "audio_backlog_dir": "",            # where to write it; empty = the Windows temp folder
    "save_transcripts": False,
    "update_checks": True,
    "voice_commands": False,              # spoken commands from a fixed, harmless list (off by default)
    "voice_command_wake": "echo sub",     # a command only counts after this wake word
    "voice_custom_commands": [],           # user phrases mapped to an approved built-in action
    "voice_key_presses": False,            # allow short A-Z / 0-9 press commands after the wake word
    "ai_enabled": False,                   # "ask ..." sends recent captions and the question to an AI
    "ai_provider": "claude",               # claude | openai | gemini | deepseek | lmstudio
    "ai_profiles": {},                     # per service: {"model", "base_url", "key" (encrypted)}
    "ai_context_lines": 20,                # how many recent captions go with a question
    "ai_context_who": "everyone",          # everyone | me
    "ai_trigger": "ask, اسأل",             # words after the wake word that start a question (comma-separated)
    "ai_color": "#C9B6FF",                 # the colour an AI's answer is shown in
    "ai_label": "AI",                      # the word shown in front of an AI's answer
    "ai_auto_answer": False,               # answer questions heard in the captions without being asked
    "ai_auto_from": "everyone",            # everyone | others | me: whose questions are answered that way
    "ai_auto_cooldown": 20,                # seconds between answers given without being asked
    "ai_auto_solo": True,                  # ...and only while one person is talking, not a group
    "ai_answer_seconds": 0,                # how long an answer stays; 0 = long enough to read it
    "ai_font_size": 0,                     # pt for an AI's answer; 0 = the same size as the captions
    "reminders": [],                       # set by voice: {"when": iso time, "what": ...}
    "transcript_fixes": [],                # your own spellings: {"heard": ..., "write": ...}
    "alert_words": [],                     # words to be told about when anything says them
    "alert_sound": True,                   # a notification when a watched word is heard
    "voice_typing": False,                 # "type ..." writes what was said into the active window
    "voice_command_delay": 3,              # seconds to show a command before it runs (0 = at once)
    "mic_wake_word": False,                # your own microphone does not need the wake word
    "voice_go_folders": [],                # folders "go to <name>" may open: {"name": ..., "path": ...}
    "screen_replies": False,               # answer chosen phrases with your own text in the caption box
    "screen_reply_pairs": [],              # [{"phrase": ..., "reply": ...}], written by you
    "screen_reply_seconds": 8,             # how long an answer stays on screen
    "usage_line": False,                   # EchoSub's own CPU, memory, GPU and disk use in the caption box
    "usage_window": False,                 # ...in a small window of its own
    "usage_window_on_top": True,           # ...kept above other windows
    "last_update_check": 0,
    "global_hotkeys": True,
    "click_through": False,
    "overlay_enabled": True,
    "geometry": None,
}

# Window placement and toggles that "Restore defaults" leaves alone
KEEP_ON_RESET = ("geometry", "click_through", "overlay_enabled")

ORIGINAL_LABELS = {
    "none": "Nothing",
    "code": "Language code (EN)",
    "name": "Language name (English)",
    "flag": "Flag",
    "flag_code": "Flag + code",
    "flag_name": "Flag + name",
}
LABEL_POSITIONS = {
    "before": "Before the text",
    "after": "After the text",
    "above": "Above the text",
    "below": "Below the text",
}
TEXT_ALIGNMENTS = {
    "center": "Center",
    "left": "Left",
    "right": "Right",
    "reading": "Follow reading direction (Arabic right, English left)",
}
ARABIC_DIACRITICS = {
    "off": "Off",
    "translation": "On the translation",
    "original": "On the original text",
    "both": "On the translation and the original text",
}
CAPTION_ANIMATIONS = {
    "slide": "Slide: lines glide up, new text slides in and cross-fades",
    "fade": "Fade: lines and changed text fade, without moving",
    "none": "None: change text instantly",
}
BOX_ROWS = ("top", "middle", "bottom")
BOX_COLUMNS = ("left", "center", "right")

# Settings that require reloading models or reopening the audio stream
ENGINE_KEYS = ("whisper_model", "device", "translator", "audio_device", "speaker_detection", "light_mode",
               "audio_backlog_sec", "audio_backlog_dir", "mic_enabled", "mic_device", "light_model")

SPEAKER_COLOR_TARGETS = {
    "both": "Translation and original text",
    "translation": "Translation only",
    "original": "Original text only",
}


def load():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            saved = json.load(f)
    except (OSError, ValueError):
        return cfg
    if "box_position" not in saved and saved.get("geometry"):
        saved["box_position"] = "custom"  # settings from before screen presets existed: keep the dragged spot
    cfg.update(saved)
    return cfg


def save(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
