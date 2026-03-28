import threading

import pytest

from sttc.recorder import AppState
from sttc.runtime import RuntimeController
from sttc.settings import Settings


def _controller_for_apply_settings() -> RuntimeController:
    controller = RuntimeController.__new__(RuntimeController)
    controller._started = False
    controller.settings = Settings(_env_file=None)
    return controller


def test_apply_settings_without_restart_only_updates_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    controller = _controller_for_apply_settings()
    calls: list[str] = []

    def _fake_stop(_self: RuntimeController) -> None:
        calls.append("stop")

    def _fake_start(_self: RuntimeController) -> None:
        calls.append("start")

    monkeypatch.setattr(RuntimeController, "stop", _fake_stop)
    monkeypatch.setattr(RuntimeController, "start", _fake_start)

    updated = Settings(_env_file=None, recording_hotkey="ctrl+alt+r")
    controller.apply_settings(updated, restart=False)

    assert controller.settings == updated
    assert calls == []


def test_apply_settings_with_restart_stops_then_starts_when_running(monkeypatch: pytest.MonkeyPatch) -> None:
    controller = _controller_for_apply_settings()
    controller._started = True
    calls: list[str] = []

    def _fake_stop(self: RuntimeController) -> None:
        calls.append("stop")
        self._started = False

    def _fake_start(self: RuntimeController) -> None:
        calls.append("start")
        self._started = True

    monkeypatch.setattr(RuntimeController, "stop", _fake_stop)
    monkeypatch.setattr(RuntimeController, "start", _fake_start)

    updated = Settings(_env_file=None, stt_chunk_seconds=7)
    controller.apply_settings(updated, restart=True)

    assert controller.settings == updated
    assert calls == ["stop", "start"]


def test_apply_settings_with_restart_starts_engine_when_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    controller = _controller_for_apply_settings()
    calls: list[str] = []

    def _fake_stop(_self: RuntimeController) -> None:
        calls.append("stop")

    def _fake_start(self: RuntimeController) -> None:
        calls.append("start")
        self._started = True

    monkeypatch.setattr(RuntimeController, "stop", _fake_stop)
    monkeypatch.setattr(RuntimeController, "start", _fake_start)

    updated = Settings(_env_file=None, sample_rate_target=22050)
    controller.apply_settings(updated, restart=True)

    assert controller.settings == updated
    assert calls == ["start"]


def test_current_state_prefers_recording_over_transcribing() -> None:
    controller = RuntimeController.__new__(RuntimeController)
    controller.state = AppState(recording=True)
    controller._transcribing = True

    assert controller._current_state() == "recording"


class _FakeListener:
    def __init__(self, *, alive: bool = True, running: bool = False) -> None:
        self._alive = alive
        self.running = running
        self.join_calls: list[float] = []

    def is_alive(self) -> bool:
        return self._alive

    def join(self, timeout: float = 0) -> None:
        self.join_calls.append(timeout)


class _FakeThread:
    def __init__(self, target=None, kwargs=None, daemon=None) -> None:
        self.target = target
        self.kwargs = kwargs or {}
        self.daemon = daemon
        self.started = False

    def start(self) -> None:
        self.started = True

    def join(self, timeout: float | None = None) -> None:
        return


def test_ensure_listener_started_returns_when_listener_is_running() -> None:
    controller = RuntimeController.__new__(RuntimeController)
    controller._keyboard_listener = _FakeListener(alive=True, running=True)

    controller._ensure_listener_started()



def test_ensure_listener_started_raises_when_listener_stops_during_startup() -> None:
    controller = RuntimeController.__new__(RuntimeController)
    listener = _FakeListener(alive=False, running=False)
    controller._keyboard_listener = listener

    with pytest.raises(RuntimeError, match="stopped during startup"):
        controller._ensure_listener_started()

    assert listener.join_calls == [0]


def test_start_does_not_build_transcriber_on_main_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    controller = RuntimeController(Settings(_env_file=None))
    build_calls: list[str] = []

    class _KeyboardListener(_FakeListener):
        def __init__(self, **_kwargs) -> None:
            super().__init__(alive=True, running=True)

        def start(self) -> None:
            self.running = True

        def stop(self) -> None:
            self.running = False
            self._alive = False

    monkeypatch.setattr("sttc.runtime.build_transcriber", lambda _settings, **_kwargs: build_calls.append("build"))
    monkeypatch.setattr("sttc.runtime.threading.Thread", _FakeThread)
    monkeypatch.setattr("sttc.runtime.keyboard.Listener", _KeyboardListener)
    monkeypatch.setattr(RuntimeController, "_ensure_listener_started", lambda _self: None)

    controller.start()

    assert build_calls == []
    assert controller.is_running is True



def test_start_recording_waits_for_engine_readiness() -> None:
    controller = RuntimeController.__new__(RuntimeController)
    controller._started = True
    controller.state = AppState()
    controller._transcriber_ready = threading.Event()
    controller._startup_error = None
    statuses: list[str] = []
    controller._emit_engine_status = statuses.append
    controller._waiting_status_message = lambda: "Whisper model is still downloading. Please wait."
    controller._on_session_started = lambda _session_id: None

    controller.start_recording()

    assert statuses == ["Whisper model is still downloading. Please wait."]
    assert controller.state.is_recording() is False



def test_start_recording_surfaces_setup_message_when_engine_failed() -> None:
    controller = RuntimeController.__new__(RuntimeController)
    controller._started = True
    controller.state = AppState()
    controller._transcriber_ready = threading.Event()
    controller._startup_error = "OpenAI mode requires an API key. Open Settings to continue."
    statuses: list[str] = []
    controller._emit_engine_status = statuses.append
    controller._on_session_started = lambda _session_id: None

    controller.start_recording()

    assert statuses == ["OpenAI mode requires an API key. Open Settings to continue."]
    assert controller.state.is_recording() is False



def test_startup_status_message_mentions_whisper_download(monkeypatch: pytest.MonkeyPatch) -> None:
    controller = RuntimeController(Settings(_env_file=None, stt_model=None))
    monkeypatch.setattr("sttc.runtime.should_announce_model_download", lambda _settings: True)

    assert controller._startup_status_message() == "Downloading Whisper model... This can take a moment on first start."



def test_startup_status_message_requires_api_key_for_cloud_mode() -> None:
    controller = RuntimeController(Settings(_env_file=None, stt_model="openai/gpt-4o-mini-transcribe", openai_api_key=None))

    assert controller._startup_status_message() == "OpenAI mode requires an API key. Open Settings to continue."
