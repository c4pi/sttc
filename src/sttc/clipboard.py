"""Cross-platform clipboard helpers."""

import platform
import shutil
import subprocess

import pyperclip


def _run_copy_command(command: list[str], text: str, *, encoding: str = "utf-8") -> bool:
    try:
        subprocess.run(command, input=text.encode(encoding), check=True)  # noqa: S603
    except (OSError, subprocess.SubprocessError):
        return False
    return True


def _copy_windows(text: str) -> bool:
    # `clip` expects UTF-16LE on Windows console pipelines.
    return _run_copy_command(["clip"], text, encoding="utf-16le")


def _copy_macos(text: str) -> bool:
    return _run_copy_command(["pbcopy"], text)


def _copy_linux(text: str) -> bool:
    candidates = [
        ["wl-copy"],
        ["xclip", "-selection", "clipboard"],
        ["xsel", "--clipboard", "--input"],
    ]
    return any(shutil.which(cmd[0]) and _run_copy_command(cmd, text) for cmd in candidates)


def copy_to_clipboard(text: str) -> None:
    """Copy text to clipboard using pyperclip with native fallbacks."""
    try:
        pyperclip.copy(text)
        return
    except pyperclip.PyperclipException:
        pass

    system = platform.system().lower()
    if system == "windows" and _copy_windows(text):
        return
    if system == "darwin" and _copy_macos(text):
        return
    if system == "linux" and _copy_linux(text):
        return

    raise RuntimeError("No clipboard backend available on this system")
