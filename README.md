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
