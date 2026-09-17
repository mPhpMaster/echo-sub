# EchoSub — User Guide

![EchoSub caption box](screenshots/captions-en-ar.png)

## First start

1. Start EchoSub from the Start menu. Its icon appears in the system tray (next to the clock).
2. The first start downloads the AI models (~2.5 GB). A window shows the progress, speed and time left; **Cancel** stops it and **Retry** continues where it stopped (nothing already downloaded is lost). Later starts take a few seconds.
3. Play anything with speech. Captions appear at the bottom of the screen and disappear when nobody is talking.

The small dot on the tray icon shows the status: **blue** listening · **amber** loading or reconnecting audio · **grey** paused · **red** error (hover for details).

## Menu

Right-click the caption box or click the tray icon:

| Item | What it does |
|---|---|
| Translation language | Quick switch between common languages (all ~100 are in Settings) |
| Show captions `Ctrl+Alt+H` | Turn the caption box on/off |
| Adjust window position and size | Shows the box with sample text so you can drag it or resize it from its corner |
| Lock window (click-through) `Ctrl+Alt+L` | Clicks go through the box to the app underneath |
| Pause `Ctrl+Alt+P` | Stop listening |
| Clear captions | Remove the current text |
| Caption history… | Everything captioned this session, with Copy all / Save as… |
| Settings… | All options, with live preview on the caption box |
| Open log file | For troubleshooting |
| Restart engine | Reload the models and audio device |
| About EchoSub… | Version, author, license, links |

The hotkeys work while other apps (games, videos) have focus. If another program already uses one, EchoSub tells you; they can be turned off in Settings → Advanced.

## Settings

Every dropdown accepts typing to search (e.g. type `ital` for Italian; Arabic names work too, with or without hamza).

### Language & Engine

![Language & Engine settings](screenshots/settings-language.png)

- **Show captions in** — the language captions are translated into.
- **Spoken language** — *Auto-detect* works for any language; choosing the language improves accuracy.
- **Speech recognition model** — *Large v3 Turbo* is the best balance; *Small*/*Medium* are faster on weaker GPUs.
- **Translation engine** — *NLLB 600M* (offline, fast), *NLLB 1.3B* (offline, more accurate), *Google Translate* (online), or *No translation*.
- **Run on** — GPU (CUDA) or CPU. **Audio source** — follow the default output device, or pick one.
- **Translate even when speech is already in the caption language** — rewrites dialect or casual speech into the standard language (e.g. Egyptian or Gulf Arabic into Modern Standard Arabic).
- **Arabic diacritics (تشكيل)** — adds harakat to Arabic captions: on the translation, the original text, or both. Turning it on downloads a 70 MB model once. Sentences mixing Arabic with other languages get less accurate harakat.
- **Moroccan Arabic (Darija)** — choose it as *Show captions in* to get captions in Darija, or as *Spoken language* when the audio is Darija (auto-detect hears Darija as Arabic). *NLLB 1.3B* gives noticeably better Darija than *NLLB 600M*.

### Text & Colors

![Text & Colors settings](screenshots/settings-text.png)

- Font; show the original text above the translation; show live text while someone is still talking.
- **Translation** and **Original text**: font size, bold, color, and a **language label** (code, name, flag, flag + code, flag + name, or nothing) placed before, after, above or below the text. "Before"/"after" follow the reading direction.
- **Spacing & background**: line height (any value, including below 100%), space between caption lines, space between original and translation, number of lines, background opacity, and how long after silence the box hides (it never hides while the mouse is over it).

### Position & Alignment

![Position & Alignment settings](screenshots/settings-position.png)

- **Text alignment** — center, left, right, or follow the reading direction.
- **Position** — 9 spots on the screen or *Custom* (drag the box anywhere; dragging switches to Custom automatically). **Screen**, **distance from the screen edge** and **box width**.
- **Autosize** — the box shrinks and grows to fit its text, up to the box width.
- **Box style** — corner radius (0 = square) and padding.
- **Animation** — *Slide* (lines glide, text cross-fades, the box resizes smoothly), *Fade*, or *None*, and the duration.

### Speakers

![Speakers settings](screenshots/settings-speakers.png)

- **Detect speakers** — a new line and color for each voice. **Apply speaker color to** the translation, the original, or both. **Speaker colors** for up to 8 voices.
- **Matching strictness** — raise it if two people share a color; lower it if one person gets several colors.

### Advanced
- Speech detection threshold, silence that ends a sentence, maximum sentence length.
- **Save every caption to a transcript file** (in `%LOCALAPPDATA%\EchoSub\transcripts`).
- **Global hotkeys** on/off.

**Restore defaults** resets everything except where the caption box is.

## Troubleshooting

| Problem | Try |
|---|---|
| No captions | Check the tray icon status. Make sure the sound plays through the device EchoSub listens to (Settings → Audio source). |
| Captions are slow | Use a smaller model (Small/Medium), or close other GPU-heavy apps. |
| Wrong language detected | Set *Spoken language* instead of Auto-detect. |
| Words invented during music | Raise the speech detection threshold (Settings → Advanced). |
| "Could not use the GPU" | Update the NVIDIA driver; EchoSub keeps working on the CPU meanwhile. |
| A model download failed or was canceled | Menu → *Restart engine* (or *Retry* in the download window). Downloads resume where they stopped. |
| Not sure if the GPU / models work | Run `"%LOCALAPPDATA%\Programs\EchoSub\EchoSub.exe" --self-test` (or the path you installed to). It loads every model without opening a window and writes the result to the log; add a 16-bit `.wav` file path to also test recognition and translation. |
| Anything else | Menu → *Open log file*, and include the relevant lines when reporting an issue. |
