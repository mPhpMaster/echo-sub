# Privacy Policy

_Last updated: 17 September 2026_

EchoSub is designed to work on your computer, not in the cloud. This page explains exactly what it does with your data.

## Audio

- EchoSub captures the audio playing through your selected output device (speakers or headphones) while it is running and not paused.
- The audio is processed **in memory on your computer** to detect speech, recognize voices and create captions. It is never saved to disk and never uploaded.

## Captions and transcripts

- Captions are shown on screen and kept in memory for the current session (the *Caption history* window).
- Transcript files are written **only if you enable** *Save every caption to a transcript file* (Settings → Advanced). They are stored in `%LOCALAPPDATA%\EchoSub\transcripts` (or the `transcripts` folder when running from source) and never leave your computer.

## Voices

- To tell speakers apart, EchoSub computes a short numeric "voice fingerprint" for each voice it hears. These exist only in memory while the app runs and are discarded when it closes.

## Data sent over the internet

EchoSub connects to the internet only in these cases:

| When | Where | What is sent |
|---|---|---|
| First use of a model (including the Arabic diacritics model, if you turn that option on) | Hugging Face (huggingface.co) and GitHub (github.com) | A normal download request for the model files. No audio or captions. |
| You select the **Google Translate** engine | Google's translation service | The text of each caption, so it can be translated. Google's privacy policy applies. |
| You click a link in the About window | The linked website | Whatever your browser normally sends. |

With the default offline engines, no caption text or audio ever leaves your computer.

## Settings and logs

- Settings are stored in `settings.json` and logs in `logs\echosub.log` inside `%LOCALAPPDATA%\EchoSub`. Logs contain technical status messages and errors, not caption text (unless you enable debug logging, which records recognized text for troubleshooting).
- EchoSub contains no analytics, telemetry, advertising or tracking of any kind.

## Removing your data

Uninstalling EchoSub offers to delete `%LOCALAPPDATA%\EchoSub` (settings, models, logs and transcripts). You can also delete that folder yourself at any time.

## Contact

Questions about privacy: Mohammad Al-Safadi — [mPhpMaster@gmail.com](mailto:mPhpMaster@gmail.com)
