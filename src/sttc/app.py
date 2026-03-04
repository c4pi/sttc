"""Application orchestration for hotkey recording and transcription."""

import logging
import queue
import subprocess
import sys
import threading

from pynput import keyboard

from sttc.clipboard import copy_to_clipboard
from sttc.recorder import AppState, HotkeyListener, QueueItem, recording_loop
from sttc.settings import Settings
from sttc.transcriber import TranscriberFn, build_transcriber

logger = logging.getLogger(__name__)

if sys.platform == "win32":  # pragma: no cover - platform dependent
    import winsound


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


def _print_banner(settings: Settings) -> None:
    logger.info("=" * 60)
    logger.info("sttc - Speech to Text Clipboard")
    logger.info("=" * 60)
    if settings.stt_model:
        logger.info("Mode               : CLOUD (%s)", settings.stt_model)
    else:
        logger.info("Mode               : LOCAL (%s)", settings.stt_whisper_model)
    logger.info("Chunk duration     : %s s", settings.stt_chunk_seconds)
    logger.info("Target sample rate : %s Hz", settings.sample_rate_target)
    logger.info("Channels           : %s", settings.channels)
    logger.info("Recording mode     : %s", settings.recording_mode)
    logger.info("Recording hotkey   : %s", settings.recording_hotkey)
    logger.info("Quit hotkey        : %s", settings.quit_hotkey)
    logger.info("")
    if settings.recording_mode == "toggle":
        logger.info(
            "Press %s to start, press again to stop, use %s to quit.",
            settings.recording_hotkey,
            settings.quit_hotkey,
        )
    else:
        logger.info(
            "Press & hold %s to record, release to stop, use %s to quit.",
            settings.recording_hotkey,
            settings.quit_hotkey,
        )
    logger.info("=" * 60)
    logger.info("")


def transcription_loop(
    state: AppState,
    audio_queue: queue.Queue[QueueItem],
    stop_event: threading.Event,
    transcribe: TranscriberFn,
) -> None:
    while True:
        if stop_event.is_set() and audio_queue.empty():
            break

        try:
            audio, samplerate, session_id, is_final = audio_queue.get(timeout=0.1)
        except queue.Empty:
            continue

        try:
            text = transcribe(audio, samplerate)
        except Exception as exc:  # pragma: no cover - backend/network dependent
            text = f"[Transcription Error] {exc}"

        if text:
            logger.info("Live transcription: %s", text)
        elif not is_final:
            logger.debug("Live transcription: (silence)")

        state.append_transcript(session_id, text)

        if is_final:
            full_text = state.finish_transcript(session_id)
            if full_text:
                logger.info("Full transcription: %s", full_text)
                try:
                    copy_to_clipboard(full_text)
                    _notify_copied()
                    logger.info("Transcript copied to clipboard")
                except RuntimeError as exc:
                    logger.warning("Transcript available above, but clipboard copy is unavailable: %s", exc)
                except Exception:
                    logger.exception("Failed to copy to clipboard")
            else:
                logger.debug("Full transcription: (silence)")

        audio_queue.task_done()


def run(settings: Settings) -> None:
    """Run the interactive hotkey-based transcription app."""
    _print_banner(settings)

    state = AppState()
    audio_queue: queue.Queue[QueueItem] = queue.Queue()
    stop_event = threading.Event()
    transcribe = build_transcriber(settings)

    recorder = threading.Thread(
        target=recording_loop,
        kwargs={
            "state": state,
            "audio_queue": audio_queue,
            "stop_event": stop_event,
            "chunk_seconds": settings.stt_chunk_seconds,
            "sample_rate_target": settings.sample_rate_target,
            "channels": settings.channels,
        },
        daemon=True,
    )
    transcriber = threading.Thread(
        target=transcription_loop,
        kwargs={
            "state": state,
            "audio_queue": audio_queue,
            "stop_event": stop_event,
            "transcribe": transcribe,
        },
        daemon=True,
    )
    recorder.start()
    transcriber.start()

    listener = HotkeyListener(
        state,
        stop_event,
        recording_mode=settings.recording_mode,
        hotkey=settings.recording_hotkey,
        quit_hotkey=settings.quit_hotkey,
    )
    keyboard_listener = keyboard.Listener(
        on_press=listener.on_press,
        on_release=listener.on_release,
        suppress=False,
    )
    keyboard_listener.start()

    try:
        keyboard_listener.join()
    except KeyboardInterrupt:
        stop_event.set()
    finally:
        stop_event.set()
        state.stop_session()
        keyboard_listener.stop()
        audio_queue.join()
        recorder.join(timeout=1.0)
        transcriber.join(timeout=1.0)
        logger.info("Goodbye!")
        sys.exit(0)
