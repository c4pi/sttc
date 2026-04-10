"""Qt application entrypoint for STTC GUI mode."""

from __future__ import annotations

import logging
import os
import sys
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from sttc.gui.bridge import STTCBridge
from sttc.gui.mini_window import MiniWindow
from sttc.gui.onboarding_dialog import OnboardingDialog
from sttc.gui.settings_window import SettingsWindow
from sttc.gui.tray import STTCTray
from sttc.onboarding import is_onboarding_complete

if TYPE_CHECKING:
    from sttc.settings import Settings

logger = logging.getLogger(__name__)


def _get_app() -> QApplication:
    existing_app = QApplication.instance()
    app = QApplication(sys.argv) if existing_app is None else cast("QApplication", existing_app)
    app.setApplicationName("STTC")
    app.setOrganizationName("c4pi")
    app.setQuitOnLastWindowClosed(False)
    return app


def run_onboarding_gui(settings: Settings) -> Settings | None:
    app = _get_app()
    dialog = OnboardingDialog(settings)
    if dialog.exec() != int(OnboardingDialog.DialogCode.Accepted):
        if QApplication.instance() is app and not app.topLevelWidgets():
            app.quit()
        return None
    return dialog.saved_settings()


def run_gui(settings: Settings, minimized: bool = False) -> None:
    """Run STTC in GUI mode."""
    app = _get_app()

    if not is_onboarding_complete(settings):
        updated_settings = run_onboarding_gui(settings)
        if updated_settings is None:
            return
        settings = updated_settings
        minimized = minimized or settings.gui_start_minimized

    if not settings.refinement_hotkeys_enabled:
        line1, line2 = settings.refinement_warning_lines
        logger.warning(line1)
        logger.warning(line2)

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

    def open_onboarding() -> None:
        dialog = OnboardingDialog(bridge.get_settings(), mini_window)
        if dialog.exec() != int(OnboardingDialog.DialogCode.Accepted):
            return
        new_settings = dialog.saved_settings()
        if new_settings is None:
            return
        try:
            bridge.apply_settings(new_settings, restart=True)
        except Exception as exc:
            QMessageBox.critical(
                mini_window,
                "STTC Restart Failed",
                f"The updated settings were saved, but restarting the engine failed:\n{exc}",
            )

    mini_window = MiniWindow(bridge, open_settings)

    tray: STTCTray | None = None
    tray_available = QSystemTrayIcon.isSystemTrayAvailable()
    logger.info("System tray available: %s", tray_available)
    if tray_available:
        tray = STTCTray(bridge, mini_window, open_settings, open_onboarding)
        tray.show()

    def _quit() -> None:
        if tray is not None:
            tray.hide()
        mini_window.close()
        if settings_window is not None:
            settings_window.close()
        app.quit()

    bridge.quit_requested.connect(_quit)

    def _notify_error(message: str) -> None:
        if tray is not None:
            tray.showMessage("STTC", message, QSystemTrayIcon.MessageIcon.Warning, 4000)

    bridge.error_occurred.connect(_notify_error)
    app.aboutToQuit.connect(bridge.stop)

    def _start_bridge() -> None:
        try:
            bridge.start()
        except Exception as exc:
            logger.exception("STTC GUI startup failed")
            QMessageBox.critical(mini_window, "STTC Startup Failed", str(exc))
            app.quit()

    if not minimized or tray is None:
        mini_window.show()

    QTimer.singleShot(0, _start_bridge)

    try:
        app.exec()
    finally:
        try:
            bridge.stop()
        except Exception:
            logger.exception("STTC GUI shutdown failed")
        if tray is not None:
            tray.hide()

    if getattr(sys, "frozen", False):
        os._exit(0)
