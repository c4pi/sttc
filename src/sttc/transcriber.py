"""Transcription backends: LiteLLM cloud and faster-whisper local."""

from collections.abc import Callable
import io
import logging
from typing import Any

import numpy as np
import soundfile as sf

from sttc.recorder import _resample
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


def _build_cloud_transcriber(model_name: str) -> TranscriberFn:
    try:
        from litellm import transcription
    except Exception as exc:
        raise RuntimeError("litellm is required for cloud transcription") from exc

    logger.info("Cloud transcription configured with model: %s", model_name)

    def transcribe(audio: np.ndarray, samplerate: int) -> str:
        if audio.size == 0:
            return ""

        wav_buffer = _to_wav_bytes(audio, samplerate)
        response = transcription(model=model_name, file=wav_buffer)
        return _extract_transcription_text(response)

    return transcribe


def _build_local_transcriber(model_name: str, target_sr: int) -> TranscriberFn:
    try:
        from faster_whisper import WhisperModel
    except Exception as exc:
        raise RuntimeError("faster-whisper is required for local transcription") from exc

    logger.info("Loading faster-whisper model: %s", model_name)
    whisper_model = WhisperModel(model_name, device="cpu", compute_type="int8")
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
    )
