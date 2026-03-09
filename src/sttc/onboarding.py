"""Shared onboarding state and persistence helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from sttc.autostart import is_autostart_enabled, sync_autostart
from sttc.gui.env_editor import upsert_env_values
from sttc.settings import CURRENT_ONBOARDING_VERSION, Settings

if TYPE_CHECKING:
    from pathlib import Path

DEFAULT_CLOUD_MODEL = "openai/gpt-4o-mini-transcribe"
CURATED_WHISPER_MODELS = ["tiny", "base", "small", "medium", "large-v3"]

Backend = Literal["local", "cloud"]
RecordingMode = Literal["hold", "toggle"]


@dataclass(slots=True)
class OnboardingValues:
    backend: Backend
    cloud_model: str
    openai_api_key: str
    whisper_model: str
    recording_mode: RecordingMode
    recording_hotkey: str
    quit_hotkey: str
    autostart_enabled: bool
    enable_gui: bool
    gui_start_minimized: bool

    def to_settings(self, base_settings: Settings) -> Settings:
        base_values = base_settings.model_dump()
        base_values.update(
            {
                "onboarding_version": CURRENT_ONBOARDING_VERSION,
                "stt_model": self.cloud_model.strip() or DEFAULT_CLOUD_MODEL if self.backend == "cloud" else None,
                "openai_api_key": self.openai_api_key.strip() or None,
                "stt_whisper_model": self.whisper_model.strip() or "base",
                "recording_mode": self.recording_mode,
                "recording_hotkey": normalize_hotkey(self.recording_hotkey),
                "quit_hotkey": normalize_hotkey(self.quit_hotkey),
                "enable_gui": self.enable_gui,
                "gui_start_minimized": self.gui_start_minimized,
            }
        )
        return Settings(**base_values)

    def env_updates(self) -> dict[str, bool | int | str | None]:
        stt_model = ""
        if self.backend == "cloud":
            stt_model = self.cloud_model.strip() or DEFAULT_CLOUD_MODEL

        return {
            "ONBOARDING_VERSION": CURRENT_ONBOARDING_VERSION,
            "STT_MODEL": stt_model,
            "OPENAI_API_KEY": self.openai_api_key.strip(),
            "STT_WHISPER_MODEL": self.whisper_model.strip() or "base",
            "RECORDING_MODE": self.recording_mode,
            "RECORDING_HOTKEY": normalize_hotkey(self.recording_hotkey),
            "QUIT_HOTKEY": normalize_hotkey(self.quit_hotkey),
            "ENABLE_GUI": self.enable_gui,
            "GUI_START_MINIMIZED": self.gui_start_minimized,
        }


def normalize_hotkey(value: str) -> str:
    return value.strip().lower().replace(" ", "")


def is_onboarding_complete(settings: Settings) -> bool:
    return settings.onboarding_version == CURRENT_ONBOARDING_VERSION


def default_onboarding_values(
    settings: Settings,
    *,
    autostart_enabled: bool | None = None,
) -> OnboardingValues:
    return OnboardingValues(
        backend="cloud" if settings.stt_model else "local",
        cloud_model=settings.stt_model or DEFAULT_CLOUD_MODEL,
        openai_api_key=settings.openai_api_key or "",
        whisper_model=settings.stt_whisper_model or "base",
        recording_mode=settings.recording_mode,
        recording_hotkey=settings.recording_hotkey,
        quit_hotkey=settings.quit_hotkey,
        autostart_enabled=is_autostart_enabled() if autostart_enabled is None else autostart_enabled,
        enable_gui=settings.enable_gui,
        gui_start_minimized=settings.gui_start_minimized,
    )


def onboarding_required_message() -> str:
    return "Onboarding is incomplete. Run `sttc setup --cli` or start the GUI once to finish setup."


def persist_onboarding_values(base_settings: Settings, values: OnboardingValues) -> tuple[Settings, Path]:
    new_settings = values.to_settings(base_settings)
    env_path = upsert_env_values(values.env_updates())
    sync_autostart(
        values.autostart_enabled,
        gui=new_settings.enable_gui,
        minimized=new_settings.gui_start_minimized,
    )
    return new_settings, env_path
