# Changelog

All notable changes to EchoSub are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

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

[1.0.2]: https://github.com/mPhpMaster/echo-sub/releases/tag/v1.0.2
[1.0.1]: https://github.com/mPhpMaster/echo-sub/releases/tag/v1.0.1
[1.0.0]: https://github.com/mPhpMaster/echo-sub/releases/tag/v1.0.0
