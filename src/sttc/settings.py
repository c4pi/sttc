"""Application settings."""

from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    stt_model: str | None = None
    stt_chunk_seconds: int = Field(default=15, ge=1)
    stt_whisper_model: str = "base"
    sample_rate_target: int = Field(default=16000, ge=8000)
    channels: int = Field(default=1, ge=1)
    recording_mode: Literal["hold", "toggle"] = "toggle"
    recording_hotkey: str = "ctrl+shift"
    quit_hotkey: str = "ctrl+alt+q"

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

    @model_validator(mode="after")
    def _validate_hotkeys(self) -> "Settings":
        if self.recording_hotkey == self.quit_hotkey:
            msg = "recording_hotkey and quit_hotkey must be different"
            raise ValueError(msg)
        return self


def get_settings() -> Settings:
    """Create a fresh settings object."""
    return Settings()
