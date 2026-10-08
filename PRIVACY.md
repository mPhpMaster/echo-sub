# Privacy Policy

_Last updated: 7 October 2026_

EchoSub is designed to work on your computer, not in the cloud. This page explains exactly what it does with your data.

## Audio

- EchoSub captures the audio playing through your selected output device (speakers or headphones) while it is running and not paused.
- The audio is processed **on your computer** to detect speech, recognize voices and create captions. It is never uploaded.
- With *Run on: Graphics card, any brand* chosen, speech is recognized by a helper program that ships with EchoSub
  (`whisper-server.exe`). EchoSub hands it the audio through a connection that only exists inside your computer
  (127.0.0.1, which other machines cannot reach). It is still never uploaded.
- Audio normally stays in memory. The one exception is the **catch-up buffer**: when recognition falls behind (a busy graphics card, for example), the audio waiting its turn is written to a temporary folder so captions can catch up instead of losing what was said. It is read back, deleted as it is read, and the whole folder is removed when EchoSub closes — a folder left behind by a crash is deleted on the next start. It is a recovery window, not a recording, and it is capped by *Settings → Advanced → Catch-up audio buffer*, where **0 min turns it off** completely. You choose which drive it is written to in the same place; by default it is the Windows temp folder.

## Captions and transcripts

- Captions are shown on screen and kept in memory for the current session (the *Caption history* window).
- Transcript files are written **only if you enable** *Save every caption to a transcript file* (Settings → Advanced). They are stored in `%LOCALAPPDATA%\EchoSub\transcripts` (or the `transcripts` folder when running from source) and never leave your computer.

## Microphone

EchoSub does not touch your microphone unless you switch it on in *Settings → Language & Engine → Microphone*.
When it is on, the microphone is captured, recognized and translated exactly like the rest of the audio, on your
computer, and it is never uploaded.

## Questions to an AI

This is **off** unless you switch it on in *Settings → AI*, and it is the one feature that can send what was
said on your PC to somebody else's computer.

- Normally nothing happens until you ask: you say your wake word and then **“ask …”**.
- **The one exception is *Answer questions on its own***, a second switch in the same tab, also off by default.
  With it on, EchoSub sends **without you asking**: every question it hears — from a call, a video or a game,
  as you choose — goes to the service with the recent captions. It only counts a sentence ending in a question
  mark and at least three words long — and, unless you switch that off, only while one person is talking —
  sends at most one every so often (20 seconds by default), and never sends a
  new one while an answer is still on its way. With a paid service, each one costs money. LM Studio keeps all of it
  on your computer.
- When you ask, it sends your question together with the **most recent captions** — as many as you choose (20 by
  default, 0 to send none), from everyone or only from your microphone — and your PC's current date, time and time
  zone, so it can answer questions such as "what's the date today?".
- **Those captions can include other people's words** — people in a call, in a video or in a game. Please only
  switch this on if that is all right with you and with them.
- The question waits for the same countdown as every spoken command, so saying “no” stops it before anything is
  sent.
- Where it goes is your choice: **Claude** (Anthropic), **ChatGPT** (OpenAI), **Gemini** (Google) or **DeepSeek**,
  whose own privacy policies then apply — or **LM Studio**, which runs on your own computer, so nothing leaves it.
- Your API key is encrypted with Windows' own data protection before it is saved, so the settings file alone is no
  use to anyone else. It is sent only to the service it belongs to.
- Answers are shown in the caption box and are not saved.

## Voices

- To tell speakers apart, EchoSub computes a short numeric "voice fingerprint" for each voice it hears. These exist only in memory while the app runs and are discarded when it closes.

## Data sent over the internet

EchoSub connects to the internet only in these cases:

| When | Where | What is sent |
|---|---|---|
| First use of a model (including the Arabic diacritics model, if you turn that option on) | Hugging Face (huggingface.co) and GitHub (github.com) | A normal download request for the model files. No audio or captions. |
| You select the **Google Translate** engine | Google's translation service | The text of each caption, so it can be translated. Google's privacy policy applies. |
| You click a link in the About window | The linked website | Whatever your browser normally sends. |
| Once a day, and when you choose *Check for updates…* (can be switched off in *Settings → Advanced*) | GitHub (api.github.com) | A request for the latest release number. No audio or captions. |
| You switch on *Settings → AI* **and** ask a question with a cloud service chosen | Anthropic, OpenAI, Google or DeepSeek — the one you chose | Your question, the recent captions you chose to send and your PC's date, time and time zone, with your API key. Never with LM Studio, which runs on your computer. |
| You switch on *Answer questions on its own* **and** a question is heard, with a cloud service chosen | The same service | The question that was heard and the recent captions — sent without you asking, as described above. |

With the default offline engines and the AI feature left off, no caption text or audio ever leaves your computer.

## Settings and logs

- Settings are stored in `settings.json` and logs in `logs\echosub.log` inside `%LOCALAPPDATA%\EchoSub`. Logs contain technical status messages and errors, not caption text (unless you enable debug logging, which records recognized text for troubleshooting).
- EchoSub contains no analytics, telemetry, advertising or tracking of any kind.

## Removing your data

Uninstalling EchoSub offers to delete `%LOCALAPPDATA%\EchoSub` (settings, models, logs and transcripts). You can also delete that folder yourself at any time.

## Contact

Questions about privacy: Mohammad Al-Safadi — [mPhpMaster@gmail.com](mailto:mPhpMaster@gmail.com)
