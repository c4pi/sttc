"""Qt bridge for the shared runtime controller."""

from __future__ import annotations

import os
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
    engine_ready_changed = Signal(bool)
    engine_status_changed = Signal(str)

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
            on_engine_ready_changed=self.engine_ready_changed.emit,
            on_engine_status_changed=self.engine_status_changed.emit,
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

    @staticmethod
    def _set_or_clear_env(key: str, value: str | None) -> None:
        if value is None or value == "":
            os.environ.pop(key, None)
            return
        os.environ[key] = value

    def _sync_runtime_env(self, settings: Settings) -> None:
        self._set_or_clear_env("OPENAI_API_KEY", settings.openai_api_key)
        self._set_or_clear_env("STT_MODEL", settings.stt_model)
        self._set_or_clear_env("REFINE_MODEL", settings.refine_model)
        self._set_or_clear_env("STT_WHISPER_MODEL", settings.stt_whisper_model)
        self._set_or_clear_env("STT_MODEL_CACHE_DIR", settings.stt_model_cache_dir)
        self._set_or_clear_env("RECORDING_MODE", settings.recording_mode)
        self._set_or_clear_env("RECORDING_HOTKEY", settings.recording_hotkey)
        self._set_or_clear_env("REFINE_HOTKEY", settings.refine_hotkey)
        self._set_or_clear_env("RECORD_AND_REFINE_HOTKEY", settings.record_and_refine_hotkey)
        self._set_or_clear_env("SUMMARY_HOTKEY", settings.summary_hotkey)
        self._set_or_clear_env("TRANSLATION_HOTKEY", settings.translation_hotkey)
        self._set_or_clear_env("QUIT_HOTKEY", settings.quit_hotkey)
        self._set_or_clear_env("STT_CHUNK_SECONDS", str(settings.stt_chunk_seconds))
        self._set_or_clear_env("SAMPLE_RATE_TARGET", str(settings.sample_rate_target))
        self._set_or_clear_env("CHANNELS", str(settings.channels))
        self._set_or_clear_env("ENABLE_GUI", "true" if settings.enable_gui else "false")
        self._set_or_clear_env("GUI_START_MINIMIZED", "true" if settings.gui_start_minimized else "false")

    def apply_settings(self, settings: Settings, *, restart: bool = True) -> None:
        self._settings = settings
        self._sync_runtime_env(settings)
        self._runtime.apply_settings(settings, restart=restart)

    def get_settings(self) -> Settings:
        return self._settings

    def is_running(self) -> bool:
        return self._runtime.is_running

    def get_history(self) -> list[str]:
        return list(self._history)
