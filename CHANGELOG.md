# Changelog

All notable changes to EchoSub are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

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

[1.0.6]: https://github.com/mPhpMaster/echo-sub/releases/tag/v1.0.6
[1.0.5]: https://github.com/mPhpMaster/echo-sub/releases/tag/v1.0.5
[1.0.4]: https://github.com/mPhpMaster/echo-sub/releases/tag/v1.0.4
[1.0.3]: https://github.com/mPhpMaster/echo-sub/releases/tag/v1.0.3
[1.0.2]: https://github.com/mPhpMaster/echo-sub/releases/tag/v1.0.2
[1.0.1]: https://github.com/mPhpMaster/echo-sub/releases/tag/v1.0.1
[1.0.0]: https://github.com/mPhpMaster/echo-sub/releases/tag/v1.0.0
