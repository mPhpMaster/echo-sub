# Changelog

All notable changes to EchoSub are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.3.3] — 2026-10-02

### Fixed
- **English captions are no longer thrown away when Whisper mislabels them.** On a short or noisy clip it often decides plain English is Hindi, Arabic, Russian or Korean; the caption was then dropped for being written in the wrong alphabet, and you saw nothing at all. Such a caption is now kept and its language corrected. Measured against a real session log: 34 of 59 lost captions come back, including “Good game.”, “but you can't do it” and “Can you show us again?”. Speech in another language merely written in Latin letters is still not called English, and text in an unexpected alphabet of its own is still dropped — there is no telling what it was meant to be.


## [1.3.2] — 2026-10-01

### Fixed
- A custom command whose line was just a path to a file, or began with `start`, failed with “the system cannot find the file specified”. `start` is a command-shell word rather than a program, and EchoSub runs these lines without a shell. Both shapes now open the file with the program Windows normally uses for it, the way double-clicking it would. A program that really is missing now says which one.


## [1.3.1] — 2026-10-01

### Added
- The places table takes a row you type yourself: write the word to say and the path, with no file picker involved. A path that is not on this PC is shown in red as you type it. The pickers are still there as “Pick a folder…” and “Pick a file…”, and quotes around a pasted path are dropped.

- **Play a file you picked.** In *Settings → Commands*, “Add file…” next to a name you choose: say that name after “play” or “go to” and the file opens with the program Windows normally uses for it, so a song plays in your own music player. “Play …” reaches only the names you added yourself — “play music” still presses play, while “go to music” opens your Music folder — and a web address is never something it will play.

## [1.3.0] — 2026-09-29

### Added
- **A custom command can start a program you wrote down** (*Settings → Commands*). Add a phrase, choose “Start a program…” and type the program and its arguments, the way you would in a shortcut — `notepad.exe "D:\my notes.txt"`. The line is started **directly, not through a command shell**, so pipes, redirection and `&&` are just characters in an argument and never a second command. Only the line typed in the settings is ever started: nothing that was said is added to it, so speech can pick one of your lines but can never compose one. Approved built-in actions still work in the same table.
- **“Go to …”** (*Settings → Commands*). Say a web address — “go to www.example.com”, or dictated as “go to www dot example dot com” — and it opens in your own browser. Say the name of a folder and it opens in File Explorer: your own Windows folders (desktop, documents, downloads, music, pictures, videos, home) are known already, wherever Windows really keeps them, and you can add your own folders with the name you want to say for each. Only plain `http` and `https` addresses are opened; `file:`, `javascript:`, `data:`, a password in front of the host and anything else are refused. A spoken word never becomes a path — it can only pick one that is already written down.
- **A moment to change your mind.** When a command is understood, what it will do appears at the top of the screen with a countdown, and one click on it calls the command off. Nothing runs until the countdown ends. Three seconds by default, adjustable from 0 (run at once) to 30 in *Settings → Commands*. On-screen answers skip the wait, since text on your own screen has nothing to undo.
- **Your own microphone no longer needs the wake word.** Say “open the calculator” and it happens; the countdown above is what stands between a slip of the tongue and the command. To keep speech apart from orders, a command said this way has to *begin* the sentence: “open the calculator” is an order, “we could open the calculator later” is not. The PC’s own sound still needs the wake word, always. If you would rather keep it on the microphone too, there is a switch for that.

## [1.2.1] — 2026-09-28

### Changed
- **On-screen answers no longer need the wake word.** A phrase you wrote is recognized wherever it is said, in any letter case, and with or without spoken commands switched on — writing your own line in your own caption box cannot do anything to the PC. Everything else, from opening apps to the media keys, still needs the wake word first. The same phrase twice in a row is still shown once.

### Fixed
- Two settings files had a stray blank line after almost every statement, left behind by an earlier edit. Only the source formatting changed.

## [1.2.0] — 2026-09-28

### Added
- Saying the wake word on its own switches captions off, and again to bring them back. The explicit "pause captions" and "resume captions" still work, and a name inside an ordinary sentence is still ignored.
- "Open YouTube" and "open Google", in English and Arabic, opening those two fixed addresses in your own browser. The addresses live in the code; nothing is ever built from what was said.
- **On-screen answers** (*Settings → Commands*, off by default): when someone says the wake word and a phrase you chose, EchoSub writes your own prepared line in the caption box, in its own colour, labelled EchoSub and removed after a few seconds. Nothing leaves the PC, nothing is typed into another program, and no text is generated — every line is one you wrote.
- A bare action word after the wake word now means the captions ("echo sub, stop"), while a media phrase still reaches the media keys ("echo sub, stop the music").

### Changed
- The voice-command code is split into what may be done (`voice_registry`), how it is done (`voice_actions`) and what was said (`voice_commands`), so no file passes 500 lines.

## [1.1.1] — 2026-09-28

### Added
- **Light mode can use the Base model** instead of Small (*Settings → Language & Engine*). Measured on this machine over a 39-second clip: Base is two to six times faster than Small and just as accurate down to 0 dB of noise; Small only pulls ahead in heavy noise (-5 dB: 4 % against 11 % of words wrong). Small stays the default.

### Changed
- flake8 runs clean over the whole app and its tests (`setup.cfg`, 120 columns). The vendored `tashkeel/` code is excluded, as it belongs to the CATT project. Imports left behind by the 1.1.0 file split were removed.
- Fresh screenshots in the README and the user guide, including the microphone and the Advanced tab.

## [1.1.0] — 2026-09-28

### Added
- **Your microphone, captioned too** (*Settings → Language & Engine → Microphone*, off by default). What you say is recognized and translated like anything else, shown in its own colour with your own label ("You"), kept on its own line, and spoken commands are accepted from it as well — that last part can be switched off. Both sources share the one speech model, so nothing extra runs while nobody is talking, and a microphone that cannot be opened never stops the captions.
- **Voice commands** (off by default; tray menu and *Settings → Advanced*). Only a fixed list of harmless actions can run: open or close eighteen everyday apps (Calculator, Notepad, Paint, File Explorer, Windows Settings, Task Manager, Snipping Tool, on-screen keyboard, Magnifier, Character Map, Chrome, Edge, Firefox, VLC, VS Code, Discord, Steam, Spotify), and pause, resume, hide, show or clear captions. Closing is the same as clicking the X, so unsaved work is still protected; File Explorer only loses its folder windows, never the desktop. A command counts only after a wake word ("echo sub" by default), because EchoSub hears everything the PC plays. Nothing from what is said is ever passed to a shell or used as a program name. Commands are understood in about twenty languages, in everyday wording and with grammatical endings, and the wake word is matched as a whole word so a short one is not heard inside another word. Several wake words can be listed, separated by commas ("mama, ماما"). When the wake word is heard but the rest is not a command, a notification shows what was heard.
- **Catch-up audio buffer**: when recognition falls behind, waiting audio is kept in a temporary folder and recognized in order instead of being thrown away. Session-only, deleted as it is read and when the app closes; capped in *Settings → Advanced* (0 min = off).
- The catch-up buffer's folder can be chosen in *Settings → Advanced*, to put it on a fast drive. Empty means the Windows temp folder, the folder is created if needed, and a drive that cannot be written to falls back to the temp folder with a message instead of failing.
- **Update checks for the installed app** through the official GitHub releases: once a day in the background, plus *Check for updates…* in the tray menu. A newer version shows a message with a button that opens the download page — EchoSub never downloads or installs anything by itself. Can be turned off in *Settings → Advanced*.
- Tests for the quality gates, the catch-up buffer, sound-device reconnection, release comparison and voice commands (no GPU, models or sound card needed).

### Changed
- **Fewer made-up captions.** Whisper's own signals are weighed together (no-speech probability with average log probability, and the compression ratio), known filler phrases and looping repetitions are dropped, and text too long for the audio it came from is rejected. Live text is held to a stricter standard than a finished caption and can never enter the history or the transcript file.
- Text that fails these gates is never sent to translation.
- Every source file is under 500 lines: captions, placement, animation, translation, segmentation, settings widgets and tabs, update checks and voice commands each live in their own module.

### Fixed
- The Advanced settings were wider than the window: a long hint beside the wake word forced a sideways scrollbar, and the folder field showed the end of the path instead of its start. The tab is now grouped into boxes, every hint wraps on its own line, and the path reads from the beginning.
- Number fields across the whole Settings window are one width instead of stretching the full row, "Box width" no longer cuts off its own unit, background opacity shows its value as a percentage, and colour buttons no longer stretch across the window.
- **The sound card can now be unplugged and plugged back in.** A failed attempt to open a device used to leave a PortAudio instance behind, each with its own stale device list, so the device that came back kept failing with "Invalid device info"; now every attempt cleans up after itself. If the device you picked is missing, EchoSub listens to the default one and says so, then moves back on its own when your device returns. Reconnection attempts are at most 5 s apart.
- The catch-up buffer is written by a background worker, never inside the sound card's callback, and is handed to the engine in slices, so a long backlog cannot stall capture or make speech detection scan minutes of audio at once.

## [1.0.7] — 2026-09-27

### Fixed
- The Settings window could open taller than the screen — on a 1920x1080 screen with Windows text scaling at 125 % or 150 % the Save button ended up below the bottom edge. Every tab now scrolls, the buttons stay at the bottom, and the window opens no larger than the screen it appears on (it can shrink to 406 x 144). The caption history window is sized the same way, and a window that opens partly off-screen is pulled back.

## [1.0.6] — 2026-09-27

### Fixed
- The caption box could be zoomed until it covered the screen: Shift + wheel is also how Windows scrolls sideways, so scrolling in a window underneath the box zoomed it by accident. The zoom now stops while the box still fits the screen, the box menu has **Caption size: back to 100%**, and the Settings window has a **100%** button next to Size (zoom). A size you already set is never changed on its own.

## [1.0.5] — 2026-09-27

### Added
- **Light mode** (tray menu and *Settings → Language & Engine*): uses the Small speech model instead of a large one and turns live text off, for when a game or another program is using the graphics card. Your own model choice and settings are kept and come back when you turn it off.
- Tests under `tests/` (`python -m unittest discover -s tests`) for live-text translation, the backlog limits and light mode. They need no GPU, models or sound card.

### Changed
- Live ("partial") text is no longer translated on the recognition thread, so recognition never waits for the translator. Only the newest live text is translated; older ones are dropped, and a translation that arrives after the finished caption is discarded.
- Speech detection (VAD) reruns at most every 0.15 s, and less often for long buffers, instead of after every 50 ms chunk of audio. Before a caption is ended on possibly outdated speech regions, detection is rerun so nothing is cut off mid-sentence.
- When recognition or translation cannot keep up, EchoSub no longer falls further and further behind: audio waiting to be recognized is capped (the oldest is dropped), at most six captions wait for translation and older ones are shown in their original language, and the status line says so.

## [1.0.4] — 2026-09-23

### Added
- A copy button on every caption row: hover the caption box and a small button appears next to each original and translated line; clicking it copies that text to the clipboard. It can be turned off in *Settings → Text & Colors*.

### Fixed
- The caption box no longer treats the mouse moving onto its resize grip (or a copy button) as the mouse leaving the box.

## [1.0.3] — 2026-09-20

### Fixed
- Captions written in the wrong alphabet (English spoken text transcribed in Russian letters, for example). The previous sentence is passed to Whisper as context, and Whisper copies its alphabet, so one mis-recognized sentence dragged the following ones with it. EchoSub now knows which script each language is written in: context from another script is not used, a transcript that comes out in the wrong script is redone without context, and a transcript that is still wrong is dropped instead of poisoning the next ones.

## [1.0.2] — 2026-09-19

### Added
- Box size (zoom): hold **Shift** and turn the mouse wheel over the caption box to make the box and its text bigger or smaller (50–300 %). The value is also under *Settings → Position & Alignment → Box style → Size (zoom)*.
- While Google Translate refuses requests, EchoSub translates offline with an NLLB model you have already downloaded, and switches back to Google when it answers again.

### Fixed
- Google Translate "too many requests" errors: requests are spaced out, a refused request is retried, and after repeated refusals EchoSub pauses Google for a while (20 s, doubling up to 5 min) instead of asking again for every caption.
- Translation errors are shown as a short message that disappears after a few seconds, instead of a long message that stayed in the caption box.

## [1.0.1] — 2026-09-17

### Added
- The author's photo in the About window.
- System requirements (minimum and recommended) and per-model download size, graphics memory and speed in the README and user guide.
- Screenshots in the README and user guide.

## [1.0.0] — 2026-09-17

First public release.

### Recognition & translation
- System audio capture via WASAPI loopback, following the default output device and recovering automatically when a device disappears.
- Speech recognition with faster-whisper (large-v3-turbo default; large-v3, medium, small, base), automatic language detection, almost 100 languages, GPU (CUDA) or CPU.
- Offline translation with NLLB-200 (600M / 1.3B) or Google Translate; translation runs on its own thread so recognition never waits.
- Optional translation of speech already in the caption language (dialect / casual → standard language).
- Moroccan Arabic (Darija) language (translation via NLLB `ary_Arab`; recognized with Whisper's Arabic model).
- Optional Arabic diacritics (تشكيل) with the CATT model, on the translation, the original text, or both.
- Model download window with progress, speed, time left, Cancel and Retry; interrupted downloads resume.
- Whisper context from the previous sentence of the same speaker; filters for common hallucinations.

### Speakers
- Speaker detection with CAM++ voice embeddings: a new line and color per person, with adjustable strictness.

### Caption box
- Custom outlined text rendering; separate font size, color and bold for original and translation; line height and spacing.
- Language labels (code, name, flag, flag + code/name) before/after/above/below the original and the translation.
- Text alignment; 9 screen positions plus custom drag; screen selection; distance from edge; width; autosize.
- Corner radius and padding; slide / fade / no animation for lines, text changes and box resizing.
- Auto-hide after silence, kept visible while hovered; click-through lock; fade in/out.

### App
- System tray icon with status colors; global hotkeys (Ctrl+Alt+H / P / L).
- Settings with live preview, searchable dropdowns, restore defaults; always on top.
- Caption history window with copy / save; optional transcript files.
- Log file, crash logging, single instance, About window.
- `--self-test [file.wav]` checks the GPU, models and pipeline without opening a window.
- Windows installer (Inno Setup) and PowerShell build scripts.

[1.1.1]: https://github.com/mPhpMaster/echo-sub/releases/tag/v1.1.1
[1.1.0]: https://github.com/mPhpMaster/echo-sub/releases/tag/v1.1.0
[1.0.7]: https://github.com/mPhpMaster/echo-sub/releases/tag/v1.0.7
[1.0.6]: https://github.com/mPhpMaster/echo-sub/releases/tag/v1.0.6
[1.0.5]: https://github.com/mPhpMaster/echo-sub/releases/tag/v1.0.5
[1.0.4]: https://github.com/mPhpMaster/echo-sub/releases/tag/v1.0.4
[1.0.3]: https://github.com/mPhpMaster/echo-sub/releases/tag/v1.0.3
[1.0.2]: https://github.com/mPhpMaster/echo-sub/releases/tag/v1.0.2
[1.0.1]: https://github.com/mPhpMaster/echo-sub/releases/tag/v1.0.1
[1.0.0]: https://github.com/mPhpMaster/echo-sub/releases/tag/v1.0.0
