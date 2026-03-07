"""Helpers for updating STTC .env values while preserving existing file content."""

from __future__ import annotations

from pathlib import Path
import re

from sttc.settings import resolve_env_file_path

_ENV_ASSIGNMENT_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=.*$")


def _resolve_target_path(env_path: Path | None) -> Path:
    if env_path is not None:
        return env_path

    resolved = resolve_env_file_path()
    return Path(resolved)


def _serialize_env_value(value: bool | int | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def upsert_env_values(
    updates: dict[str, bool | int | str | None],
    *,
    env_path: Path | None = None,
) -> Path:
    """Update or append env keys and write atomically."""
    target_path = _resolve_target_path(env_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    existing_lines: list[str] = []
    if target_path.exists():
        existing_lines = target_path.read_text(encoding="utf-8").splitlines()

    remaining = {key: _serialize_env_value(value) for key, value in updates.items()}
    output_lines: list[str] = []

    for line in existing_lines:
        match = _ENV_ASSIGNMENT_RE.match(line)
        if match is None:
            output_lines.append(line)
            continue

        key = match.group(1)
        if key in remaining:
            output_lines.append(f"{key}={remaining.pop(key)}")
        else:
            output_lines.append(line)

    for key, value in remaining.items():
        output_lines.append(f"{key}={value}")

    serialized = "\n".join(output_lines).rstrip("\n") + "\n"
    temp_path = target_path.with_suffix(target_path.suffix + ".tmp")
    temp_path.write_text(serialized, encoding="utf-8")
    temp_path.replace(target_path)
    return target_path
