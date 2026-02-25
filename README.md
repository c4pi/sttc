# sttc
## speech to text clipboard

Speech-to-text with hotkey. Hold `Ctrl+Shift` to record, release to transcribe to clipboard.

**Install:** `uv sync` then `uv run audio-prompter`

**Config:** Create `.env` with `GEMINI_API_KEY=your_key` (or use `TRANSCRIPTION_BACKEND=whisper` for local)

## Requirements

- Python 3.12+
- [UV](https://docs.astral.sh/uv/) (recommended)

## Quick start

```bash
uv sync
cp .env.example .env
uv run sttc --help
uv run pytest
```

## Project structure

```
sttc/
├── .env.example
├── .gitignore
├── .pre-commit-config.yaml
├── .secrets.baseline
├── .github/
│   └── workflows/
│       └── ci.yml
├── README.md
├── LICENSE               # when license=MIT
├── main.py
├── pyproject.toml
├── src/
│   └── sttc/
│       ├── __init__.py
│       ├── cli.py
│       └── settings.py
└── tests/
    ├── __init__.py
    └── test_sttc.py
```

## Development commands

| Command                             | Description                          |
| ----------------------------------- | ------------------------------------ |
| `uv sync --all-extras --dev`        | Install runtime and dev dependencies |
| `uv run ruff check .`               | Lint                                 |
| `uv run mypy src`                   | Type-check                           |
| `uv run pytest -q`                  | Run tests                            |
| `uv run pre-commit run --all-files` | Run all pre-commit hooks             |

## Settings

The default configuration lives in `src/sttc/settings.py` and is loaded from `.env`.

1. Copy `.env.example` to `.env`.
2. Adjust values for your environment.

## CI

A starter GitHub Actions workflow is included at `.github/workflows/ci.yml`.
It runs lint, type-checking, and tests on Linux, macOS, and Windows on push/PR.

## License


MIT (see `LICENSE`).

