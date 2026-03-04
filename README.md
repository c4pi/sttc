# sttc

Hotkey-driven speech-to-text clipboard tool.

1. Press your hotkey (default: `Ctrl+Shift`) to start recording.
2. Press the same hotkey again to finish transcription.
3. Transcript is copied to clipboard.
4. Use your quit hotkey (default: `Ctrl+Alt+Q`) to exit the app.

## Quick start

```bash
uv sync
cp .env.example .env
uv run sttc --help
uv run sttc run
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

## Runtime configuration

`sttc` loads settings from `.env` using `src/sttc/settings.py`.

- Set `STT_MODEL` for cloud transcription via LiteLLM.
- Leave `STT_MODEL` empty for local `faster-whisper`.
- Set `RECORDING_MODE=toggle` (default) or `RECORDING_MODE=hold`.
- Set `RECORDING_HOTKEY` (for example `ctrl+shift`, `ctrl+alt+r`, `f8`).
- Set `QUIT_HOTKEY` for exiting the app (for example `ctrl+alt+q`, `ctrl+shift+escape`).

## Development checks

```bash
uv run pytest
uv run ruff check .
uv run mypy src
```
