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

        self.setWindowTitle("STTC")
        self.setMinimumSize(260, 110)
        self.setMaximumHeight(140)

        root_layout = QVBoxLayout()
        root_layout.setContentsMargins(12, 10, 12, 10)
        root_layout.setSpacing(8)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        self.state_indicator = QLabel("  ")
        self.state_indicator.setFixedWidth(12)
        self.state_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.state_label = QLabel("Idle")
        self.state_label.setMinimumWidth(90)

        self.mic_button = QPushButton("Start")
        self.mic_button.setMinimumWidth(72)
        self.mic_button.clicked.connect(self._bridge.toggle_recording)

        self.settings_button = QPushButton("Settings")
        self.settings_button.clicked.connect(self._open_settings)

        top_row.addWidget(self.state_indicator)
        top_row.addWidget(self.state_label)
        top_row.addStretch(1)
        top_row.addWidget(self.mic_button)
        top_row.addWidget(self.settings_button)

        self.last_transcription_label = QLabel("Last: -")
        self.last_transcription_label.setWordWrap(False)
        self.last_transcription_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        root_layout.addLayout(top_row)
        root_layout.addWidget(self.last_transcription_label)

        self.setLayout(root_layout)

        self._bridge.state_changed.connect(self._on_state_changed)
        self._bridge.transcription_ready.connect(self._on_transcription_ready)
        self._bridge.error_occurred.connect(self._on_error_occurred)

        self._on_state_changed("idle")

    def _state_color(self, state: str) -> str:
        if state == "recording":
            return "#e11d48"
        if state == "transcribing":
            return "#f59e0b"
        return "#6b7280"

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
            self.state_label.setText("Idle")
            self.mic_button.setText("Start")
            self.mic_button.setEnabled(True)

    def _on_transcription_ready(self, text: str) -> None:
        preview = text.strip().replace("\n", " ")
        if len(preview) > 120:
            preview = f"{preview[:117]}..."
        self.last_transcription_label.setText(f"Last: {preview or '-'}")

    def _on_error_occurred(self, message: str) -> None:
        self.last_transcription_label.setText(f"Error: {message}")

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
