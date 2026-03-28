from __future__ import annotations

import io
import os
from types import SimpleNamespace
from typing import TYPE_CHECKING
import urllib.error

import pytest

from sttc.settings import Settings
from sttc.transcriber import (
    _create_local_model,
    _download_local_model,
    should_announce_model_download,
    validate_openai_api_key,
)

if TYPE_CHECKING:
    from pathlib import Path


def _write_snapshot(cache_dir: Path, model_name: str = "base", snapshot_name: str = "snapshot-1") -> Path:
    repo_dir = cache_dir / f"models--Systran--faster-whisper-{model_name}"
    snapshot_dir = repo_dir / "snapshots" / snapshot_name
    snapshot_dir.mkdir(parents=True)
    (repo_dir / "refs").mkdir(parents=True, exist_ok=True)
    (repo_dir / "refs" / "main").write_text(snapshot_name, encoding="utf-8")
    for filename in ("config.json", "model.bin", "tokenizer.json"):
        (snapshot_dir / filename).write_text("ok", encoding="utf-8")
    return snapshot_dir


def _write_incomplete_repo(cache_dir: Path, model_name: str = "base", snapshot_name: str = "snapshot-1") -> Path:
    repo_dir = cache_dir / f"models--Systran--faster-whisper-{model_name}"
    snapshot_dir = repo_dir / "snapshots" / snapshot_name
    snapshot_dir.mkdir(parents=True)
    (repo_dir / "refs").mkdir(parents=True, exist_ok=True)
    (repo_dir / "refs" / "main").write_text(snapshot_name, encoding="utf-8")
    (snapshot_dir / "config.json").write_text("ok", encoding="utf-8")
    (repo_dir / "blobs").mkdir(parents=True, exist_ok=True)
    (repo_dir / "blobs" / "model.bin.incomplete").write_text("", encoding="utf-8")
    lock_dir = cache_dir / ".locks" / repo_dir.name
    lock_dir.mkdir(parents=True, exist_ok=True)
    (lock_dir / "download.lock").write_text("", encoding="utf-8")
    return repo_dir


def test_download_local_model_disables_progress_without_console(
    monkeypatch,
    tmp_path: Path,
) -> None:
    snapshot_dir = _write_snapshot(tmp_path)
    seen_env: list[str | None] = []

    def _fake_download_model(_model_name: str, **_kwargs) -> str:
        seen_env.append(os.environ.get("HF_HUB_DISABLE_PROGRESS_BARS"))
        return str(snapshot_dir)

    monkeypatch.setattr("sttc.transcriber.sys.stdout", None)
    monkeypatch.setattr("sttc.transcriber.sys.stderr", None)
    monkeypatch.delenv("HF_HUB_DISABLE_PROGRESS_BARS", raising=False)
    monkeypatch.setattr(
        "sttc.transcriber.importlib.import_module",
        lambda _name: SimpleNamespace(download_model=_fake_download_model),
    )

    result = _download_local_model("base", tmp_path)

    assert result == snapshot_dir
    assert seen_env == ["1"]
    assert os.environ.get("HF_HUB_DISABLE_PROGRESS_BARS") is None



def test_validate_openai_api_key_rejects_blank_key() -> None:
    with pytest.raises(RuntimeError, match="requires an OpenAI API key"):
        validate_openai_api_key("")

def test_validate_openai_api_key_accepts_success(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    class _Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("sttc.transcriber._openai_models_validation_request", lambda *_args, **_kwargs: _Response())

    validate_openai_api_key("sk-live")


def test_validate_openai_api_key_rejects_unauthorized(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    error = urllib.error.HTTPError(
        url="https://api.openai.com/v1/models",
        code=401,
        msg="Unauthorized",
        hdrs=None,
        fp=io.BytesIO(b'{"error":"invalid_api_key"}'),
    )
    monkeypatch.setattr(
        "sttc.transcriber._openai_models_validation_request",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(error),
    )

    with pytest.raises(RuntimeError, match="401 Unauthorized"):
        validate_openai_api_key("bad-key")


def test_validate_openai_api_key_reports_network_error(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    error = urllib.error.URLError("offline")
    monkeypatch.setattr(
        "sttc.transcriber._openai_models_validation_request",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(error),
    )

    with pytest.raises(RuntimeError, match="Could not reach OpenAI"):
        validate_openai_api_key("sk-live")


def test_should_announce_model_download_when_snapshot_is_missing(tmp_path: Path) -> None:
    (tmp_path / ".locks").mkdir()
    settings = Settings(_env_file=None, stt_model=None, stt_model_cache_dir=str(tmp_path))

    assert should_announce_model_download(settings) is True


def test_should_not_announce_model_download_when_snapshot_exists(tmp_path: Path) -> None:
    _write_snapshot(tmp_path)
    settings = Settings(_env_file=None, stt_model=None, stt_model_cache_dir=str(tmp_path))

    assert should_announce_model_download(settings) is False


def test_should_not_announce_model_download_from_default_cache(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    _write_snapshot(tmp_path)
    monkeypatch.setattr("sttc.transcriber._default_hf_cache_dir", lambda: tmp_path)
    settings = Settings(_env_file=None, stt_model=None, stt_model_cache_dir=None)

    assert should_announce_model_download(settings) is False


def test_should_announce_model_download_when_repo_is_incomplete(tmp_path: Path) -> None:
    _write_incomplete_repo(tmp_path)
    settings = Settings(_env_file=None, stt_model=None, stt_model_cache_dir=str(tmp_path))

    assert should_announce_model_download(settings) is True


def test_create_local_model_uses_cached_snapshot_and_updates_status(
    monkeypatch,
    tmp_path: Path,
) -> None:
    snapshot_dir = _write_snapshot(tmp_path)
    statuses: list[str] = []

    def _fake_import_module(_name: str) -> SimpleNamespace:
        return SimpleNamespace(WhisperModel=lambda **kwargs: kwargs)

    monkeypatch.setattr("sttc.transcriber.importlib.import_module", _fake_import_module)

    result = _create_local_model("base", tmp_path, status_callback=statuses.append)

    assert result["model_size_or_path"] == str(snapshot_dir)
    assert statuses == ["Starting Whisper engine..."]


def test_create_local_model_downloads_before_starting(
    monkeypatch,
    tmp_path: Path,
) -> None:
    statuses: list[str] = []
    download_calls: list[tuple[str, Path | None]] = []
    snapshot_dir = tmp_path / "models--Systran--faster-whisper-base" / "snapshots" / "snapshot-1"

    def _fake_download(model_name: str, model_cache_dir: Path | None) -> Path:
        download_calls.append((model_name, model_cache_dir))
        return _write_snapshot(tmp_path)

    monkeypatch.setattr("sttc.transcriber._download_local_model", _fake_download)
    monkeypatch.setattr(
        "sttc.transcriber.importlib.import_module",
        lambda _name: SimpleNamespace(WhisperModel=lambda **kwargs: kwargs),
    )

    result = _create_local_model("base", tmp_path, status_callback=statuses.append)

    assert result["model_size_or_path"] == str(snapshot_dir)
    assert download_calls == [("base", tmp_path)]
    assert statuses == [
        "Downloading Whisper model... This can take a moment on first start.",
        "Starting Whisper engine...",
    ]


def test_create_local_model_clears_incomplete_repo_before_downloading(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo_dir = _write_incomplete_repo(tmp_path)
    lock_dir = tmp_path / ".locks" / repo_dir.name
    statuses: list[str] = []
    snapshot_dir = tmp_path / repo_dir.name / "snapshots" / "snapshot-1"

    def _fake_download(model_name: str, model_cache_dir: Path | None) -> Path:
        assert model_name == "base"
        assert model_cache_dir == tmp_path
        assert repo_dir.exists() is False
        assert lock_dir.exists() is False
        return _write_snapshot(tmp_path)

    monkeypatch.setattr("sttc.transcriber._download_local_model", _fake_download)
    monkeypatch.setattr(
        "sttc.transcriber.importlib.import_module",
        lambda _name: SimpleNamespace(WhisperModel=lambda **kwargs: kwargs),
    )

    result = _create_local_model("base", tmp_path, status_callback=statuses.append)

    assert result["model_size_or_path"] == str(snapshot_dir)
    assert statuses == [
        "Repairing incomplete Whisper cache...",
        "Downloading Whisper model... This can take a moment on first start.",
        "Starting Whisper engine...",
    ]
