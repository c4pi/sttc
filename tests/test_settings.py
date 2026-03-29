from pathlib import Path

from sttc.settings import CURRENT_ONBOARDING_VERSION, get_settings, resolve_env_file_path


def test_resolve_env_file_path_uses_source_checkout_root(monkeypatch) -> None:
    source_root = Path("C:/projects/sttc")

    monkeypatch.setattr("sttc.settings.get_source_checkout_root", lambda: source_root)
    monkeypatch.setattr("sttc.settings.get_user_config_dir", lambda: Path("C:/Users/test/AppData/Roaming/sttc"))

    assert resolve_env_file_path() == source_root / ".env"


def test_resolve_env_file_path_falls_back_to_user_config_dir(monkeypatch, tmp_path: Path) -> None:
    config_dir = tmp_path / "config" / "sttc"

    monkeypatch.setattr("sttc.settings.get_source_checkout_root", lambda: None)
    monkeypatch.setattr("sttc.settings.get_user_config_dir", lambda: config_dir)

    assert resolve_env_file_path() == config_dir / ".env"
    assert config_dir.exists()


def test_get_settings_uses_source_env_even_when_cwd_changes(monkeypatch, tmp_path: Path) -> None:
    source_root = tmp_path / "repo"
    source_root.mkdir()
    (source_root / ".env").write_text(
        "ONBOARDING_VERSION=1\nENABLE_GUI=true\nGUI_START_MINIMIZED=true\n",
        encoding="utf-8",
    )

    other_dir = tmp_path / "other"
    other_dir.mkdir()

    monkeypatch.chdir(other_dir)
    monkeypatch.setattr("sttc.settings.get_source_checkout_root", lambda: source_root)
    monkeypatch.setattr("sttc.settings.get_user_config_dir", lambda: tmp_path / "config")
    monkeypatch.setenv("ENABLE_GUI", "false")
    monkeypatch.setenv("GUI_START_MINIMIZED", "false")

    settings = get_settings()

    assert settings.onboarding_version == CURRENT_ONBOARDING_VERSION
    assert settings.enable_gui is True
    assert settings.gui_start_minimized is True
