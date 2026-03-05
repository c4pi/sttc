# -*- mode: python ; coding: utf-8 -*-

from __future__ import annotations

from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_dynamic_libs, collect_submodules

PROJECT_ROOT = Path(globals().get("SPECPATH", ".")).resolve()
ENTRYPOINT = PROJECT_ROOT / "src" / "sttc" / "__main__.py"
ICON_PATH = PROJECT_ROOT / "scripts" / "appimage" / ("sttc.ico" if sys.platform == "win32" else "sttc.png")

binaries = []
for package_name in ("sounddevice", "faster_whisper", "ctranslate2"):
    try:
        binaries += collect_dynamic_libs(package_name)
    except Exception:
        continue

litellm_datas, litellm_bins, litellm_hidden = collect_all("litellm")
tiktoken_datas, tiktoken_bins, tiktoken_hidden = collect_all("tiktoken")

binaries += litellm_bins + tiktoken_bins

datas = [(str(PROJECT_ROOT / ".env.example"), ".")]
datas += litellm_datas + tiktoken_datas
# keep explicit tiktoken data inclusion for registry files
try:
    datas += collect_data_files("tiktoken")
except Exception:
    pass

hiddenimports = []
hiddenimports += litellm_hidden + tiktoken_hidden
for package_name in ("faster_whisper", "tiktoken_ext"):
    try:
        hiddenimports += collect_submodules(package_name)
    except Exception:
        continue


a = Analysis(
    [str(ENTRYPOINT)],
    pathex=[str(PROJECT_ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="sttc",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON_PATH) if ICON_PATH.exists() else None,
)
