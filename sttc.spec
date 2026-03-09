# -*- mode: python ; coding: utf-8 -*-

from __future__ import annotations

from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_dynamic_libs, collect_submodules

PROJECT_ROOT = Path(globals().get("SPECPATH", ".")).resolve()
ENTRYPOINT = PROJECT_ROOT / "src" / "sttc" / "__main__.py"
ICON_PATH = PROJECT_ROOT / "scripts" / "appimage" / ("sttc.ico" if sys.platform == "win32" else "sttc.png")
GUI_RESOURCES_DIR = PROJECT_ROOT / "src" / "sttc" / "gui" / "resources"

binaries = []
for package_name in ("sounddevice", "faster_whisper", "ctranslate2"):
    try:
        binaries += collect_dynamic_libs(package_name)
    except Exception:
        continue

litellm_datas, litellm_bins, litellm_hidden = collect_all("litellm")
tiktoken_datas, tiktoken_bins, tiktoken_hidden = collect_all("tiktoken")
try:
    hf_xet_datas, hf_xet_bins, hf_xet_hidden = collect_all("hf_xet")
except Exception:
    hf_xet_datas, hf_xet_bins, hf_xet_hidden = [], [], []

binaries += litellm_bins + tiktoken_bins + hf_xet_bins

datas = [(str(PROJECT_ROOT / ".env.example"), ".")]
datas += litellm_datas + tiktoken_datas + hf_xet_datas
if GUI_RESOURCES_DIR.exists():
    datas.append((str(GUI_RESOURCES_DIR), "sttc/gui/resources"))

try:
    datas += collect_data_files("tiktoken")
except Exception:
    pass

hiddenimports = []
hiddenimports += litellm_hidden + tiktoken_hidden + hf_xet_hidden
hiddenimports += [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "pkg_resources",
    "sttc.app",
    "sttc.gui.app",
    "sttc.gui.bridge",
    "sttc.gui.env_editor",
    "sttc.gui.mini_window",
    "sttc.gui.onboarding_dialog",
    "sttc.gui.settings_window",
    "sttc.gui.tray",
    "sttc.onboarding",
    "sttc.recorder",
    "sttc.runtime",
    "sttc.transcriber",
    "tiktoken_ext.openai_public",
]
for package_name in (
    "faster_whisper",
    "tiktoken_ext",
    "pynput",
):
    try:
        hiddenimports += collect_submodules(package_name)
    except Exception:
        continue

if sys.platform.startswith("linux"):
    hiddenimports += [
        "pynput._util.xorg",
        "pynput._util.xorg_keysyms",
        "pynput.keyboard._xorg",
        "pynput.mouse._xorg",
    ]
    try:
        hiddenimports += collect_submodules("Xlib")
    except Exception:
        pass

if sys.platform == "darwin":
    hiddenimports += [
        "plistlib",
        "pyexpat",
        "xml.etree.ElementTree",
        "xml.parsers.expat",
    ]

a = Analysis(
    [str(ENTRYPOINT)],
    pathex=[str(PROJECT_ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "IPython",
        "_pytest",
        "ipykernel",
        "jupyter_client",
        "jupyter_core",
        "mypy",
        "pytest",
        "PySide6.scripts",
        "tkinter",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="sttc",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON_PATH) if ICON_PATH.exists() else None,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="sttc",
)
