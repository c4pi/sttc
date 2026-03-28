"""Transcription backends: LiteLLM cloud and faster-whisper local."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
import importlib
import io
import logging
import os
from pathlib import Path
import shutil
import sys
from typing import TYPE_CHECKING, Any
import urllib.error
import urllib.parse
import urllib.request

import numpy as np
import soundfile as sf

if TYPE_CHECKING:
    from faster_whisper import WhisperModel

    from sttc.settings import Settings

logger = logging.getLogger(__name__)

TranscriberFn = Callable[[np.ndarray, int], str]
EngineStatusChangedFn = Callable[[str], None]


def _should_disable_hf_download_progress() -> bool:
    return sys.stdout is None or sys.stderr is None


@contextmanager
def _temporarily_disable_hf_download_progress() -> Iterator[None]:
    if not _should_disable_hf_download_progress():
        yield
        return

    previous = os.environ.get("HF_HUB_DISABLE_PROGRESS_BARS")
    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("HF_HUB_DISABLE_PROGRESS_BARS", None)
        else:
            os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = previous


def _resample_mono(audio: np.ndarray, original_sr: int, target_sr: int) -> np.ndarray:
    """Resample mono float audio to a target sample rate."""
    if original_sr == target_sr:
        return audio.astype(np.float32).reshape(-1)

    if audio.size == 0:
        return np.array([], dtype=np.float32)

    duration = audio.shape[0] / float(original_sr)
    target_samples = round(duration * target_sr)
    if target_samples <= 1:
        return audio.astype(np.float32).reshape(-1)

    src = np.linspace(0.0, 1.0, num=audio.shape[0], endpoint=True)
    dst = np.linspace(0.0, 1.0, num=target_samples, endpoint=True)
    return np.interp(dst, src, audio.astype(np.float32).reshape(-1)).astype(np.float32)


def _to_wav_bytes(audio: np.ndarray, samplerate: int) -> io.BytesIO:
    wav_buffer = io.BytesIO()

    # Normalize to a mono float32 track and serialize as PCM16 WAV.
    mono = audio.astype(np.float32).reshape(-1)
    clipped = np.clip(mono, -1.0, 1.0)
    int_audio = (clipped * 32767).astype(np.int16)

    with sf.SoundFile(
        wav_buffer,
        mode="w",
        samplerate=samplerate,
        channels=1,
        format="WAV",
        subtype="PCM_16",
    ) as wav_file:
        wav_file.write(int_audio)

    wav_buffer.seek(0)
    wav_buffer.name = "audio.wav"
    return wav_buffer


def _extract_transcription_text(response: Any) -> str:
    if response is None:
        return ""

    if isinstance(response, dict):
        text = response.get("text")
        if isinstance(text, str):
            return text.strip()

        data = response.get("data")
        if isinstance(data, dict):
            data_text = data.get("text")
            if isinstance(data_text, str):
                return data_text.strip()

    text_attr = getattr(response, "text", None)
    if isinstance(text_attr, str):
        return text_attr.strip()

    if hasattr(response, "model_dump"):
        dumped = response.model_dump()
        if isinstance(dumped, dict):
            text = dumped.get("text")
            if isinstance(text, str):
                return text.strip()

    return ""


def _configure_litellm_logging() -> None:
    for logger_name in ("LiteLLM", "LiteLLM Router", "LiteLLM Proxy"):
        ll_logger = logging.getLogger(logger_name)
        ll_logger.setLevel(logging.WARNING)
        ll_logger.propagate = False


def _openai_models_validation_request(api_key: str, *, timeout: float = 10.0):
    models_url = "https://api.openai.com/v1/models"
    parsed = urllib.parse.urlsplit(models_url)
    if parsed.scheme != "https":
        msg = "OpenAI API key validation requires HTTPS."
        raise RuntimeError(msg)

    request = urllib.request.Request(  # noqa: S310 - fixed HTTPS OpenAI endpoint validated above
        models_url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "sttc/0.1.0",
        },
        method="GET",
    )
    return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310 - fixed HTTPS OpenAI endpoint validated above


def validate_openai_api_key(api_key: str, *, timeout: float = 10.0) -> None:
    normalized = api_key.strip()
    if not normalized:
        msg = "Cloud transcription requires an OpenAI API key."
        raise RuntimeError(msg)

    try:
        with _openai_models_validation_request(normalized, timeout=timeout) as response:
            if response.status == 200:
                return
            msg = f"OpenAI API key validation failed with status {response.status}."
            raise RuntimeError(msg)
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            msg = "The OpenAI API key was rejected (401 Unauthorized)."
            raise RuntimeError(msg) from exc
        details = exc.read().decode("utf-8", errors="replace").strip()
        msg = f"OpenAI API key validation failed ({exc.code})."
        if details:
            msg = f"{msg} {details}"
        raise RuntimeError(msg) from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        msg = f"Could not reach OpenAI to validate the API key: {reason}"
        raise RuntimeError(msg) from exc

def _run_cloud_transcription(*, model_name: str, wav_buffer: io.BytesIO) -> Any:
    try:
        litellm = importlib.import_module("litellm")
        _configure_litellm_logging()
    except Exception as exc:  # pragma: no cover - environment dependent
        msg = (
            "Cloud STT backend is unavailable in this build. "
            f"Root cause: {exc!r}. "
            "Set STT_MODEL empty to use local faster-whisper."
        )
        raise RuntimeError(msg) from exc

    return litellm.transcription(model=model_name, file=wav_buffer)


def _build_cloud_transcriber(model_name: str) -> TranscriberFn:
    logger.info("Cloud transcription configured with model: %s", model_name)
    logger.info("Cloud mode uses the microphone input sample rate from the recorder stream")

    def transcribe(audio: np.ndarray, samplerate: int) -> str:
        if audio.size == 0:
            return ""

        wav_buffer = _to_wav_bytes(audio, samplerate)
        response = _run_cloud_transcription(model_name=model_name, wav_buffer=wav_buffer)
        return _extract_transcription_text(response)

    return transcribe


def _default_hf_cache_dir() -> Path:
    configured = os.environ.get("HF_HUB_CACHE") or os.environ.get("HUGGINGFACE_HUB_CACHE")
    if configured:
        return Path(configured).expanduser()

    try:
        constants = importlib.import_module("huggingface_hub.constants")
        cache_dir = getattr(constants, "HF_HUB_CACHE", None)
        if cache_dir:
            return Path(cache_dir)
    except Exception:
        pass

    return Path.home() / ".cache" / "huggingface" / "hub"


def _effective_model_cache_dir(model_cache_dir: Path | None) -> Path:
    return model_cache_dir if model_cache_dir is not None else _default_hf_cache_dir()


def _resolve_download_root(model_cache_dir: Path | None) -> str:
    effective_cache_dir = _effective_model_cache_dir(model_cache_dir)
    effective_cache_dir.mkdir(parents=True, exist_ok=True)
    return str(effective_cache_dir)


def _cache_repo_dir(model_name: str, model_cache_dir: Path | None) -> Path:
    cache_root = _effective_model_cache_dir(model_cache_dir)
    if "/" in model_name:
        owner, repo = model_name.split("/", maxsplit=1)
        repo_folder = f"models--{owner}--{repo}"
    else:
        repo_folder = f"models--Systran--faster-whisper-{model_name}"
    return cache_root / repo_folder


def _cache_lock_dir(model_name: str, model_cache_dir: Path | None) -> Path:
    repo_dir = _cache_repo_dir(model_name, model_cache_dir)
    return repo_dir.parent / ".locks" / repo_dir.name


def _is_local_model_snapshot(path: Path) -> bool:
    required_files = ("config.json", "model.bin", "tokenizer.json")
    return path.is_dir() and all((path / filename).exists() for filename in required_files)


def _resolve_cached_snapshot_dir(model_name: str, model_cache_dir: Path | None) -> Path | None:
    repo_dir = _cache_repo_dir(model_name, model_cache_dir)
    if not repo_dir.exists():
        return None

    refs_main = repo_dir / "refs" / "main"
    if refs_main.exists():
        snapshot_name = refs_main.read_text(encoding="utf-8").strip()
        if snapshot_name:
            candidate = repo_dir / "snapshots" / snapshot_name
            if _is_local_model_snapshot(candidate):
                return candidate

    snapshots_dir = repo_dir / "snapshots"
    if not snapshots_dir.exists():
        return None

    for candidate in sorted(snapshots_dir.iterdir(), reverse=True):
        if _is_local_model_snapshot(candidate):
            return candidate
    return None


def _clear_incomplete_model_cache(model_name: str, model_cache_dir: Path | None) -> None:
    repo_dir = _cache_repo_dir(model_name, model_cache_dir)
    if not repo_dir.exists():
        return
    if _resolve_cached_snapshot_dir(model_name, model_cache_dir) is not None:
        return

    logger.warning("Removing incomplete faster-whisper cache repo: %s", repo_dir)
    shutil.rmtree(repo_dir)

    lock_dir = _cache_lock_dir(model_name, model_cache_dir)
    if lock_dir.exists():
        logger.info("Removing stale faster-whisper cache lock directory: %s", lock_dir)
        shutil.rmtree(lock_dir)


def _download_local_model(model_name: str, model_cache_dir: Path | None) -> Path:
    download_model = importlib.import_module("faster_whisper").download_model
    kwargs: dict[str, Any] = {"cache_dir": _resolve_download_root(model_cache_dir)}
    if _should_disable_hf_download_progress():
        logger.info("Disabling Hugging Face progress bars because no console streams are available")
    with _temporarily_disable_hf_download_progress():
        model_path = Path(download_model(model_name, **kwargs))
    if not _is_local_model_snapshot(model_path):
        msg = f"Downloaded Whisper model is incomplete: {model_path}"
        raise RuntimeError(msg)
    return model_path


def _emit_engine_status(status_callback: EngineStatusChangedFn | None, message: str) -> None:
    if status_callback is not None:
        status_callback(message)


def _create_local_model(
    model_name: str,
    model_cache_dir: Path | None,
    *,
    status_callback: EngineStatusChangedFn | None = None,
) -> WhisperModel:
    whisper_model_cls = importlib.import_module("faster_whisper").WhisperModel
    effective_cache_dir = _effective_model_cache_dir(model_cache_dir)
    logger.info(
        "Whisper model cache root: %s",
        effective_cache_dir if model_cache_dir is not None else f"huggingface_hub default cache ({effective_cache_dir})",
    )
    repo_dir = _cache_repo_dir(model_name, model_cache_dir)
    logger.info("Whisper model cache repo: %s", repo_dir)

    model_path = _resolve_cached_snapshot_dir(model_name, model_cache_dir)
    if model_path is None:
        if repo_dir.exists():
            _emit_engine_status(status_callback, "Repairing incomplete Whisper cache...")
            _clear_incomplete_model_cache(model_name, model_cache_dir)
        _emit_engine_status(status_callback, "Downloading Whisper model... This can take a moment on first start.")
        logger.info("Downloading faster-whisper model: %s", model_name)
        model_path = _download_local_model(model_name, model_cache_dir)
        logger.info("Downloaded faster-whisper model snapshot: %s", model_path)
    else:
        logger.info("Using cached faster-whisper model snapshot: %s", model_path)

    _emit_engine_status(status_callback, "Starting Whisper engine...")
    return whisper_model_cls(
        model_size_or_path=str(model_path),
        device="cpu",
        compute_type="int8",
    )


def should_announce_model_download(settings: Settings) -> bool:
    """Return True when the configured local Whisper model is not cached yet."""
    if settings.stt_model:
        return False
    return _resolve_cached_snapshot_dir(settings.stt_whisper_model, settings.model_cache_dir) is None


def ensure_local_model_available(settings: Settings, *, announce: bool) -> None:
    """Ensure local faster-whisper model is downloaded and available."""
    if settings.stt_model:
        return

    if announce and should_announce_model_download(settings):
        print("Downloading speech model... (one-time setup)", flush=True)

    _create_local_model(
        model_name=settings.stt_whisper_model,
        model_cache_dir=settings.model_cache_dir,
    )


def _build_local_transcriber(
    model_name: str,
    target_sr: int,
    model_cache_dir: Path | None,
    *,
    status_callback: EngineStatusChangedFn | None = None,
) -> TranscriberFn:
    logger.info("Loading faster-whisper model: %s", model_name)
    whisper_model = _create_local_model(
        model_name,
        model_cache_dir,
        status_callback=status_callback,
    )
    logger.info("faster-whisper ready")
    logger.info("Whisper will resample recorder input to target sample rate: %s Hz", target_sr)

    def transcribe(audio: np.ndarray, samplerate: int) -> str:
        audio_target = _resample_mono(audio, samplerate, target_sr)
        if audio_target.size == 0:
            return ""
        segments, _ = whisper_model.transcribe(audio_target, language=None)
        return " ".join(segment.text for segment in segments).strip()

    return transcribe


def build_transcriber(
    settings: Settings,
    *,
    status_callback: EngineStatusChangedFn | None = None,
) -> TranscriberFn:
    """Build the selected transcription function."""
    if settings.stt_model:
        return _build_cloud_transcriber(settings.stt_model)

    return _build_local_transcriber(
        model_name=settings.stt_whisper_model,
        target_sr=settings.sample_rate_target,
        model_cache_dir=settings.model_cache_dir,
        status_callback=status_callback,
    )
