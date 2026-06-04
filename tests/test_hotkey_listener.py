import threading

from pynput import keyboard
import pytest

from sttc.recorder import AppState, HotkeyListener, is_combo_trigger, sync_modifier_state


def test_toggle_mode_starts_and_stops_with_repeated_hotkey() -> None:
    state = AppState()
    stop_event = threading.Event()
    listener = HotkeyListener(state, stop_event, recording_mode="toggle")

    listener.on_press(keyboard.Key.ctrl_l)
    listener.on_press(keyboard.Key.alt_l)
    listener.on_press(keyboard.KeyCode.from_char("a"))
    assert state.recording is True
    first_session = state.session_id

    listener.on_release(keyboard.KeyCode.from_char("a"))
    listener.on_release(keyboard.Key.alt_l)
    listener.on_release(keyboard.Key.ctrl_l)
    assert state.recording is True

    listener.on_press(keyboard.Key.ctrl_l)
    listener.on_press(keyboard.Key.alt_l)
    listener.on_press(keyboard.KeyCode.from_char("a"))
    assert state.recording is False
    assert state.session_id == first_session


def test_hold_mode_stops_on_key_release() -> None:
    state = AppState()
    stop_event = threading.Event()
    listener = HotkeyListener(state, stop_event, recording_mode="hold")

    listener.on_press(keyboard.Key.ctrl_l)
    listener.on_press(keyboard.Key.alt_l)
    listener.on_press(keyboard.KeyCode.from_char("a"))
    assert state.recording is True

    listener.on_release(keyboard.KeyCode.from_char("a"))
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


def test_custom_hotkey_ctrl_alt_a_toggle_mode() -> None:
    state = AppState()
    stop_event = threading.Event()
    listener = HotkeyListener(state, stop_event, recording_mode="toggle", hotkey="ctrl+alt+a")

    listener.on_press(keyboard.Key.ctrl_l)
    listener.on_press(keyboard.Key.alt_l)
    listener.on_press(keyboard.KeyCode.from_char("a"))
    assert state.recording is True

    listener.on_release(keyboard.KeyCode.from_char("a"))
    listener.on_release(keyboard.Key.alt_l)
    listener.on_release(keyboard.Key.ctrl_l)

    listener.on_press(keyboard.Key.ctrl_l)
    listener.on_press(keyboard.Key.alt_l)
    listener.on_press(keyboard.KeyCode.from_char("a"))
    assert state.recording is False


def test_hotkey_respects_engine_readiness_gate() -> None:
    state = AppState()
    stop_event = threading.Event()
    calls = {"count": 0}

    def _can_start() -> bool:
        calls["count"] += 1
        return False

    listener = HotkeyListener(state, stop_event, recording_mode="toggle", can_start_recording=_can_start)

    listener.on_press(keyboard.Key.ctrl_l)
    listener.on_press(keyboard.Key.alt_l)
    listener.on_press(keyboard.KeyCode.from_char("a"))

    assert calls["count"] == 1
    assert state.recording is False


def test_invalid_hotkey_raises_value_error() -> None:
    state = AppState()
    stop_event = threading.Event()
    with pytest.raises(ValueError, match="Unsupported hotkey key"):
        HotkeyListener(state, stop_event, hotkey="ctrl+notakey")


def test_is_combo_trigger_requires_non_modifier_key() -> None:
    combo = frozenset({"ctrl", "alt", "q"})
    assert is_combo_trigger(combo, "q") is True
    assert is_combo_trigger(combo, "ctrl") is False
    assert is_combo_trigger(combo, "alt") is False
    assert is_combo_trigger(combo, None) is False


def test_is_combo_trigger_modifier_only_combo_triggers_on_member() -> None:
    combo = frozenset({"ctrl", "alt"})
    assert is_combo_trigger(combo, "alt") is True
    assert is_combo_trigger(combo, "shift") is False


def test_sync_modifier_state_reconciles_with_os() -> None:
    pressed = {"ctrl", "a"}
    # OS reports only 'alt' physically held: 'ctrl' must drop, 'alt' must appear,
    # the non-modifier 'a' must be left untouched.
    sync_modifier_state(pressed, lambda: {"alt"})
    assert pressed == {"alt", "a"}


def test_sync_modifier_state_noop_without_probe() -> None:
    pressed = {"ctrl", "alt"}
    sync_modifier_state(pressed, None)
    assert pressed == {"ctrl", "alt"}


def test_quit_does_not_fire_from_stuck_modifiers() -> None:
    state = AppState()
    stop_event = threading.Event()
    # OS reports nothing physically held; the listener should self-heal.
    listener = HotkeyListener(state, stop_event, recording_mode="toggle", modifier_probe=set)
    # Simulate ctrl+alt left "stuck" by missed key-up events (Alt+Tab / lock screen).
    listener.pressed_keys.update({"ctrl", "alt"})

    result = listener.on_press(keyboard.KeyCode.from_vk(81))  # 'q'

    assert result is None
    assert stop_event.is_set() is False
    assert state.recording is False


def test_quit_fires_when_modifiers_actually_held() -> None:
    state = AppState()
    stop_event = threading.Event()
    listener = HotkeyListener(
        state,
        stop_event,
        recording_mode="toggle",
        modifier_probe=lambda: {"ctrl", "alt"},
    )

    result = listener.on_press(keyboard.KeyCode.from_vk(81))  # 'q'

    assert result is False
    assert stop_event.is_set() is True


def test_recording_does_not_start_from_stuck_modifiers() -> None:
    state = AppState()
    stop_event = threading.Event()
    listener = HotkeyListener(state, stop_event, recording_mode="toggle", modifier_probe=set)
    listener.pressed_keys.update({"ctrl", "alt"})

    # A lone non-trigger keystroke while modifiers are only "stuck" must not record.
    listener.on_press(keyboard.KeyCode.from_char("b"))
    assert state.recording is False

    # And the real combo still works once the OS actually reports the modifiers.
    listener.modifier_probe = lambda: {"ctrl", "alt"}
    listener.on_press(keyboard.KeyCode.from_char("a"))
    assert state.recording is True
