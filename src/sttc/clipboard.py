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


def _run_read_command(command: list[str], *, encoding: str = "utf-8") -> str | None:
    try:
        result = subprocess.run(command, capture_output=True, check=True)  # noqa: S603
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.decode(encoding, errors="replace")


def _copy_windows(text: str) -> bool:
    # `clip` expects UTF-16LE on Windows console pipelines.
    return _run_copy_command(["clip"], text, encoding="utf-16le")


def _paste_windows() -> str | None:
    return _run_read_command(["powershell", "-NoProfile", "-Command", "Get-Clipboard"])


def _copy_macos(text: str) -> bool:
    return _run_copy_command(["pbcopy"], text)


def _paste_macos() -> str | None:
    return _run_read_command(["pbpaste"])


def _linux_candidates() -> tuple[list[str], ...]:
    return (
        ["wl-copy"],
        ["xclip", "-selection", "clipboard"],
        ["xsel", "--clipboard", "--input"],
    )


def _copy_linux(text: str) -> bool:
    candidates = _linux_candidates()
    return any(shutil.which(cmd[0]) and _run_copy_command(cmd, text) for cmd in candidates)


def _paste_linux() -> str | None:
    candidates = (
        ["wl-paste", "-n"],
        ["xclip", "-selection", "clipboard", "-o"],
        ["xsel", "--clipboard", "--output"],
    )
    for command in candidates:
        if not shutil.which(command[0]):
            continue
        text = _run_read_command(command)
        if text is not None:
            return text
    return None


def _linux_clipboard_error() -> RuntimeError:
    tools = [cmd[0] for cmd in _linux_candidates()]
    available = [tool for tool in tools if shutil.which(tool)]
    if not available:
        return RuntimeError(
            "No clipboard backend available on Linux. "
            "Install one of: wl-clipboard (wl-copy) for Wayland, or xclip/xsel for X11."
        )
    return RuntimeError(
        "Clipboard backend found but access failed. "
        f"Detected tools: {', '.join(available)}. "
        "Make sure a graphical session is active and DISPLAY/WAYLAND_DISPLAY is set."
    )


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
    if system == "linux":
        if _copy_linux(text):
            return
        raise _linux_clipboard_error()

    raise RuntimeError("No clipboard backend available on this system")


def get_clipboard_text() -> str:
    """Read text from the clipboard using pyperclip with native fallbacks."""
    try:
        text = pyperclip.paste()
        if isinstance(text, str):
            return text
    except pyperclip.PyperclipException:
        pass

    system = platform.system().lower()
    native_text: str | None = None
    if system == "windows":
        native_text = _paste_windows()
    elif system == "darwin":
        native_text = _paste_macos()
    elif system == "linux":
        native_text = _paste_linux()
        if native_text is None:
            raise _linux_clipboard_error()

    if native_text is None:
        raise RuntimeError("No clipboard backend available on this system")
    return native_text
