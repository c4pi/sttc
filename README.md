# sttc

Hotkey-driven speech-to-text clipboard tool.

1. Press your hotkey (default: `Ctrl+Alt+A`) to start recording.
2. Press the same hotkey again to finish transcription.
3. Transcript is copied to clipboard.
4. Use your quit hotkey (default: `Ctrl+Alt+Q`) to exit the app.

## Quick Install (Recommended)

- STTC is currently supported and released for Windows only.
- **Windows:** Download `sttc-windows-x64.exe` from the latest GitHub Release and double-click to run.
- macOS and Linux support remains in the codebase for now, but is not currently documented or released as an officially supported target.

## Development Setup

```bash
uv sync
cp .env.example .env
uv run sttc --help
uv run sttc run
```

Install GUI dependencies for source runs:

```bash
uv sync --extra gui
```

## Run Modes

```bash
# Default terminal behavior: headless / CLI mode
uv run sttc run

# Launch the GUI explicitly
uv run sttc run --gui

# Launch GUI hidden/minimized (tray when available)
uv run sttc run --gui --minimized
```

Behavior:

- `sttc run` is CLI/headless by default.
- `sttc run --gui` opens the mini GUI + settings window.
- Settings opens a larger dialog for model/API/hotkeys/autostart/runtime options.
- Tray icon is optional and used on supported Windows setups.
- Closing the mini window hides it; app keeps running until quit.

`.env` GUI keys:

- `ENABLE_GUI=false`
- `GUI_START_MINIMIZED=false`

## First Launch and Setup

On the first launch, STTC now runs a real onboarding flow before it starts the transcription engine.

- GUI launches show a short onboarding dialog before any Whisper download or hotkey listener starts.
- `uv run sttc run` runs the matching text setup flow when onboarding is incomplete and the terminal is interactive.
- Non-interactive CLI runs fail with guidance instead of silently marking setup complete.
- Onboarding is tracked with `ONBOARDING_VERSION` in the saved config, not a separate marker file.

You can rerun onboarding any time:

```bash
uv run sttc setup
uv run sttc setup --gui
```

If you choose local Whisper during onboarding, the model download begins only after you finish setup.

## Runtime configuration

`sttc` loads settings from `.env` using `src/sttc/settings.py`.

- Set `STT_MODEL` for cloud transcription via LiteLLM.
- Set `OPENAI_API_KEY` (or provider-specific key) when using cloud models.
- Leave `STT_MODEL` empty for local `faster-whisper`.
- Set `STT_WHISPER_MODEL` to one of the curated onboarding defaults such as `tiny`, `base`, `small`, `medium`, or `large-v3`.
- Set `STT_MODEL_CACHE_DIR` to override the local model cache location.
- Set `RECORDING_MODE=toggle` (default) or `RECORDING_MODE=hold`.
- Set `RECORDING_HOTKEY` (for example `ctrl+alt+a`, `ctrl+alt+r`, `f8`).
- Set `QUIT_HOTKEY` for exiting the app (for example `ctrl+alt+q`, `ctrl+shift+escape`).
- Set `ONBOARDING_VERSION=1` when setup has completed successfully.

## Auto-Start

```bash
uv run sttc autostart enable
uv run sttc autostart disable
uv run sttc autostart status
```

Behavior:

- Autostart triggers when your desktop login session starts.
- Screen lock/unlock does not trigger autostart (`Win + L` on Windows is lock, not logout/login).
- If autostart is enabled and GUI/minimized preferences change in Settings or onboarding, STTC rewrites the autostart command to match current preferences.

## Build Native Executable

```bash
uv run python scripts/build.py
```

Build artifact:

- `dist/sttc.exe`: Windows executable (no terminal window).

## Development checks

```bash
uv run pytest
uv run ruff check .
uv run mypy src
```
