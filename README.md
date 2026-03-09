# sttc

Hotkey-driven speech-to-text clipboard tool.

1. Press your hotkey (default: `Ctrl+Shift`) to start recording.
2. Press the same hotkey again to finish transcription.
3. Transcript is copied to clipboard.
4. Use your quit hotkey (default: `Ctrl+Alt+Q`) to exit the app.

## Quick Install (Recommended)

- **Windows:** Download `sttc-windows-x64.exe` from the latest GitHub Release and double-click to run.
- **macOS:** Download `sttc-macos-x64.app.zip` from the latest GitHub Release, unzip it, and move it to Applications.
- **Linux:** Download `sttc-linux-x64.AppImage` from the latest GitHub Release, make it executable (`chmod +x sttc-linux-x64.AppImage`), and run it.

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

## GUI-First Run Mode

```bash
# Default on all desktop platforms: opens mini GUI + settings
uv run sttc run

# Launch GUI hidden/minimized (tray when available)
uv run sttc run --minimized

# Optional advanced/headless mode (no GUI)
uv run sttc run --cli
```

Behavior:

- `sttc run` is GUI-first by default.
- Mini window is the main control surface (state + mic + settings).
- Settings opens a larger dialog for model/API/hotkeys/autostart/runtime options.
- Tray icon is optional and used when supported by the desktop session.
- Closing the mini window hides it; app keeps running until quit.

`.env` GUI keys:

- `ENABLE_GUI=false`
- `GUI_START_MINIMIZED=false`

## First Launch and Setup

On the first launch, STTC now runs a real onboarding flow before it starts the transcription engine.

- GUI launches show a short onboarding dialog before any Whisper download or hotkey listener starts.
- `uv run sttc run --cli` runs a matching text setup flow when onboarding is incomplete and the terminal is interactive.
- Non-interactive CLI runs fail with guidance instead of silently marking setup complete.
- Onboarding is tracked with `ONBOARDING_VERSION` in the saved config, not a separate marker file.

You can rerun onboarding any time:

```bash
uv run sttc setup
uv run sttc setup --cli
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
- Set `RECORDING_HOTKEY` (for example `ctrl+shift`, `ctrl+alt+r`, `f8`).
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

## Advanced CLI Mode

Use CLI mode for diagnostics, scripting, or headless usage:

```bash
uv run sttc run --cli
```

## Linux prerequisites (Ubuntu)

`uv sync` installs Python packages only. Audio/clipboard system libraries must be installed via `apt`.

```bash
sudo apt-get update
sudo apt-get install -y libportaudio2 xclip
```

Wayland users can install `wl-clipboard` (`wl-copy`) instead of `xclip`:

```bash
sudo apt-get install -y libportaudio2 wl-clipboard
```

## Build Native Executable

```bash
uv run python scripts/build.py
```

Build artifact:

- `dist/sttc` (`dist/sttc.exe` on Windows): GUI-first binary (no terminal window on Windows).

## Development checks

```bash
uv run pytest
uv run ruff check .
uv run mypy src
```
