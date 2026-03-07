from click.testing import CliRunner
import pytest

import sttc.cli as cli_module
from sttc.cli import cli_group
from sttc.settings import Settings
from sttc.transcriber import build_transcriber


def test_settings_extended_defaults() -> None:
    s = Settings(_env_file=None, stt_model=None)
    assert s.stt_model is None
    assert s.stt_chunk_seconds == 15
    assert s.stt_whisper_model == "base"
    assert s.stt_model_cache_dir is None
    assert s.model_cache_dir is None
    assert s.sample_rate_target == 16000
    assert s.channels == 1
    assert s.recording_mode == "toggle"
    assert s.recording_hotkey == "ctrl+shift"
    assert s.quit_hotkey == "ctrl+alt+q"
    assert s.enable_gui is False
    assert s.gui_start_minimized is False


def test_settings_recording_hotkey_normalizes() -> None:
    s = Settings(_env_file=None, recording_hotkey=" CTRL + Alt + R ")
    assert s.recording_hotkey == "ctrl+alt+r"


def test_settings_quit_hotkey_normalizes() -> None:
    s = Settings(_env_file=None, quit_hotkey=" CTRL + SHIFT + ESCAPE ")
    assert s.quit_hotkey == "ctrl+shift+escape"


def test_settings_optional_strings_normalize() -> None:
    s = Settings(_env_file=None, stt_model="  ", stt_model_cache_dir=" ")
    assert s.stt_model is None
    assert s.stt_model_cache_dir is None


def test_settings_hotkeys_must_differ() -> None:
    with pytest.raises(ValueError, match="must be different"):
        Settings(_env_file=None, recording_hotkey="ctrl+shift", quit_hotkey="ctrl+shift")


def test_cli_run_calls_setup_and_app(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    called = {"setup": False, "run": False}

    def fake_setup(settings: Settings) -> None:
        called["setup"] = True
        assert isinstance(settings, Settings)

    def fake_run(settings: Settings) -> None:
        called["run"] = True
        assert isinstance(settings, Settings)

    monkeypatch.setattr("sttc.cli.run_first_launch_setup", fake_setup)
    monkeypatch.setattr("sttc.cli._load_run_app", lambda: fake_run)

    runner = CliRunner()
    result = runner.invoke(cli_group, ["run"])
    assert result.exit_code == 0
    assert called["setup"] is True
    assert called["run"] is True


def test_cli_run_with_gui_flag_calls_gui_app(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    called = {"setup": False, "gui": False, "headless": False}

    def fake_setup(_settings: Settings) -> None:
        called["setup"] = True

    def fake_run_gui(_settings: Settings, minimized: bool) -> None:
        called["gui"] = True
        assert minimized is False

    def fake_headless(_settings: Settings) -> None:
        called["headless"] = True

    monkeypatch.setattr("sttc.cli.run_first_launch_setup", fake_setup)
    monkeypatch.setattr("sttc.cli._load_run_gui", lambda: fake_run_gui)
    monkeypatch.setattr("sttc.cli._load_run_app", lambda: fake_headless)

    runner = CliRunner()
    result = runner.invoke(cli_group, ["run", "--gui"])
    assert result.exit_code == 0
    assert called["setup"] is True
    assert called["gui"] is True
    assert called["headless"] is False


def test_cli_run_uses_enable_gui_setting(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    called = {"gui": False}

    def fake_get_settings() -> Settings:
        return Settings(_env_file=None, enable_gui=True, gui_start_minimized=True)

    def fake_setup(_settings: Settings) -> None:
        return

    def fake_run_gui(_settings: Settings, minimized: bool) -> None:
        called["gui"] = True
        assert minimized is True

    monkeypatch.setattr("sttc.cli.get_settings", fake_get_settings)
    monkeypatch.setattr("sttc.cli.run_first_launch_setup", fake_setup)
    monkeypatch.setattr("sttc.cli._load_run_gui", lambda: fake_run_gui)

    runner = CliRunner()
    result = runner.invoke(cli_group, ["run"])
    assert result.exit_code == 0
    assert called["gui"] is True


def test_cli_run_minimized_requires_gui(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("sttc.cli.run_first_launch_setup", lambda _settings: None)

    runner = CliRunner()
    result = runner.invoke(cli_group, ["run", "--minimized"])
    assert result.exit_code != 0
    assert "requires GUI mode" in result.output


def test_cli_autostart_enable(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    called = {"value": False}

    def fake_enable() -> None:
        called["value"] = True

    monkeypatch.setattr("sttc.cli.enable_autostart", fake_enable)

    runner = CliRunner()
    result = runner.invoke(cli_group, ["autostart", "enable"])
    assert result.exit_code == 0
    assert called["value"] is True


def test_cli_autostart_status(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("sttc.cli.is_autostart_enabled", lambda: True)

    runner = CliRunner()
    result = runner.invoke(cli_group, ["autostart", "status"])
    assert result.exit_code == 0
    assert "enabled" in result.output


def test_main_bundled_defaults_to_run(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    captured = {"argv": []}

    def fake_cli_group(*, obj: dict[str, object]) -> None:
        assert obj == {}
        captured["argv"] = list(cli_module.sys.argv)

    monkeypatch.setattr(cli_module, "_is_bundled_runtime", lambda: True)
    monkeypatch.setattr(cli_module, "cli_group", fake_cli_group)
    monkeypatch.setattr(cli_module.sys, "argv", ["sttc.exe"])

    cli_module.main()

    assert captured["argv"] == ["sttc.exe", "run"]


def test_main_non_bundled_keeps_no_args(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    captured = {"argv": []}

    def fake_cli_group(*, obj: dict[str, object]) -> None:
        assert obj == {}
        captured["argv"] = list(cli_module.sys.argv)

    monkeypatch.setattr(cli_module, "_is_bundled_runtime", lambda: False)
    monkeypatch.setattr(cli_module, "cli_group", fake_cli_group)
    monkeypatch.setattr(cli_module.sys, "argv", ["sttc"])

    cli_module.main()

    assert captured["argv"] == ["sttc"]


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
    monkeypatch.setattr("sttc.transcriber._build_local_transcriber", lambda **_kwargs: sentinel)

    assert build_transcriber(settings) is sentinel
