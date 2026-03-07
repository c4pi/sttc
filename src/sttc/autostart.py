"""Cross-platform auto-start management."""

from __future__ import annotations

import importlib
from pathlib import Path
import platform
import plistlib
import sys

from sttc.settings import is_bundled_executable

RUN_KEY_NAME = "STTC"
WINDOWS_RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
MACOS_PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / "com.c4pi.sttc.plist"
LINUX_AUTOSTART_PATH = Path.home() / ".config" / "autostart" / "sttc.desktop"


def _winreg_module():
    return importlib.import_module("winreg")


def _append_gui_flags(command: str, *, gui: bool, minimized: bool) -> str:
    if not gui:
        return command

    suffix = " --gui"
    if minimized:
        suffix += " --minimized"
    return f"{command}{suffix}"


def get_executable_path(*, gui: bool = False, minimized: bool = False) -> str:
    """Return the executable path or dev-mode command."""
    if is_bundled_executable():
        if gui:
            executable = f'"{sys.executable}" run'
            return _append_gui_flags(executable, gui=gui, minimized=minimized)
        return sys.executable

    base_command = "uv run sttc run"
    return _append_gui_flags(base_command, gui=gui, minimized=minimized)


def _enable_windows_autostart(command: str) -> None:
    winreg = _winreg_module()

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        WINDOWS_RUN_KEY_PATH,
        0,
        winreg.KEY_SET_VALUE,
    ) as run_key:
        winreg.SetValueEx(run_key, RUN_KEY_NAME, 0, winreg.REG_SZ, command)


def _disable_windows_autostart() -> None:
    winreg = _winreg_module()

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            WINDOWS_RUN_KEY_PATH,
            0,
            winreg.KEY_SET_VALUE,
        ) as run_key:
            winreg.DeleteValue(run_key, RUN_KEY_NAME)
    except FileNotFoundError:
        return


def _is_windows_autostart_enabled() -> bool:
    winreg = _winreg_module()

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            WINDOWS_RUN_KEY_PATH,
            0,
            winreg.KEY_QUERY_VALUE,
        ) as run_key:
            winreg.QueryValueEx(run_key, RUN_KEY_NAME)
            return True
    except FileNotFoundError:
        return False


def _macos_program_arguments(command: str) -> list[str]:
    if is_bundled_executable():
        return ["/bin/sh", "-lc", command]
    return ["/bin/sh", "-lc", command]


def _enable_macos_autostart(command: str) -> None:
    MACOS_PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    plist_payload = {
        "Label": "com.c4pi.sttc",
        "ProgramArguments": _macos_program_arguments(command),
        "RunAtLoad": True,
        "KeepAlive": False,
    }
    with MACOS_PLIST_PATH.open("wb") as handle:
        plistlib.dump(plist_payload, handle)


def _disable_macos_autostart() -> None:
    MACOS_PLIST_PATH.unlink(missing_ok=True)


def _is_macos_autostart_enabled() -> bool:
    return MACOS_PLIST_PATH.exists()


def _linux_exec_line(command: str) -> str:
    return command


def _enable_linux_autostart(command: str) -> None:
    LINUX_AUTOSTART_PATH.parent.mkdir(parents=True, exist_ok=True)
    LINUX_AUTOSTART_PATH.write_text(
        "\n".join(
            [
                "[Desktop Entry]",
                "Type=Application",
                "Name=STTC",
                f"Exec={_linux_exec_line(command)}",
                "X-GNOME-Autostart-enabled=true",
                "Terminal=false",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _disable_linux_autostart() -> None:
    LINUX_AUTOSTART_PATH.unlink(missing_ok=True)


def _is_linux_autostart_enabled() -> bool:
    return LINUX_AUTOSTART_PATH.exists()


def enable_autostart(*, gui: bool = False, minimized: bool = False) -> None:
    """Enable auto-start on the current platform."""
    command = get_executable_path(gui=gui, minimized=minimized)
    os_name = platform.system()
    if os_name == "Windows":
        _enable_windows_autostart(command)
        return
    if os_name == "Darwin":
        _enable_macos_autostart(command)
        return
    _enable_linux_autostart(command)


def sync_autostart(enabled: bool, *, gui: bool = False, minimized: bool = False) -> None:
    """Create/update or remove auto-start based on desired enabled state."""
    if enabled:
        enable_autostart(gui=gui, minimized=minimized)
        return
    disable_autostart()


def disable_autostart() -> None:
    """Disable auto-start on the current platform."""
    os_name = platform.system()
    if os_name == "Windows":
        _disable_windows_autostart()
        return
    if os_name == "Darwin":
        _disable_macos_autostart()
        return
    _disable_linux_autostart()


def is_autostart_enabled() -> bool:
    """Return True if auto-start is enabled on this platform."""
    os_name = platform.system()
    if os_name == "Windows":
        return _is_windows_autostart_enabled()
    if os_name == "Darwin":
        return _is_macos_autostart_enabled()
    return _is_linux_autostart_enabled()
