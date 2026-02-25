"""CLI entrypoint for sttc."""

import logging
import sys
from typing import TypedDict, cast

import rich_click as click
from rich_click import RichGroup
from rich_click import rich_click as click_config
from tqdm import tqdm

from sttc import __version__
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


click_config.HEADER_TEXT = "[bold cyan]sttc[/] - [dim]sttc - speach to text clipboard[/]"
click_config.OPTIONS_PANEL_TITLE = "Options"
click_config.COMMANDS_PANEL_TITLE = "Commands"
click_config.TEXT_MARKUP = "rich"


class OrderPreservingGroup(RichGroup):
    def list_commands(self, _ctx: click.Context) -> list[str]:
        return list(self.commands)


@click.group(cls=OrderPreservingGroup, help="sttc - speach to text clipboard")
@click.option("--verbose/--no-verbose", default=False, show_default=True, help="Enable debug logging.")
@click.pass_context
def cli_group(ctx: click.Context, verbose: bool) -> None:
    _configure_logging(verbose=verbose)
    ctx.obj = {"settings": get_settings()}


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


@cli_group.command("demo", help="Run a tiny progress demo.")
@click.option("--steps", type=click.IntRange(min=1), default=5, show_default=True, help="Number of steps.")
def cmd_demo(steps: int) -> None:
    logger = logging.getLogger(__name__)
    for index in tqdm(range(steps), desc="Working", unit="step"):
        logger.info("Completed step %s/%s", index + 1, steps)


def main() -> None:
    cli_group(obj={})


if __name__ == "__main__":
    main()
