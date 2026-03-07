from sttc import autostart


def test_get_executable_path_dev_headless(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(autostart, "is_bundled_executable", lambda: False)

    assert autostart.get_executable_path() == "uv run sttc run"


def test_get_executable_path_dev_gui_minimized(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(autostart, "is_bundled_executable", lambda: False)

    assert autostart.get_executable_path(gui=True, minimized=True) == "uv run sttc run --gui --minimized"


def test_get_executable_path_bundled_gui(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(autostart, "is_bundled_executable", lambda: True)
    monkeypatch.setattr(autostart.sys, "executable", "C:/Apps/sttc.exe")

    assert autostart.get_executable_path(gui=True, minimized=False) == '"C:/Apps/sttc.exe" run --gui'


def test_sync_autostart_enabled_calls_enable(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    called: dict[str, object] = {"enable": None, "disable": False}

    def _enable(*, gui: bool, minimized: bool) -> None:
        called["enable"] = (gui, minimized)

    monkeypatch.setattr(autostart, "enable_autostart", _enable)
    monkeypatch.setattr(autostart, "disable_autostart", lambda: called.__setitem__("disable", True))

    autostart.sync_autostart(True, gui=True, minimized=True)

    assert called["enable"] == (True, True)
    assert called["disable"] is False


def test_sync_autostart_disabled_calls_disable(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    called = {"enable": False, "disable": False}

    monkeypatch.setattr(
        autostart,
        "enable_autostart",
        lambda *, gui, minimized: called.__setitem__("enable", (gui, minimized)),
    )
    monkeypatch.setattr(autostart, "disable_autostart", lambda: called.__setitem__("disable", True))

    autostart.sync_autostart(False, gui=True, minimized=True)

    assert called["enable"] is False
    assert called["disable"] is True
