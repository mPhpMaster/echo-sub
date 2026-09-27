# EchoSub — Development Guide

## Requirements

- Windows 10/11 64-bit
- [Python 3.10 (64-bit)](https://www.python.org/downloads/release/python-31011/) — with the `py` launcher
- An NVIDIA GPU is optional for development (the app falls back to the CPU)
- [Inno Setup 6](https://jrsoftware.org/isdl.php) — only to build the installer (`winget install JRSoftware.InnoSetup`)

If PowerShell refuses to run the scripts, start them with `powershell -ExecutionPolicy Bypass -File <script>` as shown below.

## Scripts

| Script | What it does |
|---|---|
| `scripts\dev.ps1` | Creates `.venv`, installs `requirements.txt` when it changed, and runs EchoSub from source with the log in the console. |
| `scripts\build.ps1` | Installs `requirements-build.txt`, regenerates the icon and version resource, and builds `dist\EchoSub\EchoSub.exe` with PyInstaller. |
| `scripts\build-installer.ps1` | Runs `build.ps1`, then compiles `installer\EchoSub.iss` into `dist\installer\EchoSub-Setup-<version>.exe` (+ `.sha256`). |
| `scripts\make_icon.py` | Draws the app icon into `echosub\assets` (called by `build.ps1`). |
| `run.bat` | Double-click shortcut: starts EchoSub from source without a console (after `dev.ps1` has set up `.venv`). |

Options:

```powershell
scripts\dev.ps1 -DebugLog            # log Whisper confidence + recognized text for every segment
scripts\dev.ps1 -DataDir D:\tmp\es   # separate settings/models/logs folder
scripts\dev.ps1 -NoConsole           # start in the background (pythonw)
scripts\dev.ps1 -SkipInstall         # don't touch dependencies

scripts\build.ps1 -Clean             # from-scratch build
scripts\build-installer.ps1 -SkipBuild   # re-package the existing dist\EchoSub
```

## Where data lives

| Running | Settings, models, logs, transcripts |
|---|---|
| From source (`dev.ps1`, `run.bat`) | The project folder (`settings.json`, `models\`, `logs\`, `transcripts\` — all git-ignored) |
| Installed / `dist\EchoSub\EchoSub.exe` | `%LOCALAPPDATA%\EchoSub` |
| Any | `ECHOSUB_DATA_DIR` overrides the folder; `ECHOSUB_MODELS_DIR` overrides only the models folder |

Set `ECHOSUB_MODELS_DIR` to your source checkout's `models` folder to test a build without downloading the models again.

## Tests

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

They use stand-in models and Qt's offscreen platform, so they need no GPU, no downloads and no sound card. They cover the parts that are easy to break: live text must never be translated on the recognition thread, stale live translations must be dropped, the translation queue and the audio backlog must stay bounded and in order, speech detection must not rerun for every chunk, and light mode must swap the model without touching the user's settings.

## Self-test

`python -m echosub --self-test [speech.wav]` (or `EchoSub.exe --self-test [speech.wav]`) loads the speech, translation and speaker models from the current settings without opening any window, optionally transcribes and translates the WAV file, logs every step with timings, and exits with code 0 (passed) or 1 (failed). Use it to verify a build:

```powershell
$env:ECHOSUB_DATA_DIR = "$env:TEMP\echosub-test"; $env:ECHOSUB_MODELS_DIR = "$PWD\models"
Start-Process dist\EchoSub\EchoSub.exe -ArgumentList "--self-test", "C:\path\speech.wav" -Wait -PassThru
Get-Content "$env:TEMP\echosub-test\logs\echosub.log"
```

## Releasing a new version

1. Update `__version__` in `echosub/__init__.py` (the build scripts, exe version resource and installer read it from there).
2. Add the changes to `CHANGELOG.md`.
3. Run `scripts\build-installer.ps1 -Clean`.
4. Test the installer on a clean Windows user account.
5. Create a GitHub release tagged `v<version>`, attach `EchoSub-Setup-<version>.exe` and paste the SHA-256 from the `.sha256` file.

## Project layout

```
echosub/                 the application package
  __init__.py            name, version, description, author, links
  __main__.py            `python -m echosub`
  main.py                tray icon, menus, hotkeys, single instance, wiring UI <-> engine
  engine.py              audio -> VAD -> speaker id -> Whisper pipeline, translation thread, self-recovery
  audio.py               WASAPI loopback capture, default-device tracking
  asr.py                 faster-whisper wrapper, hallucination filters
  translate.py           NLLB-200 (CTranslate2) and Google translators
  speaker.py             online speaker tracking (CAM++ embeddings via sherpa-onnx)
  overlay.py             caption box: text rendering, labels, placement, autosize, animations
  settings_dialog.py     Settings window
  history.py             caption history window, transcript files
  about.py               About window
  selftest.py            `--self-test`: load models and run a WAV through the pipeline, no UI
  downloads.py           model downloads with progress, cancel and resume (Hugging Face + GitHub)
  download_dialog.py     download progress window
  tashkeel/              Arabic diacritics (CATT ONNX model; tokenizer adapted from CATT, Apache-2.0)
  hotkeys.py             global hotkeys (Win32 RegisterHotKey)
  config.py              defaults, data folders, settings persistence
  languages.py           languages, NLLB/Google codes, flags
  logging_setup.py       rotating log file, crash logging, pythonw stdout/stderr fix
  cuda_setup.py          makes the pip NVIDIA DLLs loadable
  assets/                icon (+ optional author photo: author.png / author.jpg)
  flags/                 flag images
launcher.py              PyInstaller entry point
EchoSub.spec             PyInstaller build definition
installer/EchoSub.iss    Inno Setup installer definition
scripts/                 dev / build / installer scripts
docs/                    guides
```

## How the pipeline works

1. **Capture** — `audio.LoopbackCapture` records the output device with PyAudioWPatch, down-mixes to mono and resamples to 16 kHz with soxr.
2. **Segmentation** — `engine.CaptionEngine._loop` runs Silero VAD over the buffer (only when new audio arrived). A sentence ends after `silence_sec` of silence or `max_segment_sec` of speech.
3. **Speakers** — `speaker.SpeakerTracker` embeds each speech region with CAM++ and matches it against known voices; a segment is split where the voice changes.
4. **Recognition** — faster-whisper transcribes each speaker run (int8 on GPUs without fast float16), with the previous sentence of the same speaker as context. Live partial text is produced only if the GPU keeps up.
5. **Translation** — finals are emitted immediately with their original text; a separate thread translates them (NLLB-200 or Google) and emits the translation.
6. **Display** — `overlay.CaptionOverlay` merges consecutive sentences of one speaker, animates line changes (FLIP slide) and box resizing, and hides itself after silence.

All engine callbacks run on worker threads and reach the UI through Qt signals (`main.Bridge`); each engine restart gets a new generation number so late events from an old engine are ignored.

## Code style

- PEP 8, 120-character lines, type-free but descriptive names.
- Comments explain *why*, not *what*.
- Every source file starts with the SPDX license header (see `CONTRIBUTING.md`).
