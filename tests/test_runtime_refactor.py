from click.testing import CliRunner
import pytest

from sttc.cli import cli_group
from sttc.settings import Settings
from sttc.transcriber import build_transcriber


def test_settings_extended_defaults() -> None:
    s = Settings(_env_file=None)
    assert s.stt_model is None
    assert s.stt_chunk_seconds == 15
    assert s.stt_whisper_model == "base"
    assert s.sample_rate_target == 16000
    assert s.channels == 1
    assert s.recording_mode == "toggle"
    assert s.recording_hotkey == "ctrl+shift"
    assert s.quit_hotkey == "ctrl+alt+q"


def test_settings_recording_hotkey_normalizes() -> None:
    s = Settings(_env_file=None, recording_hotkey=" CTRL + Alt + R ")
    assert s.recording_hotkey == "ctrl+alt+r"


def test_settings_quit_hotkey_normalizes() -> None:
    s = Settings(_env_file=None, quit_hotkey=" CTRL + SHIFT + ESCAPE ")
    assert s.quit_hotkey == "ctrl+shift+escape"


def test_settings_hotkeys_must_differ() -> None:
    with pytest.raises(ValueError, match="must be different"):
        Settings(_env_file=None, recording_hotkey="ctrl+shift", quit_hotkey="ctrl+shift")


def test_cli_run_calls_app(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    called = {"value": False}

    def fake_run(settings: Settings) -> None:
        called["value"] = True
        assert isinstance(settings, Settings)

    monkeypatch.setattr("sttc.cli.run_app", fake_run)

    runner = CliRunner()
    result = runner.invoke(cli_group, ["run"])
    assert result.exit_code == 0
    assert called["value"] is True


def test_transcriber_selection_cloud(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(stt_model="whisper-1")
    sentinel = object()

    monkeypatch.setattr("sttc.transcriber._build_cloud_transcriber", lambda _m: sentinel)
    monkeypatch.setattr("sttc.transcriber._build_local_transcriber", lambda **_kwargs: None)

    assert build_transcriber(settings) is sentinel


def test_transcriber_selection_local(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(stt_model=None, stt_whisper_model="small")
    sentinel = object()

    monkeypatch.setattr("sttc.transcriber._build_cloud_transcriber", lambda _m: None)
    monkeypatch.setattr(
        "sttc.transcriber._build_local_transcriber", lambda **_kwargs: sentinel
    )

    assert build_transcriber(settings) is sentinel
