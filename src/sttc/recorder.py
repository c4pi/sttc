"""Audio recording state and hotkey-driven capture loop."""

from collections.abc import Callable
from dataclasses import dataclass, field
import logging
import queue
import sys
import threading
import time
from typing import ClassVar, Literal

import numpy as np
from pynput import keyboard
import sounddevice as sd

logger = logging.getLogger(__name__)

QueueItem = tuple[np.ndarray, int, int, bool]
type KeyLike = keyboard.Key | keyboard.KeyCode

# A callable returning the set of modifier identifiers ("ctrl", "alt", ...) the OS
# currently reports as physically held, or ``None`` when the OS state is unavailable.
ModifierProbe = Callable[[], "set[str] | None"]

# Modifier identifiers tracked in the pressed-key sets.
_MODIFIER_IDS: frozenset[str] = frozenset({"ctrl", "shift", "alt", "cmd"})

# Virtual-key codes used to query the real keyboard state on Windows.
_WIN_MODIFIER_VKS: dict[str, tuple[int, ...]] = {
    "ctrl": (0x11,),  # VK_CONTROL
    "shift": (0x10,),  # VK_SHIFT
    "alt": (0x12,),  # VK_MENU
    "cmd": (0x5B, 0x5C),  # VK_LWIN, VK_RWIN
}

if sys.platform == "win32":  # pragma: no cover - platform dependent
    import ctypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
else:  # pragma: no cover - platform dependent
    _user32 = None


def _query_windows_modifiers() -> set[str] | None:  # pragma: no cover - platform dependent
    """Return modifiers the OS reports as physically held, via ``GetAsyncKeyState``."""
    if _user32 is None:
        return None
    try:
        pressed: set[str] = set()
        for mod, vks in _WIN_MODIFIER_VKS.items():
            if any(_user32.GetAsyncKeyState(vk) & 0x8000 for vk in vks):
                pressed.add(mod)
    except Exception:
        # A throw inside a global-hook callback can kill the listener thread; never propagate.
        return None
    return pressed


def default_modifier_probe() -> ModifierProbe | None:
    """Return the platform's modifier probe, or ``None`` where unsupported."""
    if sys.platform == "win32":
        return _query_windows_modifiers
    return None


def sync_modifier_state(pressed_keys: set[str], probe: ModifierProbe | None) -> None:
    """Reconcile tracked modifier keys with the real OS keyboard state.

    Global low-level hooks routinely miss key-up events (Alt+Tab, lock screen, UAC,
    focus changes), leaving modifiers stuck as "pressed" forever. Re-syncing on every
    event lets a stuck modifier heal itself on the next keystroke. A ``None`` probe
    (non-Windows, or unit tests) leaves the tracked set untouched.
    """
    if probe is None:
        return
    actual = probe()
    if actual is None:
        return
    for mod in _MODIFIER_IDS:
        if mod in actual:
            pressed_keys.add(mod)
        else:
            pressed_keys.discard(mod)


def is_combo_trigger(combo: frozenset[str], just_pressed: str | None) -> bool:
    """Return True if ``just_pressed`` is the activating key of ``combo``.

    A chord should fire on the key-down of its non-modifier key while the modifiers
    are held, not merely because the combo is a subset of the tracked keys (which is
    what makes stuck modifiers dangerous). Modifier-only combos trigger on any member.
    """
    if just_pressed is None:
        return False
    triggers = combo - _MODIFIER_IDS
    if not triggers:
        triggers = combo
    return just_pressed in triggers


@dataclass
class AppState:
    """Thread-safe state for a single record/transcribe session."""

    recording: bool = False
    session_id: int | None = None
    next_session: int = 1
    buffer: list[np.ndarray] = field(default_factory=list)
    transcripts: dict[int, list[str]] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def start_session(self) -> int:
        with self.lock:
            self.recording = True
            self.buffer.clear()
            self.session_id = self.next_session
            self.transcripts[self.session_id] = []
            self.next_session += 1
            return self.session_id

    def stop_session(self) -> int | None:
        with self.lock:
            self.recording = False
            return self.session_id

    def clear_session(self) -> None:
        with self.lock:
            self.session_id = None

    def add_buffer_chunk(self, chunk: np.ndarray) -> None:
        with self.lock:
            if self.recording:
                self.buffer.append(chunk)

    def pop_buffer(self, samples: int | None) -> np.ndarray:
        with self.lock:
            if not self.buffer:
                return np.array([], dtype=np.float32)

            data = np.concatenate(self.buffer).reshape(-1)
            self.buffer.clear()

        if samples is None:
            return data.astype(np.float32)

        return data[: min(samples, data.shape[0])].astype(np.float32)

    def buffer_sample_count(self) -> int:
        with self.lock:
            return sum(len(chunk) for chunk in self.buffer)

    def is_recording(self) -> bool:
        with self.lock:
            return self.recording

    def append_transcript(self, session_id: int, text: str) -> None:
        with self.lock:
            self.transcripts.setdefault(session_id, []).append(text)

    def finish_transcript(self, session_id: int) -> str:
        with self.lock:
            parts = self.transcripts.pop(session_id, [])
        return " ".join(filter(None, parts)).strip()


def _pick_input_samplerate(fallback: int) -> int:
    """Pick default input-device sample rate, or fallback when unavailable."""
    try:
        default_input = sd.default.device[0]
        info = sd.query_devices(default_input)
        return int(info.get("default_samplerate", fallback))
    except Exception:
        return fallback


def _audio_callback(state: AppState, indata: np.ndarray, status: sd.CallbackFlags) -> None:
    if status:
        logger.warning("Audio warning: %s", status)
    state.add_buffer_chunk(indata.copy())


def recording_loop(
    state: AppState,
    audio_queue: queue.Queue[QueueItem],
    stop_event: threading.Event,
    *,
    chunk_seconds: int,
    sample_rate_target: int,
    channels: int,
) -> None:
    """Capture microphone audio and emit chunk/final buffers into a queue."""
    stream: sd.InputStream | None = None
    samplerate = sample_rate_target
    target_samples = int(chunk_seconds * samplerate)

    def _stream_callback(
        indata: np.ndarray,
        _frames: int,
        _time_info: dict[str, object],
        status: sd.CallbackFlags,
    ) -> None:
        _audio_callback(state, indata, status)

    while not stop_event.is_set():
        if state.recording and stream is None:
            samplerate = _pick_input_samplerate(sample_rate_target)
            target_samples = int(chunk_seconds * samplerate)
            stream = sd.InputStream(
                samplerate=samplerate,
                channels=channels,
                dtype="float32",
                callback=_stream_callback,
            )
            stream.start()
            logger.info("Recording at %s Hz (device input, target=%s Hz)", samplerate, sample_rate_target)

        if not state.recording and stream is not None:
            session_id = state.session_id
            data = state.pop_buffer(None)
            if session_id is not None:
                audio_queue.put((data, samplerate, session_id, True))
            stream.stop()
            stream.close()
            stream = None
            state.clear_session()
            logger.info("Recording stopped")

        if (
            state.recording
            and stream is not None
            and state.session_id is not None
            and state.buffer_sample_count() >= target_samples
        ):
            data = state.pop_buffer(target_samples)
            audio_queue.put((data, samplerate, state.session_id, False))

        time.sleep(0.05)

    if stream is not None:
        session_id = state.stop_session()
        data = state.pop_buffer(None)
        if session_id is not None:
            audio_queue.put((data, samplerate, session_id, True))
        stream.stop()
        stream.close()


class HotkeyListener:
    """Track hotkey state and control recording lifecycle."""

    _ALIASES: ClassVar[dict[str, str]] = {
        "control": "ctrl",
        "strg": "ctrl",
        "option": "alt",
        "altgr": "alt",
        "escape": "esc",
        "return": "enter",
        "spacebar": "space",
        "command": "cmd",
        "windows": "cmd",
        "win": "cmd",
    }
    _CTRL_KEYS: ClassVar[set[keyboard.Key]] = {keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r}
    _SHIFT_KEYS: ClassVar[set[keyboard.Key]] = {keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r}
    _ALT_KEYS: ClassVar[set[keyboard.Key]] = {keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr}
    _CMD_KEYS: ClassVar[set[keyboard.Key]] = {keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r}
    _DISPLAY_NAMES: ClassVar[dict[str, str]] = {
        "ctrl": "Ctrl",
        "shift": "Shift",
        "alt": "Alt",
        "cmd": "Cmd",
        "esc": "Esc",
        "enter": "Enter",
        "space": "Space",
        "tab": "Tab",
        "backspace": "Backspace",
        "delete": "Delete",
        "up": "Up",
        "down": "Down",
        "left": "Left",
        "right": "Right",
    }

    def __init__(
        self,
        state: AppState,
        stop_event: threading.Event,
        *,
        recording_mode: Literal["hold", "toggle"] = "toggle",
        hotkey: str = "ctrl+alt+a",
        quit_hotkey: str = "ctrl+alt+q",
        can_start_recording: Callable[[], bool] | None = None,
        on_session_started: Callable[[int], None] | None = None,
        on_session_stopped: Callable[[int | None], None] | None = None,
        on_quit: Callable[[], None] | None = None,
        modifier_probe: ModifierProbe | None = None,
    ) -> None:
        self.state = state
        self.stop_event = stop_event
        self.recording_mode = recording_mode
        self.hotkey_keys, self.hotkey_label = self._parse_hotkey(hotkey)
        self.quit_hotkey_keys, self.quit_hotkey_label = self._parse_hotkey(quit_hotkey)
        self.pressed_keys: set[str] = set()
        self.combo_active = False
        self.can_start_recording = can_start_recording
        self.on_session_started = on_session_started
        self.on_session_stopped = on_session_stopped
        self.on_quit = on_quit
        self.modifier_probe = modifier_probe

    @classmethod
    def _canonical_name(cls, name: str) -> str:
        return cls._ALIASES.get(name.strip().lower(), name.strip().lower())

    @classmethod
    def _format_key(cls, key_name: str) -> str:
        if len(key_name) == 1:
            return key_name.upper()
        if key_name.startswith("f") and key_name[1:].isdigit():
            return key_name.upper()
        return cls._DISPLAY_NAMES.get(key_name, key_name.capitalize())

    @classmethod
    def _key_to_identifier(cls, key: KeyLike) -> str | None:
        if isinstance(key, keyboard.KeyCode):
            vk = getattr(key, "vk", None)
            if isinstance(vk, int):
                if 65 <= vk <= 90:  # A-Z
                    return chr(vk + 32)
                if 48 <= vk <= 57:  # 0-9
                    return chr(vk)
                if 96 <= vk <= 105:  # numpad 0-9
                    return chr(vk - 48)
            if key.char and key.char.isprintable():
                return key.char.lower()
            return None

        if key in cls._CTRL_KEYS:
            return "ctrl"
        if key in cls._SHIFT_KEYS:
            return "shift"
        if key in cls._ALT_KEYS:
            return "alt"
        if key in cls._CMD_KEYS:
            return "cmd"

        name = getattr(key, "name", None)
        if not name:
            return None
        return cls._canonical_name(name)

    @classmethod
    def key_to_identifier(cls, key: KeyLike) -> str | None:
        return cls._key_to_identifier(key)

    @classmethod
    def _parse_hotkey(cls, hotkey: str) -> tuple[frozenset[str], str]:
        raw_parts = [part.strip().lower() for part in hotkey.split("+")]
        if not raw_parts or any(not part for part in raw_parts):
            msg = f"Invalid recording hotkey: {hotkey!r}"
            raise ValueError(msg)

        parsed_keys: set[str] = set()
        display_parts: list[str] = []

        for raw_part in raw_parts:
            key_name = cls._canonical_name(raw_part)
            if len(key_name) == 1:
                parsed_keys.add(key_name)
                display_parts.append(cls._format_key(key_name))
                continue

            key_attr = getattr(keyboard.Key, key_name, None)
            if key_attr is None:
                msg = f"Unsupported hotkey key: {raw_part!r}"
                raise ValueError(msg)

            key_id = cls._key_to_identifier(key_attr)
            if key_id is None:
                msg = f"Unsupported hotkey key: {raw_part!r}"
                raise ValueError(msg)

            parsed_keys.add(key_id)
            display_parts.append(cls._format_key(key_id))

        return frozenset(parsed_keys), "+".join(display_parts)

    @classmethod
    def parse_hotkey(cls, hotkey: str) -> tuple[frozenset[str], str]:
        return cls._parse_hotkey(hotkey)

    def on_press(self, key: KeyLike) -> bool | None:
        key_id = self._key_to_identifier(key)
        sync_modifier_state(self.pressed_keys, self.modifier_probe)
        if key_id:
            self.pressed_keys.add(key_id)

        if is_combo_trigger(self.quit_hotkey_keys, key_id) and self.quit_hotkey_keys.issubset(self.pressed_keys):
            session_id = self.state.stop_session()
            if self.on_session_stopped is not None:
                self.on_session_stopped(session_id)
            self.stop_event.set()
            if self.on_quit is not None:
                self.on_quit()
            logger.info("Stopping application (hotkey %s)", self.quit_hotkey_label)
            return False

        combo_pressed = self.hotkey_keys.issubset(self.pressed_keys)
        if not combo_pressed or self.combo_active:
            return None
        if not is_combo_trigger(self.hotkey_keys, key_id):
            return None

        self.combo_active = True
        if self.recording_mode == "toggle":
            if self.state.recording:
                session_id = self.state.stop_session()
                if self.on_session_stopped is not None:
                    self.on_session_stopped(session_id)
                logger.info("Finishing transcription")
            else:
                if self.can_start_recording is not None and not self.can_start_recording():
                    return None
                session = self.state.start_session()
                if self.on_session_started is not None:
                    self.on_session_started(session)
                logger.info("Session %s started (toggle %s)", session, self.hotkey_label)
            return None

        if not self.state.recording:
            if self.can_start_recording is not None and not self.can_start_recording():
                return None
            session = self.state.start_session()
            if self.on_session_started is not None:
                self.on_session_started(session)
            logger.info("Session %s started (hold %s)", session, self.hotkey_label)

        return None

    def on_release(self, key: KeyLike) -> bool | None:
        key_id = self._key_to_identifier(key)
        if key_id:
            self.pressed_keys.discard(key_id)
        sync_modifier_state(self.pressed_keys, self.modifier_probe)

        combo_pressed = self.hotkey_keys.issubset(self.pressed_keys)
        if not combo_pressed:
            self.combo_active = False

        if self.recording_mode == "hold" and self.state.recording and not combo_pressed:
            session_id = self.state.stop_session()
            if self.on_session_stopped is not None:
                self.on_session_stopped(session_id)
            logger.info("Finishing transcription")

        return None
