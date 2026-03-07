"""Application settings."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_NAME = "sttc"
ENV_FILENAME = ".env"
ENV_EXAMPLE_FILENAME = ".env.example"


def is_bundled_executable() -> bool:
    """Return True when running from a PyInstaller bundle."""
    return vars(sys).get("_MEIPASS") is not None


def get_user_config_dir() -> Path:
    """Return the per-user configuration directory for this platform."""
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / APP_NAME
        return Path.home() / "AppData" / "Roaming" / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return Path.home() / ".config" / APP_NAME


def get_resource_path(filename: str) -> Path:
    """Return the path to a bundled or local resource file."""
    bundle_root = vars(sys).get("_MEIPASS")
    if bundle_root is not None:
        return Path(bundle_root) / filename
    return Path(filename)


def get_default_model_cache_dir() -> Path | None:
    """Return the default local model cache directory."""
    if is_bundled_executable():
        return get_user_config_dir() / "models"
    return None


def ensure_bundled_env_file() -> tuple[Path, bool]:
    """Create user .env from bundled .env.example if missing.

    Returns the env path and whether the file was newly created.
    """
    config_dir = get_user_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)

    env_path = config_dir / ENV_FILENAME
    if env_path.exists():
        return env_path, False

    env_example_path = get_resource_path(ENV_EXAMPLE_FILENAME)
    if env_example_path.exists():
        shutil.copyfile(env_example_path, env_path)
    else:
        env_path.touch()
    return env_path, True


def resolve_env_file_path() -> Path | str:
    """Resolve which env file should be used for this runtime mode."""
    if is_bundled_executable():
        config_dir = get_user_config_dir()
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / ENV_FILENAME
    return ENV_FILENAME


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    openai_api_key: str | None = None

    stt_model: str | None = None
    stt_chunk_seconds: int = Field(default=15, ge=1)
    stt_whisper_model: str = "base"
    stt_model_cache_dir: str | None = None
    sample_rate_target: int = Field(default=16000, ge=8000)
    channels: int = Field(default=1, ge=1)
    recording_mode: Literal["hold", "toggle"] = "toggle"
    recording_hotkey: str = "ctrl+shift"
    quit_hotkey: str = "ctrl+alt+q"
    enable_gui: bool = False
    gui_start_minimized: bool = False

    @field_validator("debug", mode="before")
    @classmethod
    def _coerce_debug(cls, value: object) -> object:
        if not isinstance(value, str):
            return value

        normalized = value.strip().lower()
        if normalized in {"release", "prod", "production"}:
            return False
        if normalized in {"debug", "dev", "development"}:
            return True
        return value

    @field_validator("recording_mode", mode="before")
    @classmethod
    def _coerce_recording_mode(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return value.strip().lower()

    @field_validator("recording_hotkey", mode="before")
    @classmethod
    def _coerce_recording_hotkey(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip().lower().replace(" ", "")
        return normalized or "ctrl+shift"

    @field_validator("quit_hotkey", mode="before")
    @classmethod
    def _coerce_quit_hotkey(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip().lower().replace(" ", "")
        return normalized or "ctrl+alt+q"

    @field_validator("stt_model", "stt_model_cache_dir", mode="before")
    @classmethod
    def _coerce_optional_string(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if not normalized:
            return None
        return normalized

    @model_validator(mode="after")
    def _validate_hotkeys(self) -> Settings:
        if self.recording_hotkey == self.quit_hotkey:
            msg = "recording_hotkey and quit_hotkey must be different"
            raise ValueError(msg)
        return self

    @property
    def model_cache_dir(self) -> Path | None:
        if self.stt_model_cache_dir:
            return Path(self.stt_model_cache_dir).expanduser()
        return get_default_model_cache_dir()


def get_settings() -> Settings:
    """Create a fresh settings object."""
    return Settings(_env_file=resolve_env_file_path())  # type: ignore[call-arg]
