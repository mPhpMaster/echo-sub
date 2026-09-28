# EchoSub Voice Commands — Handoff for Claude

## Scope

Continue only the EchoSub voice-command and on-screen interaction work. Do not change Laundry POS or GUI Control Bridge. Keep source files below 500 lines and split modules by responsibility. Do not run arbitrary shell commands, scripts, paths, or terminal applications from speech.

## Current implemented work

### Voice-command foundation

- Commands are disabled by default and only act on final captions after a configured wake word.
- Multiple wake words are supported, separated by commas in **Settings → Commands**.
- Built-in wake aliases currently include `echo sub`, Arabic spellings, `PC`, `بي سي`, `Alexa`, and `إليكسا`.
- `Help` works after every configured wake word, for example `Maya help` once `Maya` has been added to the configured list.
- Commands can open or close only approved everyday applications from the fixed allowlist.
- The fixed application allowlist currently includes Calculator, Notepad, Paint, File Explorer, Settings, Task Manager, Snipping Tool, on-screen keyboard, Magnifier, Character Map, Chrome, Edge, Firefox, VLC, VS Code, Discord, Steam, and Spotify.

### Settings UI

- A **Commands** tab exists in Settings.
- It stores user-defined spoken phrases mapped to an approved existing action only.
- A custom phrase must never become a shell command, executable path, script, or command line.
- The tab has an opt-in `Press` setting. It is off by default.

### Press command

- With the opt-in setting enabled, `Maya press A B C` sends individual `A`, `B`, and `C` key presses.
- It is limited to at most six individual `A-Z` or `0-9` keys.
- It refuses modifiers, shortcuts, Enter, navigation, system keys, clipboard commands, and arbitrary text.

### Media control

- Windows media-key commands were added for play/pause, stop, next, previous, mute, volume up, and volume down.
- Examples include `Maya next song`, `Maya الأغنية التالية`, `Maya ارفع الصوت`, and `Maya طفي الموسيقى`.
- The implementation uses Windows media virtual keys, so it controls the currently active system media session instead of targeting a specific player.
- Seeking to an exact time (for example, second zero) is **not implemented** because there is no reliable universal Windows media key for time seeking across YouTube, Spotify, VLC, and other players.

### Caption presentation

- Language and speaker labels now render in a separated badge with a background and a fixed separator.
- A microphone speaker name is promoted above the caption or translation so it does not look attached to spoken text.

## Verified work

- Python compilation passed for the EchoSub package.
- Voice-command and voice-command UI tests passed after the media-command work.
- The caption-overlay visual test was not completed in this session; visually verify microphone label placement in the running application.

## Completed in this session

1. **Wake-word-only toggle** — done. The whole caption must be the name, so an embedded name is ignored; the
   existing repeat cooldown debounces it. `pause captions` / `resume captions` still work, and a bare action word
   after the wake word ("stop", "وقف", "طفي") now controls the captions while media phrases still reach the media
   keys.
2. **Browser shortcuts** — done, as a `LINKS` registry of fixed HTTPS addresses opened through the normal Windows
   browser handler. Only the site name is recognized; no address is ever built from speech, and there is no
   search or arbitrary browsing.
3. **On-screen interaction** — done as user-written phrase → on-screen-text pairs (`screen_replies.py`), which
   covers the fixed-card option as a special case. Off by default, capped at 20 pairs, shown in its own colour
   with an `EchoSub` label and removed after a configurable few seconds. Nothing is sent to Discord, no API, no
   typing into other programs, no model and no network request.
4. **Language coverage** — the new words are explicit vocabulary entries (`LINK_WORDS`, extra caption-action
   words); nothing is translated or guessed at runtime.

Also: `voice_commands.py` was split into `voice_registry.py` (what may be reached), `voice_actions.py` (how it is
carried out) and `voice_commands.py` (what was said), so every file stays under 500 lines.

Validation: 161 tests pass, flake8 is clean over `echosub` and `tests`, and the caption box was rendered
off-screen to check the three kinds of line (system audio, microphone, on-screen answer) are told apart by colour
and label.

## Original required work

### 1. Wake-word-only toggle

Implement the latest requested behavior:

- Saying the wake name alone, such as `Maya`, toggles EchoSub captions.
- When captions are active, it pauses them.
- When captions are paused, it resumes them.
- Remove the need for separate short phrases such as `Maya وقف` and `Maya كمل`.
- Keep explicit commands such as `pause captions` and `resume captions` available.
- Prevent repeated final-caption events from toggling twice. Reuse the existing repeat cooldown or implement a dedicated debounce.
- Do not treat a wake word embedded in a normal sentence as a command.

Expected command examples:

| Spoken phrase | Result |
| --- | --- |
| `Maya` | Toggle caption pause/resume |
| `مايا` | Toggle caption pause/resume |
| `Maya pause captions` | Pause captions |
| `Maya resume captions` | Resume captions |
| `Maya stop music` | Stop the active media session |
| `Maya الأغنية التالية` | Next media track |

### 2. Browser shortcuts through the approved app registry

Add safe fixed commands for:

- `Maya open YouTube`
- `Maya open Google`
- Arabic equivalents such as `مايا افتح يوتيوب` and `مايا افتح جوجل`

Requirements:

- Use fixed, hard-coded HTTPS URLs only.
- Open URLs through the normal Windows browser handler; do not construct a URL from spoken text.
- Do not add general web search, arbitrary URLs, browser automation, or browsing commands in this task.
- Add the commands to Help and the Settings custom-action selector.

### 3. On-screen interaction for Discord screen sharing

The requested result is text shown on the shared EchoSub caption overlay, **not** a Discord message and not audio sent into Discord.

Requirements to resolve before implementation:

- EchoSub already receives Discord audio through system-loopback capture and can recognize wake words in it.
- Create a narrow on-screen interaction mode: when a Discord participant says the wake word followed by an allowed interaction phrase, EchoSub displays a short on-screen response in the caption overlay.
- Do not send any message to Discord, invoke a Discord bot/API, type into Discord, or use the microphone as output.
- Keep interaction phrases and responses local, explicit, and configurable in Settings. A good first version can be fixed question/response cards or custom phrase → display-text mappings.
- Do not add an LLM, cloud request, automatic web access, arbitrary code execution, or unrestricted chatbot behavior without a separate product decision.
- Make the on-screen response visually distinct from ordinary captions and microphone captions, including a short timeout and clear source label such as `EchoSub`.
- Add an enable/disable setting. Default it to off.

Open product decision for Claude to ask only if required: should the first interaction set be fixed local responses, or should the Settings page allow the user to create phrase → on-screen-text pairs?

### 4. Language coverage

- Preserve current Arabic and English command support.
- Preserve the existing vocabulary-driven language structure.
- Add command equivalents through explicit vocabulary entries, not machine translation of a final caption and not fuzzy arbitrary intent parsing.
- Do not claim that every human language is guaranteed; recognize only languages and phrases explicitly covered by the vocabulary and speech-recognition model.

## Files likely involved

- `echosub/voice_commands.py` — command registry, parsing, media controller, safe validation.
- `echosub/voice_command_ui.py` — application action wiring and tray feedback.
- `echosub/voice_vocabulary.py` — language-specific words.
- `echosub/settings_voice_commands.py` — Commands settings tab.
- `echosub/settings_dialog.py` — settings tab registration and save values.
- `echosub/caption_widgets.py` — badge and on-screen presentation.
- `tests/test_voice_commands.py`
- `tests/test_voice_command_ui.py`
- `tests/test_microphone.py`

## Mandatory validation

Run targeted tests after each logical batch:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_voice_commands tests.test_voice_command_ui -v
.\.venv\Scripts\python.exe -m compileall -q echosub
```

For presentation changes, launch EchoSub and visually verify: a microphone speaker label appears as a distinct header above text, no label overlaps caption text, and RTL text remains readable.

## Safety constraints

- No shell, PowerShell, CMD, Bash, WSL, registry, filesystem, deletion, process-kill, remote-control, browser automation, clipboard, or arbitrary-program commands from speech.
- No hidden background speech actions: every command requires the user-enabled feature and a wake word.
- Keep media control to fixed Windows media keys.
- Keep custom commands as mappings to approved registry actions or local on-screen response cards only.
