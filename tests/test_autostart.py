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
