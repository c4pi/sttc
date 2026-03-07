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
