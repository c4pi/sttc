from __future__ import annotations

from types import SimpleNamespace

import pytest

from sttc.refiner import REFINE_PROMPT, SUMMARY_PROMPT, TRANSLATION_PROMPT, process_text
from sttc.settings import Settings


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=content))]


@pytest.mark.parametrize(
    ("mode", "expected_prompt", "text", "result"),
    [
        ("refine", REFINE_PROMPT, "uh hello there", "Cleaned transcript"),
        ("summary", SUMMARY_PROMPT, "Long meeting notes", "Short summary"),
        ("translation", TRANSLATION_PROMPT, "Guten Morgen", "Good morning"),
    ],
)
def test_process_text_uses_expected_prompt(monkeypatch, mode: str, expected_prompt: str, text: str, result: str) -> None:
    calls: list[dict[str, object]] = []

    def _fake_completion(**kwargs):
        calls.append(kwargs)
        return _FakeResponse(result)

    monkeypatch.setattr(
        "sttc.refiner.importlib.import_module",
        lambda _name: SimpleNamespace(completion=_fake_completion),
    )

    settings = Settings(_env_file=None, openai_api_key="sk-test", refine_model="gpt-4.1-mini")
    processed = process_text(text, mode, settings)  # type: ignore[arg-type]

    assert processed == result
    assert calls[0]["model"] == "gpt-4.1-mini"
    assert calls[0]["messages"][0]["content"] == expected_prompt
    assert calls[0]["messages"][1]["content"] == text


def test_process_text_rejects_missing_api_key() -> None:
    settings = Settings(_env_file=None, openai_api_key=None)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        process_text("hello", "refine", settings)


@pytest.mark.parametrize("mode", ["refine", "summary", "translation"])
def test_process_text_rejects_blank_input(mode: str) -> None:
    settings = Settings(_env_file=None, openai_api_key="sk-test")

    with pytest.raises(RuntimeError, match="Clipboard is empty"):
        process_text("   ", mode, settings)  # type: ignore[arg-type]


@pytest.mark.parametrize("mode", ["refine", "summary", "translation"])
def test_process_text_rejects_empty_response(monkeypatch, mode: str) -> None:
    monkeypatch.setattr(
        "sttc.refiner.importlib.import_module",
        lambda _name: SimpleNamespace(completion=lambda **_kwargs: _FakeResponse("   ")),
    )

    settings = Settings(_env_file=None, openai_api_key="sk-test")

    with pytest.raises(RuntimeError, match="returned no text"):
        process_text("hello", mode, settings)  # type: ignore[arg-type]


def test_translation_prompt_describes_language_switching() -> None:
    assert "German" in TRANSLATION_PROMPT
    assert "English" in TRANSLATION_PROMPT
    assert "other language" in TRANSLATION_PROMPT


def test_refine_prompt_preserves_input_language() -> None:
    assert "German or English" in REFINE_PROMPT
    assert "Never translate" in REFINE_PROMPT
