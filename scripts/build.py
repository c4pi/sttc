#!/usr/bin/env python3
"""Build a one-file STTC executable via PyInstaller."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def _run(command: list[str], *, env: dict[str, str]) -> None:
    subprocess.run(command, cwd=ROOT, check=True, env=env)  # noqa: S603


def _ensure_output_executable_not_running() -> None:
    exe_path = ROOT / "dist" / "sttc.exe"
    if not exe_path.exists():
        return

    try:
        exe_path.unlink()
        return
    except PermissionError:
        pass

    if sys.platform == "win32":
        # A previous sttc.exe instance is still running and locking the file.
        subprocess.run(["taskkill", "/IM", "sttc.exe", "/F"], check=False, capture_output=True)  # noqa: S607
        time.sleep(0.5)

    try:
        exe_path.unlink(missing_ok=True)
    except PermissionError as exc:
        msg = (
            f"Cannot overwrite {exe_path}. A running sttc.exe still holds a file lock. "
            "Close it and run the build again."
        )
        raise RuntimeError(msg) from exc


def main() -> int:
    env = os.environ.copy()
    env.setdefault("UV_CACHE_DIR", str(ROOT / ".uv-cache"))

    _run(["uv", "sync", "--all-extras", "--dev"], env=env)
    _ensure_output_executable_not_running()
    _run(["uv", "run", "pyinstaller", "--clean", "sttc.spec"], env=env)

    dist_dir = ROOT / "dist"
    print(f"Build completed. Artifacts are in: {dist_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
