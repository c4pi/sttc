"""CLI entrypoint for sttc."""

from collections.abc import Callable
import importlib
import logging
import os
import sys
import traceback
from typing import TypedDict, cast

import rich_click as click
from rich_click import RichGroup
from rich_click import rich_click as click_config
from tqdm import tqdm

from sttc import __version__
from sttc.autostart import disable_autostart, enable_autostart, is_autostart_enabled
from sttc.first_run import run_first_launch_setup
from sttc.settings import Settings, get_settings


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
    handler = _TqdmLoggingHandler()
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def _is_bundled_runtime() -> bool:
    return getattr(sys, "_MEIPASS", None) is not None


def _prepare_bundled_default_command() -> None:
    # Double-clicking bundled sttc.exe provides no args; default to interactive run mode.
    if _is_bundled_runtime() and len(sys.argv) == 1:
        sys.argv.append("run")


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
    if settings.openai_api_key:
        os.environ["OPENAI_API_KEY"] = settings.openai_api_key
    ctx.obj = {"settings": settings}


@cli_group.command("run", help="Start hotkey recording and transcription.")
@click.pass_context
def cmd_run(ctx: click.Context) -> None:
    context = cast("CliContext", ctx.obj)
    settings = context["settings"]
    run_first_launch_setup(settings)
    _load_run_app()(settings)


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
    click.echo(f"stt_model={settings.stt_model}")
    click.echo(f"stt_chunk_seconds={settings.stt_chunk_seconds}")
    click.echo(f"stt_whisper_model={settings.stt_whisper_model}")
    click.echo(f"stt_model_cache_dir={settings.stt_model_cache_dir}")
    click.echo(f"sample_rate_target={settings.sample_rate_target}")
    click.echo(f"channels={settings.channels}")
    click.echo(f"recording_mode={settings.recording_mode}")
    click.echo(f"recording_hotkey={settings.recording_hotkey}")
    click.echo(f"quit_hotkey={settings.quit_hotkey}")


@cli_group.group("autostart", help="Manage startup-on-login behavior.")
def autostart_group() -> None:
    return


@autostart_group.command("enable", help="Enable startup on login.")
def cmd_autostart_enable() -> None:
    enable_autostart()
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
            input("STTC crashed. Press Enter to exit...")
        raise


if __name__ == "__main__":
    main()
