"""System tray integration for GUI mode."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

from sttc.autostart import disable_autostart, enable_autostart, is_autostart_enabled

if TYPE_CHECKING:
    from collections.abc import Callable

    from sttc.gui.bridge import STTCBridge
    from sttc.gui.mini_window import MiniWindow


class STTCTray(QSystemTrayIcon):
    """Tray icon and menu actions for controlling STTC."""

    def __init__(
        self,
        bridge: STTCBridge,
        mini_window: MiniWindow,
        open_settings: Callable[[], None],
        open_onboarding: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._bridge = bridge
        self._mini_window = mini_window
        self._engine_ready = False
        self._current_state = "idle"

        self._status_action = QAction("Status: Preparing", self)
        self._status_action.setEnabled(False)

        self._toggle_window_action = QAction("Hide Mini Window", self)
        self._toggle_window_action.triggered.connect(self._mini_window.toggle_visibility)

        self._record_action = QAction("Start Recording", self)
        self._record_action.setEnabled(False)
        self._record_action.triggered.connect(self._bridge.toggle_recording)

        self._settings_action = QAction("Settings", self)
        self._settings_action.triggered.connect(open_settings)

        self._onboarding_action = QAction("Run Onboarding", self)
        self._onboarding_action.triggered.connect(open_onboarding)

        self._autostart_action = QAction("Auto-start", self)
        self._autostart_action.setCheckable(True)
        self._autostart_action.triggered.connect(self._toggle_autostart)

        self._quit_action = QAction("Quit", self)
        self._quit_action.triggered.connect(self._quit_requested)

        self._menu = QMenu()
        self._menu.addAction(self._status_action)
        self._menu.addSeparator()
        self._menu.addAction(self._toggle_window_action)
        self._menu.addAction(self._record_action)
        self._menu.addAction(self._settings_action)
        self._menu.addAction(self._onboarding_action)
        self._menu.addSeparator()
        self._menu.addAction(self._autostart_action)
        self._menu.addSeparator()
        self._menu.addAction(self._quit_action)

        self._menu.aboutToShow.connect(self._refresh_menu)

        self.setContextMenu(self._menu)
        self.activated.connect(self._on_activated)

        self._bridge.state_changed.connect(self._on_state_changed)
        self._bridge.engine_ready_changed.connect(self._on_engine_ready_changed)
        self._on_state_changed("idle")

    def _icon_for_state(self, state: str) -> QIcon:
        color = QColor("#6b7280")
        if not self._engine_ready:
            color = QColor("#2563eb")
        elif state == "recording":
            color = QColor("#e11d48")
        elif state == "transcribing":
            color = QColor("#f59e0b")

        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(8, 8, 48, 48)
        painter.end()

        return QIcon(pixmap)

    def _refresh_menu(self) -> None:
        self._autostart_action.setChecked(is_autostart_enabled())
        self._toggle_window_action.setText("Hide Mini Window" if self._mini_window.isVisible() else "Show Mini Window")

    def _on_engine_ready_changed(self, ready: bool) -> None:
        self._engine_ready = ready
        self._on_state_changed(self._current_state)

    def _on_state_changed(self, state: str) -> None:
        self._current_state = state
        label = "Preparing" if not self._engine_ready and state == "idle" else state.capitalize()
        self._status_action.setText(f"Status: {label}")
        if state == "recording":
            self._record_action.setText("Stop Recording")
            self._record_action.setEnabled(True)
        elif self._engine_ready:
            self._record_action.setText("Start Recording")
            self._record_action.setEnabled(True)
        else:
            self._record_action.setText("Preparing Engine")
            self._record_action.setEnabled(False)
        self.setIcon(self._icon_for_state(state))
        self.setToolTip(f"STTC ({label})")

    def _toggle_autostart(self) -> None:
        try:
            if self._autostart_action.isChecked():
                enable_autostart()
            else:
                disable_autostart()
        except Exception as exc:
            self._bridge.error_occurred.emit(f"Auto-start update failed: {exc}")

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in {QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick}:
            self._mini_window.toggle_visibility()

    def _quit_requested(self) -> None:
        self._bridge.quit_requested.emit()
