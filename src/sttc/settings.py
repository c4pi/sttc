"""Application settings."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
from typing import Literal

from pydantic import Field, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_NAME = "sttc"
ENV_FILENAME = ".env"
ENV_EXAMPLE_FILENAME = ".env.example"
WHISPER_SAMPLE_RATE = 16000
CURRENT_ONBOARDING_VERSION = 1
_DEFAULT_HOTKEYS = {
    "recording_hotkey": "ctrl+alt+a",
    "refine_hotkey": "ctrl+alt+r",
    "record_and_refine_hotkey": "ctrl+alt+w",
    "summary_hotkey": "ctrl+alt+s",
    "translation_hotkey": "ctrl+alt+t",
    "quit_hotkey": "ctrl+alt+q",
}


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


def get_source_checkout_root() -> Path | None:
    """Return the repository root when running from a source checkout."""
    package_dir = Path(__file__).resolve().parent
    src_dir = package_dir.parent
    if src_dir.name != "src":
        return None

    project_root = src_dir.parent
    if not (project_root / "pyproject.toml").exists():
        return None
    if (project_root / "src" / "sttc").resolve() != package_dir:
        return None
    return project_root


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


def get_user_env_file_path() -> Path:
    """Return the per-user env path, creating the config directory if needed."""
    config_dir = get_user_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / ENV_FILENAME


def ensure_bundled_env_file() -> tuple[Path, bool]:
    """Create user .env from bundled .env.example if missing.

    Returns the env path and whether the file was newly created.
    """
    env_path = get_user_env_file_path()
    if env_path.exists():
        return env_path, False

    env_example_path = get_resource_path(ENV_EXAMPLE_FILENAME)
    if env_example_path.exists():
        shutil.copyfile(env_example_path, env_path)
    else:
        env_path.touch()
    return env_path, True


def resolve_env_file_path() -> Path:
    """Resolve which env file should be used for this runtime mode."""
    source_root = get_source_checkout_root()
    if source_root is not None:
        return source_root / ENV_FILENAME
    return get_user_env_file_path()


def format_hotkey(hotkey: str) -> str:
    return "+".join(part.upper() if len(part) == 1 else part.capitalize() for part in hotkey.split("+"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        _settings_cls: type[BaseSettings],
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ) -> tuple:
        """Prefer the explicitly resolved env file over inherited shell variables."""
        return init_settings, dotenv_settings, env_settings, file_secret_settings

    app_env: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    onboarding_version: int | None = None
    openai_api_key: str | None = None

    stt_model: str | None = None
    refine_model: str = "gpt-4.1-mini"
    stt_chunk_seconds: int = Field(default=15, ge=1)
    stt_whisper_model: str = "base"
    stt_model_cache_dir: str | None = None
    sample_rate_target: int = Field(default=WHISPER_SAMPLE_RATE, ge=8000)
    channels: int = Field(default=1, ge=1)
    recording_mode: Literal["hold", "toggle"] = "toggle"
    recording_hotkey: str = _DEFAULT_HOTKEYS["recording_hotkey"]
    refine_hotkey: str = _DEFAULT_HOTKEYS["refine_hotkey"]
    record_and_refine_hotkey: str = _DEFAULT_HOTKEYS["record_and_refine_hotkey"]
    summary_hotkey: str = _DEFAULT_HOTKEYS["summary_hotkey"]
    translation_hotkey: str = _DEFAULT_HOTKEYS["translation_hotkey"]
    quit_hotkey: str = _DEFAULT_HOTKEYS["quit_hotkey"]
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

    @field_validator(
        "recording_hotkey",
        "refine_hotkey",
        "record_and_refine_hotkey",
        "summary_hotkey",
        "translation_hotkey",
        "quit_hotkey",
        mode="before",
    )
    @classmethod
    def _coerce_hotkey(cls, value: object, info: ValidationInfo) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip().lower().replace(" ", "")
        field_name = info.field_name
        if field_name is None:
            return normalized
        return normalized or _DEFAULT_HOTKEYS[field_name]

    @field_validator("stt_model", "stt_model_cache_dir", mode="before")
    @classmethod
    def _coerce_optional_string(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if not normalized:
            return None
        return normalized

    @field_validator("refine_model", mode="before")
    @classmethod
    def _coerce_refine_model(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or "gpt-4.1-mini"

    @field_validator("sample_rate_target", mode="before")
    @classmethod
    def _force_whisper_sample_rate(cls, _value: object) -> int:
        return WHISPER_SAMPLE_RATE

    @model_validator(mode="after")
    def _validate_hotkeys(self) -> Settings:
        active_hotkeys = {
            "recording_hotkey": self.recording_hotkey,
            "quit_hotkey": self.quit_hotkey,
        }
        if self.refinement_hotkeys_enabled:
            active_hotkeys.update(
                {
                    "refine_hotkey": self.refine_hotkey,
                    "record_and_refine_hotkey": self.record_and_refine_hotkey,
                    "summary_hotkey": self.summary_hotkey,
                    "translation_hotkey": self.translation_hotkey,
                }
            )

        seen: dict[str, str] = {}
        for field_name, hotkey in active_hotkeys.items():
            other = seen.get(hotkey)
            if other is not None:
                msg = f"{field_name} and {other} must be different"
                raise ValueError(msg)
            seen[hotkey] = field_name
        return self

    @property
    def model_cache_dir(self) -> Path | None:
        if self.stt_model_cache_dir:
            return Path(self.stt_model_cache_dir).expanduser()
        return get_default_model_cache_dir()

    @property
    def refinement_hotkeys_enabled(self) -> bool:
        return bool(self.openai_api_key and self.openai_api_key.strip())

    @property
    def refinement_warning_lines(self) -> tuple[str, str]:
        return (
            "WARNING: No OPENAI_API_KEY found. Refinement hotkeys "
            f"({format_hotkey(self.refine_hotkey)}, {format_hotkey(self.record_and_refine_hotkey)}, "
            f"{format_hotkey(self.summary_hotkey)}, {format_hotkey(self.translation_hotkey)}) are disabled.",
            "   Set OPENAI_API_KEY in your .env to enable them.",
        )


def get_settings() -> Settings:
    """Create a fresh settings object."""
    return Settings(_env_file=resolve_env_file_path())  # type: ignore[call-arg]
