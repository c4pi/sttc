"""Runtime controller shared by headless and GUI modes."""

from __future__ import annotations

from collections.abc import Callable
import logging
import queue
import subprocess
import sys
import threading
from typing import TYPE_CHECKING, Literal

from pynput import keyboard

from sttc.clipboard import copy_to_clipboard
from sttc.recorder import AppState, HotkeyListener, QueueItem, recording_loop
from sttc.transcriber import TranscriberFn, build_transcriber

if TYPE_CHECKING:
    from sttc.settings import Settings

logger = logging.getLogger(__name__)

RuntimeState = Literal["idle", "recording", "transcribing"]

if sys.platform == "win32":  # pragma: no cover - platform dependent
    import winsound


StateChangedFn = Callable[[RuntimeState], None]
TranscriptionFn = Callable[[str], None]
ErrorFn = Callable[[str], None]
StopRequestedFn = Callable[[], None]
EngineStatusFn = Callable[[], None]


def _run_notification_command(command: list[str]) -> bool:
    try:
        result = subprocess.run(  # noqa: S603 - command list is hardcoded in _notify_copied
            command,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:  # pragma: no cover - platform dependent
        return False
    return result.returncode == 0


def _notify_copied() -> None:
    if sys.platform == "win32":  # pragma: no cover - platform dependent
        winsound.MessageBeep()
        return
    if sys.platform == "darwin" and _run_notification_command(["osascript", "-e", "beep"]):
        return
    for command in (
        ["paplay", "/usr/share/sounds/freedesktop/stereo/complete.oga"],
        ["canberra-gtk-play", "--id", "complete"],
    ):
        if _run_notification_command(command):
            return
    print("\a", end="", flush=True)


class RuntimeController:
    """Manage recorder/transcriber/hotkey runtime lifecycle."""

    def __init__(
        self,
        settings: Settings,
        *,
        on_state_changed: StateChangedFn | None = None,
        on_transcription: TranscriptionFn | None = None,
        on_error: ErrorFn | None = None,
        on_stop_requested: StopRequestedFn | None = None,
        on_engine_started: EngineStatusFn | None = None,
        on_engine_stopped: EngineStatusFn | None = None,
    ) -> None:
        self.settings = settings
        self.on_state_changed = on_state_changed
        self.on_transcription = on_transcription
        self.on_error = on_error
        self.on_stop_requested = on_stop_requested
        self.on_engine_started = on_engine_started
        self.on_engine_stopped = on_engine_stopped

        self.state = AppState()
        self.audio_queue: queue.Queue[QueueItem] = queue.Queue()
        self.stop_event = threading.Event()

        self._state_lock = threading.Lock()
        self._last_state: RuntimeState | None = None
        self._transcribing = False
        self._started = False

        self._transcribe: TranscriberFn | None = None
        self._recorder_thread: threading.Thread | None = None
        self._transcriber_thread: threading.Thread | None = None
        self._keyboard_listener: keyboard.Listener | None = None

    @property
    def is_running(self) -> bool:
        return self._started

    def _safe_callback(self, callback: Callable[..., None] | None, *args: object) -> None:
        if callback is None:
            return
        try:
            callback(*args)
        except Exception:
            logger.exception("Runtime callback failed")

    def _current_state(self) -> RuntimeState:
        if self._transcribing:
            return "transcribing"
        if self.state.is_recording():
            return "recording"
        return "idle"

    def _emit_state_if_changed(self) -> None:
        new_state = self._current_state()
        with self._state_lock:
            if new_state == self._last_state:
                return
            self._last_state = new_state
        self._safe_callback(self.on_state_changed, new_state)

    def _set_transcribing(self, value: bool) -> None:
        with self._state_lock:
            self._transcribing = value
        self._emit_state_if_changed()

    def _emit_error(self, message: str) -> None:
        self._safe_callback(self.on_error, message)

    def _emit_transcription(self, text: str) -> None:
        self._safe_callback(self.on_transcription, text)

    def _on_session_started(self, _session_id: int) -> None:
        self._emit_state_if_changed()

    def _on_session_stopped(self, _session_id: int | None) -> None:
        self._emit_state_if_changed()

    def _on_quit_requested(self) -> None:
        self._safe_callback(self.on_stop_requested)

    def _transcription_loop(self) -> None:
        if self._transcribe is None:
            return

        while True:
            if self.stop_event.is_set() and self.audio_queue.empty():
                break

            try:
                audio, samplerate, session_id, is_final = self.audio_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            self._set_transcribing(True)
            try:
                text = self._transcribe(audio, samplerate)
            except Exception as exc:  # pragma: no cover - backend/network dependent
                text = f"[Transcription Error] {exc}"
                self._emit_error(f"Transcription failed: {exc}")
            finally:
                self._set_transcribing(False)

            if text:
                logger.info("Live transcription: %s", text)
            elif not is_final:
                logger.debug("Live transcription: (silence)")

            self.state.append_transcript(session_id, text)

            if is_final:
                full_text = self.state.finish_transcript(session_id)
                if full_text:
                    logger.info("Full transcription: %s", full_text)
                    try:
                        copy_to_clipboard(full_text)
                        _notify_copied()
                        logger.info("Transcript copied to clipboard")
                    except RuntimeError as exc:
                        logger.warning("Transcript available above, but clipboard copy is unavailable: %s", exc)
                        self._emit_error(str(exc))
                    except Exception as exc:
                        logger.exception("Failed to copy to clipboard")
                        self._emit_error(f"Failed to copy transcript to clipboard: {exc}")
                    self._emit_transcription(full_text)
                else:
                    logger.debug("Full transcription: (silence)")

            self.audio_queue.task_done()

    def start(self) -> None:
        if self._started:
            return

        self.stop_event.clear()
        self._transcribe = build_transcriber(self.settings)

        self._recorder_thread = threading.Thread(
            target=recording_loop,
            kwargs={
                "state": self.state,
                "audio_queue": self.audio_queue,
                "stop_event": self.stop_event,
                "chunk_seconds": self.settings.stt_chunk_seconds,
                "sample_rate_target": self.settings.sample_rate_target,
                "channels": self.settings.channels,
            },
            daemon=True,
        )
        self._transcriber_thread = threading.Thread(target=self._transcription_loop, daemon=True)

        listener = HotkeyListener(
            self.state,
            self.stop_event,
            recording_mode=self.settings.recording_mode,
            hotkey=self.settings.recording_hotkey,
            quit_hotkey=self.settings.quit_hotkey,
            on_session_started=self._on_session_started,
            on_session_stopped=self._on_session_stopped,
            on_quit=self._on_quit_requested,
        )
        self._keyboard_listener = keyboard.Listener(
            on_press=listener.on_press,
            on_release=listener.on_release,
            suppress=False,
        )

        self._recorder_thread.start()
        self._transcriber_thread.start()
        self._keyboard_listener.start()

        self._started = True
        self._set_transcribing(False)
        self._safe_callback(self.on_engine_started)

    def wait_for_stop_signal(self) -> None:
        if self._keyboard_listener is None:
            return
        self._keyboard_listener.join()

    def start_recording(self) -> None:
        if not self._started or self.state.is_recording():
            return
        session_id = self.state.start_session()
        self._on_session_started(session_id)

    def stop_recording(self) -> None:
        if not self._started or not self.state.is_recording():
            return
        session_id = self.state.stop_session()
        self._on_session_stopped(session_id)

    def toggle_recording(self) -> None:
        if self.state.is_recording():
            self.stop_recording()
            return
        self.start_recording()

    def stop(self) -> None:
        if not self._started:
            return

        self.stop_event.set()
        session_id = self.state.stop_session()
        self._on_session_stopped(session_id)

        if self._keyboard_listener is not None:
            self._keyboard_listener.stop()

        self.audio_queue.join()

        if self._recorder_thread is not None:
            self._recorder_thread.join(timeout=1.0)
        if self._transcriber_thread is not None:
            self._transcriber_thread.join(timeout=1.0)

        self._recorder_thread = None
        self._transcriber_thread = None
        self._keyboard_listener = None
        self._transcribe = None
        self._started = False
        self._set_transcribing(False)

        self._safe_callback(self.on_engine_stopped)

    def apply_settings(self, settings: Settings, *, restart: bool = True) -> None:
        was_running = self._started
        if was_running and restart:
            self.stop()
            self.settings = settings
            self.start()
            return

        self.settings = settings
