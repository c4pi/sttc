"""CLI entrypoint for sttc."""

from __future__ import annotations

import importlib
import logging
import os
import sys
import traceback
from typing import TYPE_CHECKING, TypedDict, cast

import rich_click as click
from rich_click import RichGroup
from rich_click import rich_click as click_config
from tqdm import tqdm

from sttc import __version__
from sttc.autostart import disable_autostart, enable_autostart, is_autostart_enabled
from sttc.onboarding import (
    CURATED_WHISPER_MODELS,
    DEFAULT_CLOUD_MODEL,
    Backend,
    OnboardingValues,
    RecordingMode,
    default_onboarding_values,
    is_onboarding_complete,
    onboarding_required_message,
    persist_onboarding_values,
)
from sttc.settings import Settings, get_settings, get_user_config_dir, is_bundled_executable
from sttc.transcriber import should_announce_model_download, validate_openai_api_key

if TYPE_CHECKING:
    from collections.abc import Callable


class CliContext(TypedDict):
    settings: Settings


class _TqdmLoggingHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            tqdm.write(msg, file=sys.stderr)
        except Exception:
            self.handleError(record)


def _configure_logging(*, verbose: bool) -> None:
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
    )

    handler = _TqdmLoggingHandler()
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)

    if is_bundled_executable():
        log_dir = get_user_config_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_dir / "sttc.log", encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def _is_bundled_runtime() -> bool:
    return getattr(sys, "_MEIPASS", None) is not None


def _can_read_stdin() -> bool:
    stdin = sys.stdin
    if stdin is None or stdin.closed:
        return False
    try:
        stdin.read(0)
    except (OSError, ValueError, RuntimeError):
        return False
    return True


def _has_interactive_terminal() -> bool:
    stdin = sys.stdin
    stdout = sys.stdout
    return bool(
        _can_read_stdin()
        and stdin is not None
        and stdout is not None
        and hasattr(stdin, "isatty")
        and hasattr(stdout, "isatty")
        and stdin.isatty()
        and stdout.isatty()
    )


def _prepare_bundled_default_command() -> None:
    # Double-clicking bundled sttc.exe provides no args; default to GUI mode.
    if _is_bundled_runtime() and len(sys.argv) == 1:
        sys.argv.extend(["run", "--gui"])


def _load_run_app() -> Callable[[Settings], None]:
    try:
        run_app = importlib.import_module("sttc.app").run
    except ImportError as exc:
        if sys.platform.startswith("linux") and "pynput" in str(exc):
            msg = (
                "Global hotkeys are unavailable. On Linux, STTC needs the packaged pynput backend "
                "and an active X11/XWayland session."
            )
            raise click.ClickException(msg) from exc
        raise
    return run_app


def _is_missing_pyside6(exc: ImportError) -> bool:
    return isinstance(exc, ModuleNotFoundError) and getattr(exc, "name", "") == "PySide6"


def _is_broken_pyside6_install(exc: ImportError) -> bool:
    module_name = getattr(exc, "name", "")
    return isinstance(exc, ModuleNotFoundError) and module_name.startswith("PySide6.")


def _broken_pyside6_message(context: str, exc: ImportError) -> str:
    return (
        f"{context} failed because the PySide6 installation in this environment is incomplete or broken: {exc}. "
        "Rebuild the venv with `Remove-Item -Recurse -Force .venv` and then `uv sync --extra gui`."
    )


def _load_run_gui() -> Callable[[Settings, bool], None]:
    try:
        run_gui = importlib.import_module("sttc.gui.app").run_gui
    except ImportError as exc:
        if _is_missing_pyside6(exc):
            msg = "GUI mode requires PySide6. Install it with: uv sync --extra gui"
            raise click.ClickException(msg) from exc
        if _is_broken_pyside6_install(exc):
            raise click.ClickException(_broken_pyside6_message("GUI mode", exc)) from exc
        if "PySide6" in str(exc):
            msg = f"GUI mode failed to import even though PySide6 seems present: {exc}"
            raise click.ClickException(msg) from exc
        if sys.platform.startswith("linux") and "pynput" in str(exc):
            msg = (
                "Global hotkeys are unavailable. On Linux, STTC needs the packaged pynput backend "
                "and an active X11/XWayland session."
            )
            raise click.ClickException(msg) from exc
        raise
    return run_gui


def _load_run_onboarding_gui() -> Callable[[Settings], Settings | None]:
    try:
        run_onboarding_gui = importlib.import_module("sttc.gui.app").run_onboarding_gui
    except ImportError as exc:
        if _is_missing_pyside6(exc):
            msg = "GUI onboarding requires PySide6. Install it with: uv sync --extra gui"
            raise click.ClickException(msg) from exc
        if _is_broken_pyside6_install(exc):
            raise click.ClickException(_broken_pyside6_message("GUI onboarding", exc)) from exc
        if "PySide6" in str(exc):
            msg = f"GUI onboarding failed to import even though PySide6 seems present: {exc}"
            raise click.ClickException(msg) from exc
        raise
    return run_onboarding_gui





def _set_or_clear_env(key: str, value: str | None) -> None:
    if value is None or value == "":
        os.environ.pop(key, None)
        return
    os.environ[key] = value


def _sync_process_env(settings: Settings) -> None:
    _set_or_clear_env("OPENAI_API_KEY", settings.openai_api_key)
    _set_or_clear_env("STT_MODEL", settings.stt_model)
    _set_or_clear_env("STT_WHISPER_MODEL", settings.stt_whisper_model)
    _set_or_clear_env("STT_MODEL_CACHE_DIR", settings.stt_model_cache_dir)
    _set_or_clear_env("RECORDING_MODE", settings.recording_mode)
    _set_or_clear_env("RECORDING_HOTKEY", settings.recording_hotkey)
    _set_or_clear_env("QUIT_HOTKEY", settings.quit_hotkey)
    _set_or_clear_env("STT_CHUNK_SECONDS", str(settings.stt_chunk_seconds))
    _set_or_clear_env("SAMPLE_RATE_TARGET", str(settings.sample_rate_target))
    _set_or_clear_env("CHANNELS", str(settings.channels))
    _set_or_clear_env("ENABLE_GUI", "true" if settings.enable_gui else "false")
    _set_or_clear_env("GUI_START_MINIMIZED", "true" if settings.gui_start_minimized else "false")
    _set_or_clear_env(
        "ONBOARDING_VERSION",
        None if settings.onboarding_version is None else str(settings.onboarding_version),
    )


def _prompt_hotkey_settings(defaults: OnboardingValues) -> tuple[str, str, str]:
    keep_defaults = click.confirm("Keep the default recording mode and hotkeys?", default=True)
    if keep_defaults:
        return defaults.recording_mode, defaults.recording_hotkey, defaults.quit_hotkey

    recording_mode = cast(
        "str",
        click.prompt(
            "Recording mode",
            type=click.Choice(["toggle", "hold"], case_sensitive=False),
            default=defaults.recording_mode,
            show_choices=True,
        ),
    )
    recording_hotkey = cast("str", click.prompt("Recording hotkey", default=defaults.recording_hotkey))
    quit_hotkey = cast("str", click.prompt("Quit hotkey", default=defaults.quit_hotkey))
    return recording_mode, recording_hotkey, quit_hotkey


def _prompt_openai_api_key(current_api_key: str) -> str:
    if current_api_key.strip():
        click.echo("Press Enter to keep the currently saved OpenAI API key.")
        entered_key = cast(
            "str",
            click.prompt("OpenAI API key", default="", show_default=False, hide_input=True),
        )
        return entered_key.strip() or current_api_key.strip()

    return cast("str", click.prompt("OpenAI API key", show_default=False, hide_input=True)).strip()


def _prompt_backend_settings(defaults: OnboardingValues) -> tuple[str, str, str]:
    while True:
        backend = cast(
            "str",
            click.prompt(
                "Transcription backend",
                type=click.Choice(["local", "cloud"], case_sensitive=False),
                default=defaults.backend,
                show_choices=True,
            ),
        )
        if backend == "local":
            whisper_model = cast(
                "str",
                click.prompt(
                    "Whisper model",
                    type=click.Choice(CURATED_WHISPER_MODELS, case_sensitive=False),
                    default=defaults.whisper_model,
                    show_choices=True,
                ),
            )
            return backend, "", whisper_model

        api_key = _prompt_openai_api_key(defaults.openai_api_key)
        try:
            validate_openai_api_key(api_key)
        except RuntimeError as exc:
            click.echo(f"OpenAI API key validation failed: {exc}")
            click.echo("Enter a different key or choose the local backend.")
            click.echo()
            continue

        cloud_model = cast("str", click.prompt("Cloud model", default=defaults.cloud_model or DEFAULT_CLOUD_MODEL))
        return backend, api_key, cloud_model


def _prompt_startup_settings(defaults: OnboardingValues) -> tuple[bool, bool, bool]:
    autostart_enabled = click.confirm("Enable auto-start on login?", default=defaults.autostart_enabled)
    enable_gui = click.confirm("When auto-start runs, launch the GUI?", default=defaults.enable_gui)
    gui_start_minimized = False
    if enable_gui:
        gui_start_minimized = click.confirm(
            "Start the auto-started GUI minimized?",
            default=defaults.gui_start_minimized,
        )
    return autostart_enabled, enable_gui, gui_start_minimized


def _render_onboarding_summary(values: OnboardingValues) -> None:
    click.echo()
    click.echo("Review setup:")
    click.echo(f"  Backend: {'Cloud / OpenAI' if values.backend == 'cloud' else 'Local Whisper'}")
    if values.backend == "cloud":
        click.echo(f"  Cloud model: {values.cloud_model}")
        click.echo("  API key: configured")
    else:
        click.echo(f"  Whisper model: {values.whisper_model}")
        click.echo("  Model download: starts after setup finishes if needed")
    click.echo(f"  Recording mode: {values.recording_mode}")
    click.echo(f"  Recording hotkey: {values.recording_hotkey}")
    click.echo(f"  Quit hotkey: {values.quit_hotkey}")
    click.echo(f"  Auto-start: {'enabled' if values.autostart_enabled else 'disabled'}")
    click.echo(f"  Auto-start launch: {'GUI' if values.enable_gui else 'CLI / headless'}")
    if values.enable_gui:
        click.echo(f"  Start minimized: {'yes' if values.gui_start_minimized else 'no'}")
    click.echo()


def run_cli_onboarding(settings: Settings) -> Settings:
    defaults = default_onboarding_values(settings)

    click.echo("STTC setup")
    click.echo("Choose how STTC should start before it downloads a local model or listens for hotkeys.")
    click.echo("You can rerun this any time with `sttc setup`.")
    click.echo()

    recording_mode, recording_hotkey, quit_hotkey = _prompt_hotkey_settings(defaults)
    backend, api_key, backend_model = _prompt_backend_settings(defaults)
    autostart_enabled, enable_gui, gui_start_minimized = _prompt_startup_settings(defaults)

    values = OnboardingValues(
        backend=cast("Backend", backend),
        cloud_model=backend_model if backend == "cloud" else DEFAULT_CLOUD_MODEL,
        openai_api_key=api_key if backend == "cloud" else "",
        whisper_model=backend_model if backend == "local" else defaults.whisper_model,
        recording_mode=cast("RecordingMode", recording_mode),
        recording_hotkey=recording_hotkey,
        quit_hotkey=quit_hotkey,
        autostart_enabled=autostart_enabled,
        enable_gui=enable_gui,
        gui_start_minimized=gui_start_minimized,
    )

    try:
        values.to_settings(settings)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    _render_onboarding_summary(values)
    if not click.confirm("Save these settings?", default=True):
        msg = "Setup cancelled. Onboarding is still incomplete. Run `sttc setup` to try again."
        raise click.ClickException(msg)

    new_settings, env_path = persist_onboarding_values(settings, values)
    _sync_process_env(new_settings)
    click.echo(f"Settings saved to {env_path}")
    if values.backend == "local" and should_announce_model_download(new_settings):
        click.echo("Local Whisper model download will begin on the next startup.")
    return new_settings


click_config.HEADER_TEXT = "[bold cyan]sttc[/] - [dim]sttc - speech to text clipboard[/]"
click_config.OPTIONS_PANEL_TITLE = "Options"
click_config.COMMANDS_PANEL_TITLE = "Commands"
click_config.TEXT_MARKUP = "rich"


class OrderPreservingGroup(RichGroup):
    def list_commands(self, _ctx: click.Context) -> list[str]:
        return list(self.commands)


@click.group(cls=OrderPreservingGroup, help="sttc - speech to text clipboard")
@click.option("--verbose/--no-verbose", default=False, show_default=True, help="Enable debug logging.")
@click.pass_context
def cli_group(ctx: click.Context, verbose: bool) -> None:
    _configure_logging(verbose=verbose)
    settings = get_settings()
    _sync_process_env(settings)
    ctx.obj = {"settings": settings}


@cli_group.command("run", help="Start hotkey recording and transcription in CLI/headless mode by default.")
@click.option("--gui", is_flag=True, help="Run the GUI (mini window + settings) instead of headless mode.")
@click.option("--minimized", is_flag=True, help="Start GUI minimized/hidden.")
@click.pass_context
def cmd_run(ctx: click.Context, gui: bool, minimized: bool) -> None:
    context = cast("CliContext", ctx.obj)
    settings = context["settings"]

    use_gui = gui
    if minimized and not use_gui:
        msg = "--minimized can only be used with --gui."
        raise click.ClickException(msg)

    if not use_gui and not is_onboarding_complete(settings):
        if not _has_interactive_terminal():
            raise click.ClickException(onboarding_required_message())
        settings = run_cli_onboarding(settings)

    if use_gui:
        start_minimized = minimized or settings.gui_start_minimized
        _load_run_gui()(settings, start_minimized)
        return

    _load_run_app()(settings)


@cli_group.command("setup", help="Run the onboarding flow again in the terminal by default.")
@click.option("--gui", is_flag=True, help="Run setup in the GUI instead of the terminal.")
@click.pass_context
def cmd_setup(ctx: click.Context, gui: bool) -> None:
    context = cast("CliContext", ctx.obj)
    settings = context["settings"]

    if not gui:
        if not _has_interactive_terminal():
            raise click.ClickException(onboarding_required_message())
        run_cli_onboarding(settings)
        return

    new_settings = _load_run_onboarding_gui()(settings)
    if new_settings is None:
        if not is_onboarding_complete(settings):
            raise click.ClickException("Setup cancelled. Onboarding is still incomplete.")
        return
    _sync_process_env(new_settings)



@cli_group.command("version", help="Print the application version.")
def cmd_version() -> None:
    click.echo(__version__)


@cli_group.command("settings", help="Show effective settings.")
@click.pass_context
def cmd_settings(ctx: click.Context) -> None:
    context = cast("CliContext", ctx.obj)
    settings = context["settings"]
    click.echo(f"app_env={settings.app_env}")
    click.echo(f"debug={settings.debug}")
    click.echo(f"log_level={settings.log_level}")
    click.echo(f"onboarding_version={settings.onboarding_version}")
    click.echo(f"stt_model={settings.stt_model}")
    click.echo(f"stt_chunk_seconds={settings.stt_chunk_seconds}")
    click.echo(f"stt_whisper_model={settings.stt_whisper_model}")
    click.echo(f"stt_model_cache_dir={settings.stt_model_cache_dir}")
    click.echo(f"sample_rate_target={settings.sample_rate_target}")
    click.echo(f"channels={settings.channels}")
    click.echo(f"recording_mode={settings.recording_mode}")
    click.echo(f"recording_hotkey={settings.recording_hotkey}")
    click.echo(f"quit_hotkey={settings.quit_hotkey}")
    click.echo(f"enable_gui={settings.enable_gui}")
    click.echo(f"gui_start_minimized={settings.gui_start_minimized}")


@cli_group.group("autostart", help="Manage startup-on-login behavior.")
def autostart_group() -> None:
    return


@autostart_group.command("enable", help="Enable startup on login.")
@click.pass_context
def cmd_autostart_enable(ctx: click.Context) -> None:
    context = cast("CliContext", ctx.obj)
    settings = context["settings"]
    enable_autostart(gui=settings.enable_gui, minimized=settings.gui_start_minimized)
    click.echo("Auto-start enabled")


@autostart_group.command("disable", help="Disable startup on login.")
def cmd_autostart_disable() -> None:
    disable_autostart()
    click.echo("Auto-start disabled")


@autostart_group.command("status", help="Show startup-on-login status.")
def cmd_autostart_status() -> None:
    status = "enabled" if is_autostart_enabled() else "disabled"
    click.echo(f"Auto-start is {status}")


def main() -> None:
    _prepare_bundled_default_command()
    try:
        cli_group(obj={})
    except Exception:
        if _is_bundled_runtime():
            traceback.print_exc()
            if _can_read_stdin():
                input("STTC crashed. Press Enter to exit...")
        raise


if __name__ == "__main__":
    main()
