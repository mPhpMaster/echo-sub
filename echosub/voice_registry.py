# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""What a spoken command is allowed to reach: a fixed list of apps, sites and media keys.

Nothing here is ever built from what was said. Speech only ever picks one of these entries, and
what is written here is the whole of what voice commands can do to this PC.
"""

from . import voice_vocabulary as vocabulary

CREATE_NO_WINDOW = 0x08000000
WM_CLOSE = 0x0010

# Only these programs may be started or closed. Both are ordinary Windows accessories.
# "close": "polite" asks the window to close (unsaved work is safe); "force" ends the process,
# which is only used for an app that keeps nothing and ignores the polite request.
APPS = {
    "calculator": {
        "launch": "calc.exe", "close": "force",
        "processes": ("CalculatorApp.exe", "Calculator.exe", "calc.exe"),
    },
    "notepad": {
        "launch": "notepad.exe", "close": "polite", "processes": ("Notepad.exe", "notepad.exe"),
    },
    "paint": {
        "launch": "mspaint.exe", "close": "polite", "processes": ("mspaint.exe", "PaintApp.exe"),
    },
    "files": {  # File Explorer: only its folder windows are closed, never the desktop or taskbar
        "launch": "explorer.exe", "close": "polite", "processes": ("explorer.exe",),
        "window_classes": ("CabinetWClass", "ExploreWClass"),
    },
    "settings": {
        "launch": "ms-settings:", "close": "polite", "processes": ("SystemSettings.exe",),
    },
    "task manager": {
        "launch": "taskmgr.exe", "close": "polite", "processes": ("Taskmgr.exe", "taskmgr.exe"),
    },
    "snipping tool": {
        "launch": "snippingtool.exe", "close": "polite",
        "processes": ("SnippingTool.exe", "ScreenSketch.exe", "snippingtool.exe"),
    },
    "on-screen keyboard": {
        "launch": "osk.exe", "close": "force", "processes": ("osk.exe",),
    },
    "magnifier": {
        "launch": "magnify.exe", "close": "force", "processes": ("Magnify.exe", "magnify.exe"),
    },
    "character map": {
        "launch": "charmap.exe", "close": "polite", "processes": ("charmap.exe",),
    },
    "chrome": {
        "launch": "chrome.exe", "close": "polite", "processes": ("chrome.exe",),
    },
    "edge": {
        "launch": "msedge.exe", "close": "polite", "processes": ("msedge.exe",),
    },
    "firefox": {
        "launch": "firefox.exe", "close": "polite", "processes": ("firefox.exe",),
    },
    "vlc": {
        "launch": "vlc.exe", "close": "polite", "processes": ("vlc.exe",),
        "paths": (r"%ProgramFiles%\VideoLAN\VLC\vlc.exe", r"%ProgramFiles(x86)%\VideoLAN\VLC\vlc.exe"),
    },
    "vs code": {
        "launch": "code.exe", "close": "polite", "processes": ("Code.exe",),
        "paths": (r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe",
                  r"%ProgramFiles%\Microsoft VS Code\Code.exe"),
    },
    "discord": {
        "launch": "discord.exe", "close": "polite", "processes": ("Discord.exe",),
        "paths": (r"%LOCALAPPDATA%\Discord\Update.exe",),
        "arguments": ("--processStart", "Discord.exe"),
    },
    "steam": {
        "launch": "steam.exe", "close": "polite", "processes": ("steam.exe",),
        "paths": (r"%ProgramFiles(x86)%\Steam\steam.exe", r"%ProgramFiles%\Steam\steam.exe"),
    },
    "spotify": {
        "launch": "spotify.exe", "close": "polite", "processes": ("Spotify.exe",),
        "paths": (r"%APPDATA%\Spotify\Spotify.exe",),
    },
}
for _name, _app in APPS.items():
    _app["words"] = vocabulary.APP_WORDS[_name]

# Websites EchoSub may open. The address is written here and never built from what was said; only
# the name is recognized, and it is handed to Windows' own browser handler.
LINKS = {
    "youtube": {"url": "https://www.youtube.com/", "title": "YouTube"},
    "google": {"url": "https://www.google.com/", "title": "Google"},
}
for _name, _link in LINKS.items():
    _link["words"] = vocabulary.LINK_WORDS[_name]

OPEN_WORDS = vocabulary.OPEN_WORDS
CLOSE_WORDS = vocabulary.CLOSE_WORDS

MEDIA_NOUNS = (
    "music", "song", "audio", "video", "media", "موسيقى", "موسيقي", "الموسيقي", "اغنيه", "الأغنية",
    "الاغنيه", "صوت", "فيديو", "الفيديو",
)
MEDIA_ACTIONS = (
    ("media_play_pause", "play_pause", "Play or pause", (
        "play", "pause", "شغل", "joue", "pause", "reproducir", "pausa", "spielen", "wiedergabe", "çal", "oynat",
        "играй", "включи", "пауза", "پخش", "播放", "暂停", "再生", "재생",
    )),
    ("media_stop", "stop", "Stop playback", (
        "stop", "وقف", "اوقف", "طفي", "إيقاف", "arret", "detener", "anhalten", "dur", "останови", "توقف", "停止", "정지",
    )),
    ("media_next", "next", "Next track", (
        "next", "skip", "التالي", "التاليه", "التالية", "غير", "suivant", "siguiente", "nächste", "sonraki",
        "следующая", "التاليه", "بعدی", "下一首", "次", "다음",
    )),
    ("media_previous", "previous", "Previous track", (
        "previous", "back", "السابق", "السابقة", "رجوع", "precedent", "anterior", "vorherige", "önceki",
        "предыдущая", "قبلی", "上一首", "前", "이전",
    )),
    ("media_mute", "mute", "Mute audio", ("mute", "كتم", "اكتم", "silence", "silencio", "stumm", "sessiz",
                                          "без звука", "بی صدا", "静音", "음소거")),
    ("media_volume_up", "volume_up", "Volume up", (
        "volume up", "ارفع الصوت", "علي الصوت", "monte le son", "sube el volumen", "lautstärke hoch",
        "sesi aç", "громче", "صدا را زیاد کن", "音量を上げ", "볼륨 올려",
    )),
    ("media_volume_down", "volume_down", "Volume down", (
        "volume down", "وطي الصوت", "خفض الصوت", "baisse le son", "baja el volumen", "lautstärke runter",
        "sesi kıs", "тише", "صدا را کم کن", "音量を下げ", "볼륨 내려",
    )),
)
MEDIA_VIRTUAL_KEYS = {
    "play_pause": 0xB3, "stop": 0xB2, "next": 0xB0, "previous": 0xB1, "mute": 0xAD,
    "volume_up": 0xAF, "volume_down": 0xAE,
}
