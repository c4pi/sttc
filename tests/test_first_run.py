from pathlib import Path

from sttc import first_run
from sttc.settings import Settings


def _yes_no_answers(*answers: bool | None):
    iterator = iter(answers)

    def _fake(_prompt: str) -> bool | None:
        return next(iterator)

    return _fake


def test_ask_yes_no_retries_until_valid_yes(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    responses = iter(["", "maybe", "yes"])

    monkeypatch.setattr("builtins.input", lambda _prompt: next(responses))

    assert first_run._ask_yes_no("prompt") is True


def test_ask_yes_no_retries_until_valid_no(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    responses = iter([" ", "n"])

    monkeypatch.setattr("builtins.input", lambda _prompt: next(responses))

    assert first_run._ask_yes_no("prompt") is False



def test_ask_api_key_retries_until_valid(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    entries = iter(["bad-key", "sk-valid"])
    checks = iter([(False, "unauthorized"), (True, "ok")])

    monkeypatch.setattr(first_run, "getpass", lambda _prompt: next(entries))
    monkeypatch.setattr(first_run, "_validate_openai_api_key", lambda _key: next(checks))

    assert first_run._ask_api_key() == "sk-valid"


def test_ask_api_key_allows_skip_after_invalid(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    entries = iter(["wrong", "skip"])

    monkeypatch.setattr(first_run, "getpass", lambda _prompt: next(entries))
    monkeypatch.setattr(first_run, "_validate_openai_api_key", lambda _key: (False, "unauthorized"))

    assert first_run._ask_api_key() == ""

def test_run_first_launch_setup_no_choice_asks_again_next_time(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    env_path = tmp_path / ".env"

    monkeypatch.setattr(first_run, "is_bundled_executable", lambda: True)
    monkeypatch.setattr(first_run, "get_user_config_dir", lambda: tmp_path)
    monkeypatch.setattr(first_run, "ensure_bundled_env_file", lambda: (env_path, False))
    monkeypatch.setattr(first_run, "is_autostart_enabled", lambda: False)
    monkeypatch.setattr(first_run, "_ask_yes_no", _yes_no_answers(None))

    first_run.run_first_launch_setup(Settings(_env_file=None, stt_model=None))

    assert not (tmp_path / first_run.FIRST_RUN_MARKER).exists()
    assert not env_path.exists()


def test_run_first_launch_setup_no_api_key_downloads_local_model(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    env_path = tmp_path / ".env"
    model_download = {"called": False}

    def _mark_model(_settings: Settings, **_kwargs: object) -> None:
        model_download["called"] = True

    monkeypatch.setattr(first_run, "is_bundled_executable", lambda: True)
    monkeypatch.setattr(first_run, "get_user_config_dir", lambda: tmp_path)
    monkeypatch.setattr(first_run, "ensure_bundled_env_file", lambda: (env_path, False))
    monkeypatch.setattr(first_run, "is_autostart_enabled", lambda: False)
    monkeypatch.setattr(first_run, "_ask_yes_no", _yes_no_answers(False, False))
    monkeypatch.setattr(first_run, "ensure_local_model_available", _mark_model)

    settings = Settings(_env_file=None, stt_model="cloud-before")
    first_run.run_first_launch_setup(settings)

    marker_path = tmp_path / first_run.FIRST_RUN_MARKER
    assert marker_path.exists()
    marker_content = marker_path.read_text(encoding="utf-8")
    assert "autostart=disabled" in marker_content
    assert "cloud_transcription=disabled" in marker_content

    env_content = env_path.read_text(encoding="utf-8")
    assert "AUTO_START_ENABLED=false" in env_content
    assert "STT_MODEL=" in env_content
    assert settings.stt_model is None
    assert model_download["called"] is True


def test_run_first_launch_setup_with_api_key_enables_cloud(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    env_path = tmp_path / ".env"
    autostart = {"enabled": False}
    model_download = {"called": False}

    def _enable_autostart() -> None:
        autostart["enabled"] = True

    def _mark_model(_settings: Settings, **_kwargs: object) -> None:
        model_download["called"] = True

    monkeypatch.setattr(first_run, "is_bundled_executable", lambda: True)
    monkeypatch.setattr(first_run, "get_user_config_dir", lambda: tmp_path)
    monkeypatch.setattr(first_run, "ensure_bundled_env_file", lambda: (env_path, False))
    monkeypatch.setattr(first_run, "is_autostart_enabled", lambda: False)
    monkeypatch.setattr(first_run, "_ask_yes_no", _yes_no_answers(True, True))
    monkeypatch.setattr(first_run, "_ask_api_key", lambda: "sk-test-123")
    monkeypatch.setattr(first_run, "enable_autostart", _enable_autostart)
    monkeypatch.setattr(first_run, "ensure_local_model_available", _mark_model)

    settings = Settings(_env_file=None, stt_model=None)
    first_run.run_first_launch_setup(settings)

    marker_path = tmp_path / first_run.FIRST_RUN_MARKER
    assert marker_path.exists()
    marker_content = marker_path.read_text(encoding="utf-8")
    assert "autostart=enabled" in marker_content
    assert "cloud_transcription=enabled" in marker_content

    env_content = env_path.read_text(encoding="utf-8")
    assert "AUTO_START_ENABLED=true" in env_content
    assert "OPENAI_API_KEY=sk-test-123" in env_content
    assert f"STT_MODEL={first_run.DEFAULT_CLOUD_MODEL}" in env_content
    assert autostart["enabled"] is True
    assert settings.stt_model == first_run.DEFAULT_CLOUD_MODEL
    assert model_download["called"] is False
