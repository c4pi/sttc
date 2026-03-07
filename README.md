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

## GUI Mode

```bash
# Launch tiny GUI window + settings
uv run sttc run --gui

# Launch GUI hidden/minimized (tray when available)
uv run sttc run --gui --minimized
```

Behavior:

- Mini window is the main control surface (state + mic + settings).
- Settings opens a larger dialog for model/API/hotkeys/autostart/runtime options.
- Tray icon is optional and used when supported by the desktop session.
- Closing the mini window hides it; app keeps running until quit.

`.env` GUI keys:

- `ENABLE_GUI=false`
- `GUI_START_MINIMIZED=false`

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

## First Launch

When you start the bundled executable for the first time, STTC asks:

- Whether auto-start on login should be enabled (`y/n`, mandatory).
- Whether you want to configure an API key now (`y/n`, mandatory).

If no API key is configured, STTC downloads the local Whisper model after setup.

## Runtime configuration

`sttc` loads settings from `.env` using `src/sttc/settings.py`.

- Set `STT_MODEL` for cloud transcription via LiteLLM.
- Set `OPENAI_API_KEY` (or provider-specific key) when using cloud models.
- Leave `STT_MODEL` empty for local `faster-whisper`.
- Set `STT_MODEL_CACHE_DIR` to override the local model cache location.
- Set `RECORDING_MODE=toggle` (default) or `RECORDING_MODE=hold`.
- Set `RECORDING_HOTKEY` (for example `ctrl+shift`, `ctrl+alt+r`, `f8`).
- Set `QUIT_HOTKEY` for exiting the app (for example `ctrl+alt+q`, `ctrl+shift+escape`).

## Auto-Start

```bash
uv run sttc autostart enable
uv run sttc autostart disable
uv run sttc autostart status
```

## Build Native Executable

```bash
uv run python scripts/build.py
```

## Development checks

```bash
uv run pytest
uv run ruff check .
uv run mypy src
```
