"""Qt application entrypoint for STTC GUI mode."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, cast

from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from sttc.gui.bridge import STTCBridge
from sttc.gui.mini_window import MiniWindow
from sttc.gui.settings_window import SettingsWindow
from sttc.gui.tray import STTCTray

if TYPE_CHECKING:
    from sttc.settings import Settings


def run_gui(settings: Settings, minimized: bool = False) -> None:
    """Run STTC in GUI mode."""
    existing_app = QApplication.instance()
    app = QApplication(sys.argv) if existing_app is None else cast("QApplication", existing_app)

    app.setApplicationName("STTC")
    app.setOrganizationName("c4pi")
    app.setQuitOnLastWindowClosed(False)

    bridge = STTCBridge(settings)

    settings_window: SettingsWindow | None = None

    def _on_settings_window_closed(_result: int) -> None:
        nonlocal settings_window
        settings_window = None

    def open_settings() -> None:
        nonlocal settings_window
        if settings_window is not None and settings_window.isVisible():
            settings_window.raise_()
            settings_window.activateWindow()
            return

        settings_window = SettingsWindow(bridge)
        settings_window.finished.connect(_on_settings_window_closed)
        settings_window.show()
        settings_window.raise_()
        settings_window.activateWindow()

    mini_window = MiniWindow(bridge, open_settings)

    tray: STTCTray | None = None
    if QSystemTrayIcon.isSystemTrayAvailable():
        tray = STTCTray(bridge, mini_window, open_settings)
        tray.show()

    bridge.quit_requested.connect(app.quit)

    def _show_error(message: str) -> None:
        QMessageBox.warning(mini_window, "STTC Error", message)

    bridge.error_occurred.connect(_show_error)

    try:
        bridge.start()
    except Exception as exc:
        QMessageBox.critical(mini_window, "STTC Startup Failed", str(exc))
        raise

    app.aboutToQuit.connect(bridge.stop)

    if not minimized or tray is None:
        mini_window.show()

    app.exec()
