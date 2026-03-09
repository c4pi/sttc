#!/usr/bin/env python3
"""Build STTC executables via PyInstaller."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist"
STAGING_DIR = DIST_DIR / "sttc"
FINAL_EXE = DIST_DIR / "sttc.exe"
FINAL_INTERNAL_DIR = DIST_DIR / "_internal"
STAGING_EXE = STAGING_DIR / "sttc.exe"
STAGING_INTERNAL_DIR = STAGING_DIR / "_internal"


def _run(command: list[str], *, env: dict[str, str]) -> None:
    subprocess.run(command, cwd=ROOT, check=True, env=env)  # noqa: S603


def _taskkill(image_name: str) -> None:
    if sys.platform != "win32":
        return
    subprocess.run(  # noqa: S603
        ["taskkill", "/IM", image_name, "/F"],  # noqa: S607
        check=False,
        capture_output=True,
    )
    time.sleep(0.5)


def _remove_path(path: Path) -> None:
    if not path.exists():
        return

    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        return
    except PermissionError:
        _taskkill(path.name)

    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
    except PermissionError as exc:
        msg = f"Cannot overwrite {path}. A running STTC process still holds a file lock. Close it and run the build again."
        raise RuntimeError(msg) from exc


def _prepare_output_paths() -> None:
    _remove_path(STAGING_DIR)
    _remove_path(FINAL_EXE)
    _remove_path(FINAL_INTERNAL_DIR)


def _flatten_onedir_output() -> None:
    if not STAGING_EXE.exists() or not STAGING_INTERNAL_DIR.exists():
        msg = f"Expected PyInstaller output in {STAGING_DIR}, but required files are missing."
        raise RuntimeError(msg)

    shutil.move(str(STAGING_EXE), str(FINAL_EXE))
    shutil.move(str(STAGING_INTERNAL_DIR), str(FINAL_INTERNAL_DIR))
    shutil.rmtree(STAGING_DIR, ignore_errors=True)


def main() -> int:
    env = os.environ.copy()
    env.setdefault("UV_CACHE_DIR", str(ROOT / ".uv-cache"))

    _run(["uv", "sync", "--all-extras", "--dev"], env=env)
    _prepare_output_paths()
    _run(["uv", "run", "pyinstaller", "--clean", "sttc.spec"], env=env)
    _flatten_onedir_output()

    print(f"Build completed. Artifact is in: {FINAL_EXE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
