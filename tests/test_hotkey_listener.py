import threading

from pynput import keyboard
import pytest

from sttc.recorder import AppState, HotkeyListener


def test_toggle_mode_starts_and_stops_with_repeated_hotkey() -> None:
    state = AppState()
    stop_event = threading.Event()
    listener = HotkeyListener(state, stop_event, recording_mode="toggle")

    listener.on_press(keyboard.Key.ctrl_l)
    listener.on_press(keyboard.Key.shift_l)
    assert state.recording is True
    first_session = state.session_id

    listener.on_release(keyboard.Key.shift_l)
    listener.on_release(keyboard.Key.ctrl_l)
    assert state.recording is True

    listener.on_press(keyboard.Key.ctrl_l)
    listener.on_press(keyboard.Key.shift_l)
    assert state.recording is False
    assert state.session_id == first_session


def test_hold_mode_stops_on_key_release() -> None:
    state = AppState()
    stop_event = threading.Event()
    listener = HotkeyListener(state, stop_event, recording_mode="hold")

    listener.on_press(keyboard.Key.ctrl_l)
    listener.on_press(keyboard.Key.shift_l)
    assert state.recording is True

    listener.on_release(keyboard.Key.shift_l)
    assert state.recording is False


def test_quit_hotkey_stops_listener_and_sets_stop_event() -> None:
    state = AppState()
    stop_event = threading.Event()
    listener = HotkeyListener(state, stop_event, recording_mode="toggle")

    state.start_session()
    listener.on_press(keyboard.Key.ctrl_l)
    listener.on_press(keyboard.Key.alt_l)
    result = listener.on_press(keyboard.KeyCode.from_vk(81))

    assert result is False
    assert stop_event.is_set() is True
    assert state.recording is False


def test_quit_hotkey_supports_altgr_like_keycode() -> None:
    state = AppState()
    stop_event = threading.Event()
    listener = HotkeyListener(state, stop_event, recording_mode="toggle")

    listener.on_press(keyboard.Key.ctrl_l)
    listener.on_press(keyboard.Key.alt_l)
    result = listener.on_press(keyboard.KeyCode(vk=81, char="@"))

    assert result is False
    assert stop_event.is_set() is True


def test_esc_no_longer_stops_app() -> None:
    state = AppState()
    stop_event = threading.Event()
    listener = HotkeyListener(state, stop_event, recording_mode="toggle")

    state.start_session()
    result = listener.on_release(keyboard.Key.esc)

    assert result is None
    assert stop_event.is_set() is False
    assert state.recording is True


def test_custom_hotkey_ctrl_alt_r_toggle_mode() -> None:
    state = AppState()
    stop_event = threading.Event()
    listener = HotkeyListener(state, stop_event, recording_mode="toggle", hotkey="ctrl+alt+r")

    listener.on_press(keyboard.Key.ctrl_l)
    listener.on_press(keyboard.Key.alt_l)
    listener.on_press(keyboard.KeyCode.from_char("r"))
    assert state.recording is True

    listener.on_release(keyboard.KeyCode.from_char("r"))
    listener.on_release(keyboard.Key.alt_l)
    listener.on_release(keyboard.Key.ctrl_l)

    listener.on_press(keyboard.Key.ctrl_l)
    listener.on_press(keyboard.Key.alt_l)
    listener.on_press(keyboard.KeyCode.from_char("r"))
    assert state.recording is False


def test_invalid_hotkey_raises_value_error() -> None:
    state = AppState()
    stop_event = threading.Event()
    with pytest.raises(ValueError, match="Unsupported hotkey key"):
        HotkeyListener(state, stop_event, hotkey="ctrl+notakey")
