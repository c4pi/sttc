from pathlib import Path

from sttc.onboarding import (
    DEFAULT_CLOUD_MODEL,
    OnboardingValues,
    default_onboarding_values,
    is_onboarding_complete,
    persist_onboarding_values,
)
from sttc.settings import CURRENT_ONBOARDING_VERSION, Settings


def test_is_onboarding_complete_checks_version() -> None:
    assert is_onboarding_complete(Settings(_env_file=None, onboarding_version=None)) is False
    assert is_onboarding_complete(Settings(_env_file=None, onboarding_version=CURRENT_ONBOARDING_VERSION)) is True


def test_default_onboarding_values_follow_current_settings() -> None:
    settings = Settings(
        _env_file=None,
        onboarding_version=CURRENT_ONBOARDING_VERSION,
        stt_model="openai/gpt-4o-mini-transcribe",
        openai_api_key="test-api-key",  # pragma: allowlist secret
        recording_mode="hold",
        recording_hotkey="ctrl+alt+r",
        quit_hotkey="ctrl+shift+q",
        enable_gui=True,
        gui_start_minimized=True,
    )

    values = default_onboarding_values(settings, autostart_enabled=True)

    assert values.backend == "cloud"
    assert values.cloud_model == "openai/gpt-4o-mini-transcribe"
    assert values.openai_api_key == "sk-test" # pragma: allowlist secret
    assert values.recording_mode == "hold"
    assert values.enable_gui is True
    assert values.gui_start_minimized is True
    assert values.autostart_enabled is True


def test_onboarding_values_to_settings_marks_onboarding_complete() -> None:
    values = OnboardingValues(
        backend="local",
        cloud_model=DEFAULT_CLOUD_MODEL,
        openai_api_key="",
        whisper_model="small",
        recording_mode="toggle",
        recording_hotkey=" CTRL + ALT + R ",
        quit_hotkey=" CTRL + SHIFT + Q ",
        autostart_enabled=False,
        enable_gui=True,
        gui_start_minimized=False,
    )

    settings = values.to_settings(Settings(_env_file=None))

    assert settings.onboarding_version == CURRENT_ONBOARDING_VERSION
    assert settings.stt_model is None
    assert settings.stt_whisper_model == "small"
    assert settings.recording_hotkey == "ctrl+alt+r"
    assert settings.quit_hotkey == "ctrl+shift+q"
    assert settings.enable_gui is True


def test_persist_onboarding_values_updates_env_and_autostart(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    saved = {}
    sync_calls = []
    env_path = Path("C:/temp/.env")

    def fake_upsert(updates, *, env_path=None):
        saved.update(updates)
        return Path("C:/temp/.env")

    def fake_sync(enabled: bool, *, gui: bool, minimized: bool) -> None:
        sync_calls.append((enabled, gui, minimized))

    monkeypatch.setattr("sttc.onboarding.upsert_env_values", fake_upsert)
    monkeypatch.setattr("sttc.onboarding.sync_autostart", fake_sync)

    values = OnboardingValues(
        backend="cloud",
        cloud_model="openai/gpt-4o-mini-transcribe",
        openai_api_key="live-api-key",  # pragma: allowlist secret
        whisper_model="base",
        recording_mode="hold",
        recording_hotkey="ctrl+alt+r",
        quit_hotkey="ctrl+shift+q",
        autostart_enabled=True,
        enable_gui=True,
        gui_start_minimized=True,
    )

    settings, persisted_path = persist_onboarding_values(Settings(_env_file=None), values)

    assert persisted_path == env_path
    assert settings.onboarding_version == CURRENT_ONBOARDING_VERSION
    assert saved["ONBOARDING_VERSION"] == CURRENT_ONBOARDING_VERSION
    assert saved["STT_MODEL"] == "openai/gpt-4o-mini-transcribe"
    assert saved["OPENAI_API_KEY"] == "sk-live" # pragma: allowlist secret
    assert sync_calls == [(True, True, True)]
