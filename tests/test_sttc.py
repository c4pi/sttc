import builtins
import sys

from click.testing import CliRunner

from sttc import __version__
from sttc.cli import cli_group
from sttc.settings import Settings, get_settings


def test_version() -> None:
    assert __version__ == "0.1.0"


def test_settings_defaults() -> None:
    s = Settings()
    assert s.app_env == "development"
    assert s.debug is False
    assert s.log_level == "INFO"


def test_get_settings() -> None:
    s = get_settings()
    assert isinstance(s, Settings)


def test_cli_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli_group, ["--help"])
    assert result.exit_code == 0
    assert "Commands" in result.output


def test_cli_version() -> None:
    runner = CliRunner()
    result = runner.invoke(cli_group, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_cli_version_does_not_import_app(monkeypatch) -> None:
    sys.modules.pop("sttc.app", None)
    real_import = builtins.__import__

    def guarded_import(name: str, module_globals=None, module_locals=None, fromlist=(), level: int = 0):
        if name == "sttc.app":
            raise AssertionError("sttc.app should not be imported for the version command")
        return real_import(name, module_globals, module_locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    runner = CliRunner()
    result = runner.invoke(cli_group, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.output
