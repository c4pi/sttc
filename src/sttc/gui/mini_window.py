"""Tiny always-on control window for GUI mode."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

if TYPE_CHECKING:
    from collections.abc import Callable

    from PySide6.QtGui import QCloseEvent

    from sttc.gui.bridge import STTCBridge


class MiniWindow(QWidget):
    """Compact control surface with recording and settings actions."""

    def __init__(self, bridge: STTCBridge, open_settings: Callable[[], None]) -> None:
        super().__init__()
        self._bridge = bridge
        self._open_settings = open_settings
        self._current_state = "idle"
        self._engine_ready = False
        self._engine_status_message = "Starting transcription engine..."
        self._last_transcription_preview: str | None = None

        self.setWindowTitle("STTC")
        self.setMinimumSize(320, 120)
        self.setMaximumHeight(160)

        root_layout = QVBoxLayout()
        root_layout.setContentsMargins(12, 10, 12, 10)
        root_layout.setSpacing(8)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        self.state_indicator = QLabel("  ")
        self.state_indicator.setFixedWidth(12)
        self.state_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.state_label = QLabel("Starting")
        self.state_label.setMinimumWidth(110)

        self.mic_button = QPushButton("Please wait")
        self.mic_button.setMinimumWidth(96)
        self.mic_button.clicked.connect(self._bridge.toggle_recording)

        self.settings_button = QPushButton("Settings")
        self.settings_button.clicked.connect(self._open_settings)

        top_row.addWidget(self.state_indicator)
        top_row.addWidget(self.state_label)
        top_row.addStretch(1)
        top_row.addWidget(self.mic_button)
        top_row.addWidget(self.settings_button)

        self.detail_label = QLabel(self._engine_status_message)
        self.detail_label.setWordWrap(True)
        self.detail_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        root_layout.addLayout(top_row)
        root_layout.addWidget(self.detail_label)

        self.setLayout(root_layout)

        self._bridge.state_changed.connect(self._on_state_changed)
        self._bridge.transcription_ready.connect(self._on_transcription_ready)
        self._bridge.error_occurred.connect(self._on_error_occurred)
        self._bridge.engine_ready_changed.connect(self._on_engine_ready_changed)
        self._bridge.engine_status_changed.connect(self._on_engine_status_changed)

        self._on_engine_ready_changed(False)
        self._on_state_changed("idle")

    def _state_color(self, state: str) -> str:
        if state == "recording":
            return "#e11d48"
        if state == "transcribing":
            return "#f59e0b"
        if not self._engine_ready:
            return "#2563eb"
        return "#6b7280"

    def _set_detail_text(self, text: str) -> None:
        self.detail_label.setText(text)

    def _refresh_idle_controls(self) -> None:
        if not self._engine_ready:
            if "api key" in self._engine_status_message.lower():
                self.state_label.setText("Setup Needed")
                self.mic_button.setText("Start")
            else:
                self.state_label.setText("Preparing")
                self.mic_button.setText("Please wait")
            self.mic_button.setEnabled(False)
            return

        self.state_label.setText("Idle")
        self.mic_button.setText("Start")
        self.mic_button.setEnabled(True)

    def _on_state_changed(self, state: str) -> None:
        self._current_state = state
        color = self._state_color(state)
        self.state_indicator.setStyleSheet(
            f"background-color: {color}; border-radius: 6px; min-width: 12px; min-height: 12px;"
        )

        if state == "recording":
            self.state_label.setText("Recording")
            self.mic_button.setText("Stop")
            self.mic_button.setEnabled(True)
        elif state == "transcribing":
            self.state_label.setText("Transcribing")
            self.mic_button.setText("Start")
            self.mic_button.setEnabled(False)
        else:
            self._refresh_idle_controls()

    def _on_engine_ready_changed(self, ready: bool) -> None:
        self._engine_ready = ready
        if ready and self._last_transcription_preview is None:
            self._engine_status_message = "Ready. Press Start or use your hotkey."
            self._set_detail_text(self._engine_status_message)
        self._on_state_changed(self._current_state)

    def _on_engine_status_changed(self, message: str) -> None:
        self._engine_status_message = message
        if self._last_transcription_preview is None or not self._engine_ready:
            self._set_detail_text(message)
        self._on_state_changed(self._current_state)

    def _on_transcription_ready(self, text: str) -> None:
        preview = text.strip().replace("\n", " ")
        if len(preview) > 120:
            preview = f"{preview[:117]}..."
        self._last_transcription_preview = preview or "-"
        self._set_detail_text(f"Last: {self._last_transcription_preview}")

    def _on_error_occurred(self, message: str) -> None:
        self._set_detail_text(message)

    def toggle_visibility(self) -> None:
        if self.isVisible():
            self.hide()
            return
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        event.ignore()
        self.hide()
