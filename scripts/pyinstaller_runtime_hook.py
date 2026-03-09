"""PyInstaller runtime hook to prioritize bundled Qt DLLs."""

from contextlib import suppress
import os
from pathlib import Path
import sys


def _is_external_qt_path(entry: str, *, meipass_lower: str) -> bool:
    normalized = entry.strip().lower()
    if not normalized:
        return False
    if normalized == meipass_lower or normalized.startswith(meipass_lower + os.sep):
        return False
    blocked_tokens = (
        "anaconda",
        "miniconda",
        "\\library\\bin",
        "\\pyside",
        "\\qt",
    )
    return any(token in normalized for token in blocked_tokens)


meipass = getattr(sys, "_MEIPASS", None)
if meipass:
    meipass_path = Path(meipass)
    meipass_lower = str(meipass_path).lower()
    dll_dirs = [meipass_path, meipass_path / "PySide6"]
    dll_dirs = [path for path in dll_dirs if path.exists()]

    filtered_path = []
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry.strip():
            continue
        if _is_external_qt_path(entry, meipass_lower=meipass_lower):
            continue
        filtered_path.append(entry)

    os.environ["PATH"] = os.pathsep.join([*(str(path) for path in dll_dirs), *filtered_path])

    plugins_dir = meipass_path / "PySide6" / "plugins"
    qml_dir = meipass_path / "PySide6" / "qml"
    if plugins_dir.exists():
        os.environ["QT_PLUGIN_PATH"] = str(plugins_dir)
    else:
        os.environ.pop("QT_PLUGIN_PATH", None)
    if qml_dir.exists():
        os.environ["QML2_IMPORT_PATH"] = str(qml_dir)
    else:
        os.environ.pop("QML2_IMPORT_PATH", None)

    for env_key in (
        "CONDA_DEFAULT_ENV",
        "CONDA_PREFIX",
        "CONDA_PROMPT_MODIFIER",
        "CONDA_PYTHON_EXE",
        "CONDA_SHLVL",
        "QT_API",
    ):
        os.environ.pop(env_key, None)

    add_dll_directory = getattr(os, "add_dll_directory", None)
    if add_dll_directory is not None:
        for path in dll_dirs:
            with suppress(OSError):
                add_dll_directory(str(path))
