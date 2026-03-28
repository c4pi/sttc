from click.testing import CliRunner
import pytest

from sttc.cli import cli_group
from sttc.settings import CURRENT_ONBOARDING_VERSION, Settings
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
    assert s.recording_hotkey == "ctrl+alt+a"
    assert s.quit_hotkey == "ctrl+alt+q"
    assert s.enable_gui is False
    assert s.gui_start_minimized is False
    assert s.onboarding_version is None


def test_settings_recording_hotkey_normalizes() -> None:
    s = Settings(_env_file=None, recording_hotkey=" CTRL + Alt + R ")
    assert s.recording_hotkey == "ctrl+alt+r"


def test_settings_sample_rate_is_fixed() -> None:
    s = Settings(_env_file=None, sample_rate_target=44100)
    assert s.sample_rate_target == 16000


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


def test_cli_run_defaults_to_headless(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"gui": False, "headless": False}

    def fake_run_gui(_settings: Settings, _minimized: bool) -> None:
        called["gui"] = True

    def fake_headless(settings: Settings) -> None:
        called["headless"] = True
        assert isinstance(settings, Settings)

    monkeypatch.setattr(
        "sttc.cli.get_settings",
        lambda: Settings(_env_file=None, gui_start_minimized=False, onboarding_version=CURRENT_ONBOARDING_VERSION),
    )
    monkeypatch.setattr("sttc.cli._load_run_gui", lambda: fake_run_gui)
    monkeypatch.setattr("sttc.cli._load_run_app", lambda: fake_headless)

    runner = CliRunner()
    result = runner.invoke(cli_group, ["run"])
    assert result.exit_code == 0
    assert called["gui"] is False
    assert called["headless"] is True


def test_cli_run_gui_flag_starts_gui(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"gui": False, "headless": False}

    def fake_run_gui(settings: Settings, minimized: bool) -> None:
        called["gui"] = True
        assert isinstance(settings, Settings)
        assert minimized is False

    def fake_headless(_settings: Settings) -> None:
        called["headless"] = True

    monkeypatch.setattr(
        "sttc.cli.get_settings",
        lambda: Settings(_env_file=None, gui_start_minimized=False, onboarding_version=CURRENT_ONBOARDING_VERSION),
    )
    monkeypatch.setattr("sttc.cli._load_run_gui", lambda: fake_run_gui)
    monkeypatch.setattr("sttc.cli._load_run_app", lambda: fake_headless)

    runner = CliRunner()
    result = runner.invoke(cli_group, ["run", "--gui"])
    assert result.exit_code == 0
    assert called["gui"] is True
    assert called["headless"] is False


def test_cli_run_uses_gui_start_minimized_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"gui": False}

    monkeypatch.setattr(
        "sttc.cli.get_settings",
        lambda: Settings(_env_file=None, gui_start_minimized=True, onboarding_version=CURRENT_ONBOARDING_VERSION),
    )

    def fake_run_gui(_settings: Settings, minimized: bool) -> None:
        called["gui"] = True
        assert minimized is True

    monkeypatch.setattr("sttc.cli._load_run_gui", lambda: fake_run_gui)

    runner = CliRunner()
    result = runner.invoke(cli_group, ["run", "--gui"])
    assert result.exit_code == 0
    assert called["gui"] is True


def test_cli_run_runs_onboarding_when_interactive(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"setup": False, "headless": False}
    configured = Settings(_env_file=None, onboarding_version=CURRENT_ONBOARDING_VERSION)

    monkeypatch.setattr("sttc.cli.get_settings", lambda: Settings(_env_file=None, onboarding_version=None))
    monkeypatch.setattr("sttc.cli._has_interactive_terminal", lambda: True)

    def fake_setup(_settings: Settings) -> Settings:
        calls["setup"] = True
        return configured

    def fake_headless(settings: Settings) -> None:
        calls["headless"] = True
        assert settings is configured

    monkeypatch.setattr("sttc.cli.run_cli_onboarding", fake_setup)
    monkeypatch.setattr("sttc.cli._load_run_app", lambda: fake_headless)

    runner = CliRunner()
    result = runner.invoke(cli_group, ["run"])
    assert result.exit_code == 0
    assert calls == {"setup": True, "headless": True}


def test_cli_run_fails_noninteractive_when_onboarding_incomplete(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sttc.cli.get_settings", lambda: Settings(_env_file=None, onboarding_version=None))
    monkeypatch.setattr("sttc.cli._has_interactive_terminal", lambda: False)

    runner = CliRunner()
    result = runner.invoke(cli_group, ["run"])
    assert result.exit_code != 0
    assert "Run `sttc setup`" in result.output


def test_cli_run_minimized_requires_gui() -> None:
    runner = CliRunner()
    result = runner.invoke(cli_group, ["run", "--minimized"])
    assert result.exit_code != 0
    assert "only be used with --gui" in result.output


def test_cli_setup_runs_terminal_onboarding_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"setup": False}
    monkeypatch.setattr("sttc.cli.get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr("sttc.cli._has_interactive_terminal", lambda: True)

    def fake_setup(_settings: Settings) -> Settings:
        calls["setup"] = True
        return Settings(_env_file=None, onboarding_version=CURRENT_ONBOARDING_VERSION)

    monkeypatch.setattr("sttc.cli.run_cli_onboarding", fake_setup)

    runner = CliRunner()
    result = runner.invoke(cli_group, ["setup"])
    assert result.exit_code == 0
    assert calls["setup"] is True


def test_cli_setup_gui_flag_opens_gui_onboarding(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"gui": False}
    updated = Settings(_env_file=None, onboarding_version=CURRENT_ONBOARDING_VERSION)
    monkeypatch.setattr("sttc.cli.get_settings", lambda: Settings(_env_file=None))

    def fake_gui_setup(_settings: Settings) -> Settings:
        called["gui"] = True
        return updated

    monkeypatch.setattr("sttc.cli._load_run_onboarding_gui", lambda: fake_gui_setup)

    runner = CliRunner()
    result = runner.invoke(cli_group, ["setup", "--gui"])
    assert result.exit_code == 0
    assert called["gui"] is True


def test_cli_onboarding_hides_api_key_and_saves_valid_cloud_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    validated: list[str] = []

    monkeypatch.setattr("sttc.cli.get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr("sttc.cli._has_interactive_terminal", lambda: True)
    monkeypatch.setattr("sttc.cli.should_announce_model_download", lambda _settings: False)

    def fake_validate(api_key: str) -> None:
        validated.append(api_key)

    def fake_persist(_settings: Settings, values) -> tuple[Settings, str]:
        saved = Settings(
            _env_file=None,
            onboarding_version=CURRENT_ONBOARDING_VERSION,
            stt_model=values.cloud_model,
            openai_api_key=values.openai_api_key,
            enable_gui=values.enable_gui,
            gui_start_minimized=values.gui_start_minimized,
        )
        return saved, "C:/temp/.env"

    monkeypatch.setattr("sttc.cli.validate_openai_api_key", fake_validate)
    monkeypatch.setattr("sttc.cli.persist_onboarding_values", fake_persist)

    runner = CliRunner()
    result = runner.invoke(
        cli_group,
        ["setup"],
        input="y\ncloud\nsk-live\n\nn\nn\ny\n",
    )

    assert result.exit_code == 0
    assert validated == ["sk-live"]
    assert "sk-live" not in result.output
    assert "Settings saved to C:/temp/.env" in result.output


def test_cli_onboarding_retries_when_api_key_validation_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    validated: list[str] = []

    monkeypatch.setattr("sttc.cli.get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr("sttc.cli._has_interactive_terminal", lambda: True)
    monkeypatch.setattr("sttc.cli.should_announce_model_download", lambda _settings: False)

    def fake_validate(api_key: str) -> None:
        validated.append(api_key)
        if api_key == "bad-key":  # pragma: allowlist secret
            msg = "The OpenAI API key was rejected (401 Unauthorized)."
            raise RuntimeError(msg)

    def fake_persist(_settings: Settings, values) -> tuple[Settings, str]:
        saved = Settings(
            _env_file=None,
            onboarding_version=CURRENT_ONBOARDING_VERSION,
            stt_model=values.cloud_model,
            openai_api_key=values.openai_api_key,
            enable_gui=values.enable_gui,
            gui_start_minimized=values.gui_start_minimized,
        )
        return saved, "C:/temp/.env"

    monkeypatch.setattr("sttc.cli.validate_openai_api_key", fake_validate)
    monkeypatch.setattr("sttc.cli.persist_onboarding_values", fake_persist)

    runner = CliRunner()
    result = runner.invoke(
        cli_group,
        ["setup"],
        input="y\ncloud\nbad-key\ncloud\ngood-key\n\nn\nn\ny\n",
    )

    assert result.exit_code == 0
    assert validated == ["bad-key", "good-key"]
    assert "OpenAI API key validation failed" in result.output
    assert "bad-key" not in result.output
    assert "good-key" not in result.output



def test_load_run_gui_reports_non_missing_pyside6_import_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_import(_name: str):
        raise ImportError("DLL load failed while importing PySide6.QtWidgets")

    monkeypatch.setattr("sttc.cli.importlib.import_module", fake_import)

    runner = CliRunner()
    result = runner.invoke(cli_group, ["run", "--gui"])

    assert result.exit_code != 0
    assert "failed to import even though PySide6 seems present" in result.output



def test_transcriber_selection_cloud(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(stt_model="whisper-1")
    sentinel = object()

    monkeypatch.setattr("sttc.transcriber._build_cloud_transcriber", lambda _m: sentinel)
    monkeypatch.setattr("sttc.transcriber._build_local_transcriber", lambda **_kwargs: None)

    assert build_transcriber(settings) is sentinel


def test_transcriber_selection_local(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(stt_model=None, stt_whisper_model="small")
    sentinel = object()

    monkeypatch.setattr("sttc.transcriber._build_cloud_transcriber", lambda _m: None)
    monkeypatch.setattr("sttc.transcriber._build_local_transcriber", lambda **_kwargs: sentinel)

    assert build_transcriber(settings) is sentinel
