"""Transcription backends: LiteLLM cloud and faster-whisper local."""

from __future__ import annotations

from collections.abc import Callable
import importlib
import io
import logging
from typing import TYPE_CHECKING, Any

from faster_whisper import WhisperModel
import numpy as np
import soundfile as sf

from sttc.recorder import _resample

if TYPE_CHECKING:
    from pathlib import Path

    from sttc.settings import Settings

logger = logging.getLogger(__name__)

TranscriberFn = Callable[[np.ndarray, int], str]


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

    def transcribe(audio: np.ndarray, samplerate: int) -> str:
        if audio.size == 0:
            return ""

        wav_buffer = _to_wav_bytes(audio, samplerate)
        response = _run_cloud_transcription(model_name=model_name, wav_buffer=wav_buffer)
        return _extract_transcription_text(response)

    return transcribe


def _resolve_download_root(model_cache_dir: Path | None) -> str | None:
    if model_cache_dir is None:
        return None
    model_cache_dir.mkdir(parents=True, exist_ok=True)
    return str(model_cache_dir)


def _create_local_model(model_name: str, model_cache_dir: Path | None) -> WhisperModel:
    kwargs: dict[str, Any] = {
        "model_size_or_path": model_name,
        "device": "cpu",
        "compute_type": "int8",
    }
    download_root = _resolve_download_root(model_cache_dir)
    if download_root:
        kwargs["download_root"] = download_root
    return WhisperModel(**kwargs)


def should_announce_model_download(settings: Settings) -> bool:
    """Return True when local model cache appears empty and setup is first-time."""
    model_cache_dir = settings.model_cache_dir
    if model_cache_dir is None:
        return False
    if not model_cache_dir.exists():
        return True
    return not any(model_cache_dir.iterdir())


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


def _build_local_transcriber(model_name: str, target_sr: int, model_cache_dir: Path | None) -> TranscriberFn:
    logger.info("Loading faster-whisper model: %s", model_name)
    whisper_model = _create_local_model(model_name, model_cache_dir)
    logger.info("faster-whisper ready")

    def transcribe(audio: np.ndarray, samplerate: int) -> str:
        audio_target = _resample(audio, samplerate, target_sr)
        if audio_target.size == 0:
            return ""
        segments, _ = whisper_model.transcribe(audio_target, language=None)
        return " ".join(segment.text for segment in segments).strip()

    return transcribe


def build_transcriber(settings: Settings) -> TranscriberFn:
    """Build the selected transcription function."""
    if settings.stt_model:
        return _build_cloud_transcriber(settings.stt_model)

    return _build_local_transcriber(
        model_name=settings.stt_whisper_model,
        target_sr=settings.sample_rate_target,
        model_cache_dir=settings.model_cache_dir,
    )
