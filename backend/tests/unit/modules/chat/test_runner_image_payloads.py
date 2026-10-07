"""Qué le llega a cada proveedor cuando el turno trae imágenes.

Sin imágenes el payload no cambia (texto a secas). Con imágenes, cada una va
precedida de una etiqueta que dice si es del mensaje actual o de uno anterior.
"""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import types

from app.infrastructure.config import Settings
from app.modules.chat.domain.entities import ImageInput
from app.modules.chat.domain.interfaces import ActiveProvider
from app.modules.chat.infrastructure.llm.claude import runner as claude_runner
from app.modules.chat.infrastructure.llm.gemini.runner import GeminiRunner
from app.modules.chat.infrastructure.llm.openai.runner import OpenAIRunner

_PNG = b"\x89PNG-bytes"
_JPEG = b"\xff\xd8jpeg-bytes"
_IMAGES = [
    ImageInput(mime="image/png", data=_PNG, filename="anterior.png", from_current_turn=False),
    ImageInput(mime="image/jpeg", data=_JPEG, filename="actual.jpg", from_current_turn=True),
]
_LABELS = [
    "Imagen de un mensaje anterior: anterior.png",
    "Imagen adjunta en este mensaje: actual.jpg",
]


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def test_image_labels_say_where_the_image_comes_from() -> None:
    assert [image.label for image in _IMAGES] == _LABELS


# ── OpenAI ────────────────────────────────────────────────────────────────


def _openai_provider() -> ActiveProvider:
    return ActiveProvider(
        kind="openai",
        chat_model="gpt-test",
        title_model="gpt-title",
        credential_kind="api_key",
        credential="k",
    )


class _OpenAIResponses:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> AsyncIterator[object]:
        self.calls.append(kwargs)

        async def stream() -> AsyncIterator[object]:
            yield SimpleNamespace(
                type="response.completed",
                response=SimpleNamespace(
                    usage=SimpleNamespace(
                        input_tokens=1,
                        output_tokens=1,
                        input_tokens_details=SimpleNamespace(cached_tokens=0),
                    ),
                    incomplete_details=None,
                ),
            )

        return stream()


async def _run_openai(
    monkeypatch: pytest.MonkeyPatch, images: list[ImageInput]
) -> list[dict[str, Any]]:
    monkeypatch.setattr(
        "app.modules.chat.infrastructure.llm.openai.runner.build_savi_tools", lambda **_: []
    )
    responses = _OpenAIResponses()
    client = SimpleNamespace(responses=responses)
    runner = OpenAIRunner(Settings(), _openai_provider(), client=client)  # type: ignore[arg-type]
    async for _ in runner.stream_turn("¿qué ves?", images=images):
        pass
    return responses.calls


async def test_openai_without_images_keeps_the_plain_text_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = await _run_openai(monkeypatch, [])

    assert calls[0]["input"] == [{"role": "user", "content": "¿qué ves?"}]


async def test_openai_sends_labelled_input_image_items(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = await _run_openai(monkeypatch, _IMAGES)

    assert calls[0]["input"] == [
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "¿qué ves?"},
                {"type": "input_text", "text": _LABELS[0]},
                {"type": "input_image", "image_url": f"data:image/png;base64,{_b64(_PNG)}"},
                {"type": "input_text", "text": _LABELS[1]},
                {"type": "input_image", "image_url": f"data:image/jpeg;base64,{_b64(_JPEG)}"},
            ],
        }
    ]


# ── Gemini ────────────────────────────────────────────────────────────────


class _GeminiModels:
    def __init__(self) -> None:
        self.calls: list[list[types.Content]] = []

    async def generate_content_stream(self, **kwargs: Any) -> AsyncIterator[object]:
        self.calls.append(kwargs["contents"])

        async def stream() -> AsyncIterator[object]:
            yield SimpleNamespace(
                candidates=[
                    SimpleNamespace(
                        content=SimpleNamespace(parts=[types.Part.from_text(text="ok")]),
                        finish_reason=None,
                    )
                ],
                usage_metadata=None,
            )

        return stream()


async def _run_gemini(
    monkeypatch: pytest.MonkeyPatch, images: list[ImageInput]
) -> list[types.Content]:
    monkeypatch.setattr(
        "app.modules.chat.infrastructure.llm.gemini.runner.build_savi_tools", lambda **_: []
    )
    models = _GeminiModels()
    client = SimpleNamespace(aio=SimpleNamespace(models=models))
    provider = ActiveProvider(
        kind="gemini",
        chat_model="gemini-test",
        title_model="gemini-title",
        credential_kind="api_key",
        credential="k",
    )
    runner = GeminiRunner(Settings(), provider, client=client)  # type: ignore[arg-type]
    async for _ in runner.stream_turn("¿qué ves?", images=images):
        pass
    return models.calls[0]


async def test_gemini_without_images_sends_a_single_text_part(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contents = await _run_gemini(monkeypatch, [])

    assert [(c.role, [p.text for p in c.parts or []]) for c in contents] == [
        ("user", ["¿qué ves?"])
    ]


async def test_gemini_adds_labelled_inline_data_parts(monkeypatch: pytest.MonkeyPatch) -> None:
    contents = await _run_gemini(monkeypatch, _IMAGES)

    parts = contents[0].parts or []
    assert [p.text for p in parts if p.text] == ["¿qué ves?", *_LABELS]
    inline = [p.inline_data for p in parts if p.inline_data is not None]
    assert [(i.mime_type, i.data) for i in inline] == [("image/png", _PNG), ("image/jpeg", _JPEG)]
    # Cada imagen va justo después de su etiqueta.
    assert [("text" if p.text else "image") for p in parts] == [
        "text",
        "text",
        "image",
        "text",
        "image",
    ]


# ── Claude ────────────────────────────────────────────────────────────────


def _claude_provider() -> ActiveProvider:
    return ActiveProvider(
        kind="claude", chat_model="m", title_model="t", credential_kind="api_key", credential="k"
    )


async def _drain(prompt: Any) -> list[dict[str, Any]]:
    return [message async for message in prompt]


async def test_claude_without_images_keeps_the_string_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[object] = []

    async def fake_query(*, prompt: object, options: object) -> AsyncIterator[object]:
        seen.append(prompt)
        return
        yield

    monkeypatch.setattr(claude_runner, "query", fake_query)
    monkeypatch.setattr(claude_runner, "_build_options", lambda *a, **k: None)
    runner = claude_runner.ClaudeAgentRunner(Settings(), _claude_provider())

    [event async for event in runner.stream_turn("hola")]

    assert seen == ["hola"]


async def test_claude_with_images_streams_one_structured_user_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[list[dict[str, Any]]] = []

    async def fake_query(*, prompt: Any, options: object) -> AsyncIterator[object]:
        sent.append(await _drain(prompt))
        return
        yield

    monkeypatch.setattr(claude_runner, "query", fake_query)
    monkeypatch.setattr(claude_runner, "_build_options", lambda *a, **k: None)
    runner = claude_runner.ClaudeAgentRunner(Settings(), _claude_provider())

    [event async for event in runner.stream_turn("¿qué ves?", images=_IMAGES)]

    assert sent == [
        [
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "¿qué ves?"},
                        {"type": "text", "text": _LABELS[0]},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": _b64(_PNG),
                            },
                        },
                        {"type": "text", "text": _LABELS[1]},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": _b64(_JPEG),
                            },
                        },
                    ],
                },
                "parent_tool_use_id": None,
                "session_id": "",
            }
        ]
    ]


async def test_claude_initialize_timeout_retry_rebuilds_the_image_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El generador de entrada se consume una sola vez: el reintento tiene que
    recibir uno nuevo, no el ya agotado."""
    attempts: list[list[dict[str, Any]]] = []

    async def fake_query(*, prompt: Any, options: object) -> AsyncIterator[object]:
        attempts.append(await _drain(prompt))
        if len(attempts) == 1:
            raise RuntimeError("Control request timeout: initialize")
        return
        yield

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(claude_runner, "query", fake_query)
    monkeypatch.setattr(claude_runner.asyncio, "sleep", no_sleep)

    [m async for m in claude_runner._open_query_stream("hola", None, _IMAGES)]  # type: ignore[arg-type]  # noqa: SLF001

    assert len(attempts) == 2
    assert attempts[0] == attempts[1]
    assert len(attempts[1]) == 1
