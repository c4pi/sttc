"""Qt bridge for the shared runtime controller."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

from sttc.runtime import RuntimeController

if TYPE_CHECKING:
    from sttc.settings import Settings


class STTCBridge(QObject):
    """Expose runtime updates and controls through Qt signals."""

    state_changed = Signal(str)
    transcription_ready = Signal(str)
    error_occurred = Signal(str)
    quit_requested = Signal()
    engine_running_changed = Signal(bool)

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings
        self._history: list[str] = []
        self._runtime = RuntimeController(
            settings,
            on_state_changed=self.state_changed.emit,
            on_transcription=self._on_transcription,
            on_error=self.error_occurred.emit,
            on_stop_requested=self.quit_requested.emit,
            on_engine_started=lambda: self.engine_running_changed.emit(True),
            on_engine_stopped=lambda: self.engine_running_changed.emit(False),
        )

    def _on_transcription(self, text: str) -> None:
        self._history.insert(0, text)
        self.transcription_ready.emit(text)

    def start(self) -> None:
        self._runtime.start()

    def stop(self) -> None:
        self._runtime.stop()

    def toggle_recording(self) -> None:
        self._runtime.toggle_recording()

    def start_recording(self) -> None:
        self._runtime.start_recording()

    def stop_recording(self) -> None:
        self._runtime.stop_recording()

    def apply_settings(self, settings: Settings, *, restart: bool = True) -> None:
        self._settings = settings
        self._runtime.apply_settings(settings, restart=restart)

    def get_settings(self) -> Settings:
        return self._settings

    def is_running(self) -> bool:
        return self._runtime.is_running

    def get_history(self) -> list[str]:
        return list(self._history)
