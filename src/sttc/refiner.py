"""Clipboard text processing via LiteLLM chat completions."""

from __future__ import annotations

import importlib
import logging
from typing import TYPE_CHECKING, Any, Literal

from sttc.transcriber import _configure_litellm_logging

if TYPE_CHECKING:
    from sttc.settings import Settings

logger = logging.getLogger(__name__)

RefinerMode = Literal["refine", "summary", "translation"]

REFINE_PROMPT = (
    "You are a multilingual transcript cleanup assistant. The input may be in German or English.\n"
    "Clean up the text in a single step: remove filler words and unintended repetitions, and correct grammar and spelling.\n"
    "Keep the output in exactly the same language as the input. Never translate under any circumstances.\n"
    "Preserve the original meaning, tone and intent as closely as possible. Return only the cleaned text."
)

SUMMARY_PROMPT = (
    "You are a multilingual summarization assistant. The input may be in German or English.\n"
    "Write a concise summary that captures all important key points.\n"
    "Keep the summary in the same language as the input. Do not translate.\n"
    "Return only the summary, with no explanations or prefacing text."
)

TRANSLATION_PROMPT = (
    "You are a translation assistant. Detect the input language automatically.\n"
    "If the input is German, translate it to English. If the input is English, translate it to German.\n"
    "If the input is any other language, translate it to English.\n"
    "Preserve the original meaning and tone as closely as possible. Return only the translated text."
)


def _system_prompt(mode: RefinerMode) -> str:
    if mode == "refine":
        return REFINE_PROMPT
    if mode == "summary":
        return SUMMARY_PROMPT
    if mode == "translation":
        return TRANSLATION_PROMPT
    msg = f"Unsupported processing mode: {mode}"
    raise ValueError(msg)


def _extract_message_content(response: Any) -> str:
    choices = getattr(response, "choices", None)
    if choices:
        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", None)
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                text = item.get("text") if isinstance(item, dict) else getattr(item, "text", None)
                if isinstance(text, str):
                    parts.append(text)
            return "".join(parts).strip()

    if hasattr(response, "model_dump"):
        dumped = response.model_dump()
        if isinstance(dumped, dict):
            dumped_choices = dumped.get("choices")
            if isinstance(dumped_choices, list) and dumped_choices:
                message = dumped_choices[0].get("message", {})
                content = message.get("content")
                if isinstance(content, str):
                    return content.strip()

    return ""


def process_text(text: str, mode: RefinerMode, settings: Settings) -> str:
    """Process clipboard text using the configured LLM mode."""
    if not settings.openai_api_key:
        msg = "Refinement requires OPENAI_API_KEY."
        raise RuntimeError(msg)

    if not isinstance(text, str):
        msg = "Clipboard content must be text."
        raise TypeError(msg)

    normalized = text.strip()
    if not normalized:
        msg = "Clipboard is empty or does not contain usable text."
        raise RuntimeError(msg)

    model_name = settings.refine_model.strip()
    if not model_name:
        msg = "REFINE_MODEL must not be empty."
        raise RuntimeError(msg)

    try:
        litellm = importlib.import_module("litellm")
        _configure_litellm_logging()
    except Exception as exc:  # pragma: no cover - environment dependent
        msg = f"Refinement backend is unavailable: {exc!r}"
        raise RuntimeError(msg) from exc

    logger.info("Running %s mode with model: %s", mode, model_name)
    try:
        response = litellm.completion(
            model=model_name,
            messages=[
                {"role": "system", "content": _system_prompt(mode)},
                {"role": "user", "content": normalized},
            ],
        )
    except Exception as exc:  # pragma: no cover - backend/network dependent
        msg = f"Refinement request failed: {exc}"
        raise RuntimeError(msg) from exc

    result = _extract_message_content(response)
    if not result:
        msg = "Refinement returned no text."
        raise RuntimeError(msg)
    return result
