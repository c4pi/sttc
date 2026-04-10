"""Runtime controller shared by headless and GUI modes."""

from __future__ import annotations

from collections.abc import Callable
import logging
import queue
import subprocess
import sys
import threading
import time
from typing import TYPE_CHECKING, Literal

from pynput import keyboard

from sttc.clipboard import copy_to_clipboard, get_clipboard_text
from sttc.recorder import AppState, HotkeyListener, QueueItem, recording_loop
from sttc.refiner import RefinerMode, process_text
from sttc.transcriber import TranscriberFn, build_transcriber, should_announce_model_download

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
EngineLifecycleFn = Callable[[], None]
EngineReadyChangedFn = Callable[[bool], None]
EngineStatusChangedFn = Callable[[str], None]
ClipboardQueueItem = tuple[RefinerMode, str | None]


def _run_notification_command(command: list[str]) -> bool:
    try:
        result = subprocess.run(  # noqa: S603 - command list is hardcoded in notification helpers
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


def _notify_refined() -> None:
    if sys.platform == "win32":  # pragma: no cover - platform dependent
        winsound.Beep(1200, 120)
        winsound.Beep(1200, 120)
        return
    if sys.platform == "darwin":  # pragma: no cover - platform dependent
        _run_notification_command(["osascript", "-e", "beep", "-e", "beep"])
        return
    for _ in range(2):
        for command in (
            ["paplay", "/usr/share/sounds/freedesktop/stereo/complete.oga"],
            ["canberra-gtk-play", "--id", "complete"],
        ):
            if _run_notification_command(command):
                break
        else:
            print("\a", end="", flush=True)


def _notify_error() -> None:
    if sys.platform == "win32":  # pragma: no cover - platform dependent
        winsound.Beep(440, 160)
        winsound.Beep(330, 200)
        return
    if sys.platform == "darwin":  # pragma: no cover - platform dependent
        _run_notification_command(["osascript", "-e", "beep", "-e", "delay 0.1", "-e", "beep"])
        return
    print("\a\a", end="", flush=True)


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
        on_engine_started: EngineLifecycleFn | None = None,
        on_engine_stopped: EngineLifecycleFn | None = None,
        on_engine_ready_changed: EngineReadyChangedFn | None = None,
        on_engine_status_changed: EngineStatusChangedFn | None = None,
    ) -> None:
        self.settings = settings
        self.on_state_changed = on_state_changed
        self.on_transcription = on_transcription
        self.on_error = on_error
        self.on_stop_requested = on_stop_requested
        self.on_engine_started = on_engine_started
        self.on_engine_stopped = on_engine_stopped
        self.on_engine_ready_changed = on_engine_ready_changed
        self.on_engine_status_changed = on_engine_status_changed

        self.state = AppState()
        self.audio_queue: queue.Queue[QueueItem] = queue.Queue()
        self.clipboard_queue: queue.Queue[ClipboardQueueItem] = queue.Queue()
        self.stop_event = threading.Event()

        self._state_lock = threading.Lock()
        self._last_state: RuntimeState | None = None
        self._transcribing = False
        self._started = False
        self._transcriber_ready = threading.Event()
        self._startup_error: str | None = None
        self._record_and_refine_sessions: set[int] = set()
        self._pressed_aux_keys: set[str] = set()
        self._active_aux_hotkeys: set[str] = set()

        self._transcribe: TranscriberFn | None = None
        self._recorder_thread: threading.Thread | None = None
        self._transcriber_thread: threading.Thread | None = None
        self._clipboard_thread: threading.Thread | None = None
        self._keyboard_listener: keyboard.Listener | None = None
        self._recording_listener: HotkeyListener | None = None

        self._refine_hotkey_keys: frozenset[str] = frozenset()
        self._record_and_refine_hotkey_keys: frozenset[str] = frozenset()
        self._summary_hotkey_keys: frozenset[str] = frozenset()
        self._translation_hotkey_keys: frozenset[str] = frozenset()
        self._update_aux_hotkey_bindings()

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

    def _emit_engine_ready(self, ready: bool) -> None:
        self._safe_callback(self.on_engine_ready_changed, ready)

    def _emit_engine_status(self, message: str) -> None:
        self._safe_callback(self.on_engine_status_changed, message)

    def _current_state(self) -> RuntimeState:
        if self.state.is_recording():
            return "recording"
        if self._transcribing:
            return "transcribing"
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

    def _on_session_stopped(self, session_id: int | None) -> None:
        self._emit_state_if_changed()
        if session_id is None:
            return
        if session_id not in self._record_and_refine_sessions:
            return
        self._record_and_refine_sessions.add(session_id)

    def _on_quit_requested(self) -> None:
        self._safe_callback(self.on_stop_requested)

    def _startup_status_message(self) -> str:
        if self.settings.stt_model:
            if not self.settings.openai_api_key:
                return "OpenAI mode requires an API key. Open Settings to continue."
            return "Starting OpenAI transcription engine..."
        if should_announce_model_download(self.settings):
            return "Downloading Whisper model... This can take a moment on first start."
        return "Starting Whisper engine..."

    def _waiting_status_message(self) -> str:
        if self.settings.stt_model:
            return "OpenAI transcription engine is still starting. Please wait."
        if should_announce_model_download(self.settings):
            return "Whisper model is still downloading. Please wait."
        return "Whisper engine is still starting. Please wait."

    def _can_start_recording(self) -> bool:
        if self._startup_error is not None:
            self._emit_engine_status(self._startup_error)
            return False
        if not self._transcriber_ready.is_set():
            self._emit_engine_status(self._waiting_status_message())
            return False
        return True

    def _update_aux_hotkey_bindings(self) -> None:
        self._refine_hotkey_keys = frozenset()
        self._record_and_refine_hotkey_keys = frozenset()
        self._summary_hotkey_keys = frozenset()
        self._translation_hotkey_keys = frozenset()
        if not self.settings.refinement_hotkeys_enabled:
            return
        self._refine_hotkey_keys, _ = HotkeyListener.parse_hotkey(self.settings.refine_hotkey)
        self._record_and_refine_hotkey_keys, _ = HotkeyListener.parse_hotkey(self.settings.record_and_refine_hotkey)
        self._summary_hotkey_keys, _ = HotkeyListener.parse_hotkey(self.settings.summary_hotkey)
        self._translation_hotkey_keys, _ = HotkeyListener.parse_hotkey(self.settings.translation_hotkey)

    def _copy_result_to_clipboard(self, text: str, *, refined: bool) -> None:
        copy_to_clipboard(text)
        if refined:
            _notify_refined()
        else:
            _notify_copied()

    def _run_llm_mode(self, text: str, mode: RefinerMode) -> str:
        return process_text(text, mode, self.settings)

    def _process_final_transcript(self, session_id: int, full_text: str) -> None:
        should_refine = session_id in self._record_and_refine_sessions
        if not should_refine:
            try:
                self._copy_result_to_clipboard(full_text, refined=False)
                logger.info("Transcript copied to clipboard")
                self._emit_transcription(full_text)
            except RuntimeError as exc:
                logger.warning("Transcript available above, but clipboard copy is unavailable: %s", exc)
                self._emit_error(str(exc))
            except Exception as exc:
                logger.exception("Failed to copy to clipboard")
                self._emit_error(f"Failed to copy transcript to clipboard: {exc}")
            return

        try:
            refined_text = self._run_llm_mode(full_text, "refine")
            self._copy_result_to_clipboard(refined_text, refined=True)
            logger.info("Refined transcript copied to clipboard")
            self._emit_transcription(refined_text)
        except Exception as exc:
            logger.exception("Transcript refinement failed")
            self._emit_error(f"Transcript refinement failed: {exc}")
            _notify_error()
        finally:
            self._record_and_refine_sessions.discard(session_id)

    def _transcription_loop(self) -> None:
        if self.settings.stt_model and not self.settings.openai_api_key:
            self._startup_error = "OpenAI mode requires an API key. Open Settings to continue."
            self._emit_engine_status(self._startup_error)
            return

        try:
            self._transcribe = build_transcriber(self.settings, status_callback=self._emit_engine_status)
        except Exception as exc:  # pragma: no cover - backend/network dependent
            logger.exception("Failed to initialize transcription engine")
            self._startup_error = f"Transcription engine failed to start: {exc}"
            self._emit_engine_status(self._startup_error)
            self._emit_error(self._startup_error)
            return

        self._transcriber_ready.set()
        self._emit_engine_ready(True)
        self._emit_engine_status("Ready. Press Start or use your hotkey.")

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
                    self._process_final_transcript(session_id, full_text)
                else:
                    logger.debug("Full transcription: (silence)")
                    self._record_and_refine_sessions.discard(session_id)

            self.audio_queue.task_done()

    def _clipboard_loop(self) -> None:
        while True:
            if self.stop_event.is_set() and self.clipboard_queue.empty():
                break

            try:
                mode, text = self.clipboard_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            self._set_transcribing(True)
            try:
                source_text = text if text is not None else get_clipboard_text()
                result_text = self._run_llm_mode(source_text, mode)
                self._copy_result_to_clipboard(result_text, refined=True)
                self._emit_transcription(result_text)
                logger.info("Clipboard %s result copied to clipboard", mode)
            except Exception as exc:
                logger.exception("Clipboard %s failed", mode)
                self._emit_error(str(exc))
                _notify_error()
            finally:
                self._set_transcribing(False)
                self.clipboard_queue.task_done()

    def _queue_clipboard_mode(self, mode: RefinerMode) -> None:
        if not self.settings.refinement_hotkeys_enabled:
            self._emit_error("Refinement requires OPENAI_API_KEY.")
            return
        self.clipboard_queue.put((mode, None))

    def _start_record_and_refine_session(self) -> None:
        if self.state.is_recording():
            self._emit_error("A recording is already in progress.")
            _notify_error()
            return
        if not self._can_start_recording():
            _notify_error()
            return
        session_id = self.state.start_session()
        self._record_and_refine_sessions.add(session_id)
        self._on_session_started(session_id)
        logger.info("Session %s started (record and refine)", session_id)

    def _stop_record_and_refine_session(self) -> None:
        if not self.state.is_recording():
            return
        session_id = self.state.session_id
        if session_id is None or session_id not in self._record_and_refine_sessions:
            self._emit_error("Record-and-refine hotkey cannot stop a regular recording.")
            _notify_error()
            return
        stopped_session = self.state.stop_session()
        self._emit_state_if_changed()
        logger.info("Finishing record-and-refine session %s", stopped_session)

    def _handle_aux_press(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        key_id = HotkeyListener.key_to_identifier(key)
        if key_id:
            self._pressed_aux_keys.add(key_id)

        if not self.settings.refinement_hotkeys_enabled:
            return

        if self._refine_hotkey_keys.issubset(self._pressed_aux_keys) and "refine" not in self._active_aux_hotkeys:
            self._active_aux_hotkeys.add("refine")
            self._queue_clipboard_mode("refine")

        if self._summary_hotkey_keys.issubset(self._pressed_aux_keys) and "summary" not in self._active_aux_hotkeys:
            self._active_aux_hotkeys.add("summary")
            self._queue_clipboard_mode("summary")

        if self._translation_hotkey_keys.issubset(self._pressed_aux_keys) and "translation" not in self._active_aux_hotkeys:
            self._active_aux_hotkeys.add("translation")
            self._queue_clipboard_mode("translation")

        combo_pressed = self._record_and_refine_hotkey_keys.issubset(self._pressed_aux_keys)
        if not combo_pressed or "record_and_refine" in self._active_aux_hotkeys:
            return

        self._active_aux_hotkeys.add("record_and_refine")
        if self.settings.recording_mode == "toggle":
            if self.state.is_recording():
                self._stop_record_and_refine_session()
            else:
                self._start_record_and_refine_session()
            return

        if not self.state.is_recording():
            self._start_record_and_refine_session()

    def _handle_aux_release(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        key_id = HotkeyListener.key_to_identifier(key)
        if key_id:
            self._pressed_aux_keys.discard(key_id)

        if "refine" in self._active_aux_hotkeys and not self._refine_hotkey_keys.issubset(self._pressed_aux_keys):
            self._active_aux_hotkeys.discard("refine")
        if "summary" in self._active_aux_hotkeys and not self._summary_hotkey_keys.issubset(self._pressed_aux_keys):
            self._active_aux_hotkeys.discard("summary")
        if "translation" in self._active_aux_hotkeys and not self._translation_hotkey_keys.issubset(self._pressed_aux_keys):
            self._active_aux_hotkeys.discard("translation")

        combo_pressed = self._record_and_refine_hotkey_keys.issubset(self._pressed_aux_keys)
        if not combo_pressed:
            self._active_aux_hotkeys.discard("record_and_refine")

        if self.settings.recording_mode != "hold" or combo_pressed:
            return

        session_id = self.state.session_id
        if self.state.is_recording() and session_id is not None and session_id in self._record_and_refine_sessions:
            stopped_session = self.state.stop_session()
            self._emit_state_if_changed()
            logger.info("Finishing record-and-refine session %s", stopped_session)

    def _on_keyboard_press(self, key: keyboard.Key | keyboard.KeyCode) -> bool | None:
        self._handle_aux_press(key)
        if self._recording_listener is None:
            return None
        return self._recording_listener.on_press(key)

    def _on_keyboard_release(self, key: keyboard.Key | keyboard.KeyCode) -> bool | None:
        self._handle_aux_release(key)
        if self._recording_listener is None:
            return None
        return self._recording_listener.on_release(key)

    def start(self) -> None:
        if self._started:
            return

        self.stop_event.clear()
        self._transcribe = None
        self._transcriber_ready.clear()
        self._startup_error = None
        self._pressed_aux_keys.clear()
        self._active_aux_hotkeys.clear()
        self._record_and_refine_sessions.clear()
        self._emit_engine_ready(False)
        self._emit_engine_status(self._startup_status_message())

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
        self._clipboard_thread = threading.Thread(target=self._clipboard_loop, daemon=True)

        self._recording_listener = HotkeyListener(
            self.state,
            self.stop_event,
            recording_mode=self.settings.recording_mode,
            hotkey=self.settings.recording_hotkey,
            quit_hotkey=self.settings.quit_hotkey,
            can_start_recording=self._can_start_recording,
            on_session_started=self._on_session_started,
            on_session_stopped=self._on_session_stopped,
            on_quit=self._on_quit_requested,
        )
        self._keyboard_listener = keyboard.Listener(
            on_press=self._on_keyboard_press,
            on_release=self._on_keyboard_release,
            suppress=False,
        )
        self._keyboard_listener.daemon = True

        self._recorder_thread.start()
        self._transcriber_thread.start()
        self._clipboard_thread.start()
        self._keyboard_listener.start()
        self._ensure_listener_started()

        self._started = True
        self._set_transcribing(False)
        self._safe_callback(self.on_engine_started)

    def _ensure_listener_started(self) -> None:
        if self._keyboard_listener is None:
            return

        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            if not self._keyboard_listener.is_alive():
                self._keyboard_listener.join(timeout=0)
                msg = "Global hotkey listener stopped during startup."
                raise RuntimeError(msg)
            if self._keyboard_listener.running:
                return
            time.sleep(0.01)

        if not self._keyboard_listener.is_alive():
            self._keyboard_listener.join(timeout=0)
        msg = "Global hotkey listener did not become ready."
        raise RuntimeError(msg)

    def wait_for_stop_signal(self) -> None:
        if self._keyboard_listener is None:
            return
        self._keyboard_listener.join()

    def start_recording(self) -> None:
        if not self._started or self.state.is_recording():
            return
        if not self._can_start_recording():
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
            self._keyboard_listener.join(timeout=1.0)

        self.audio_queue.join()
        self.clipboard_queue.join()

        if self._recorder_thread is not None:
            self._recorder_thread.join(timeout=1.0)
        if self._transcriber_thread is not None:
            self._transcriber_thread.join(timeout=1.0)
        if self._clipboard_thread is not None:
            self._clipboard_thread.join(timeout=1.0)

        self._recorder_thread = None
        self._transcriber_thread = None
        self._clipboard_thread = None
        self._keyboard_listener = None
        self._recording_listener = None
        self._transcribe = None
        self._started = False
        self._transcriber_ready.clear()
        self._startup_error = None
        self._record_and_refine_sessions.clear()
        self._pressed_aux_keys.clear()
        self._active_aux_hotkeys.clear()
        self._emit_engine_ready(False)
        self._emit_engine_status("Stopped")
        self._set_transcribing(False)

        self._safe_callback(self.on_engine_stopped)

    def apply_settings(self, settings: Settings, *, restart: bool = True) -> None:
        self.settings = settings
        self._update_aux_hotkey_bindings()
        if not restart:
            return

        if self._started:
            self.stop()
        self.start()
