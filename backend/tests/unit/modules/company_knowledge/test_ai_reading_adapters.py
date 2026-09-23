"""Esquema de la transcripción, errores de proveedor y adaptadores.

Los adaptadores se prueban con clientes falsos: se verifica el pedido que
arman (formato, esquema, razonamiento) y cómo leen la respuesta, sin gastar
tokens.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.modules.chat.domain.exceptions import LlmProviderUnavailableError
from app.modules.chat.domain.interfaces import ActiveProvider, ActiveProviderResolver, ModelPrice
from app.modules.company_knowledge.domain.exceptions import AiReadingError
from app.modules.company_knowledge.domain.value_objects import AiReadErrorCode
from app.modules.company_knowledge.infrastructure.ai_reading.claude_reader import ClaudePdfReader
from app.modules.company_knowledge.infrastructure.ai_reading.errors import to_reading_error
from app.modules.company_knowledge.infrastructure.ai_reading.gemini_reader import GeminiPdfReader
from app.modules.company_knowledge.infrastructure.ai_reading.openai_reader import OpenAiPdfReader
from app.modules.company_knowledge.infrastructure.ai_reading.prompt import (
    SYSTEM_PROMPT,
    user_message,
)
from app.modules.company_knowledge.infrastructure.ai_reading.reader_provider import (
    ActiveProviderAiReaderProvider,
)
from app.modules.company_knowledge.infrastructure.ai_reading.schema import (
    TRANSCRIPTION_SCHEMA,
    parse_transcription,
)


def _page(numero: int, contenido: str = "texto", legible: bool = True) -> dict[str, Any]:
    return {"numero": numero, "tipo": "texto", "contenido": contenido, "legible": legible}


# ── Esquema ────────────────────────────────────────────────────────────────


def test_schema_is_strict_for_openai() -> None:
    page = TRANSCRIPTION_SCHEMA["properties"]["paginas"]["items"]
    assert TRANSCRIPTION_SCHEMA["additionalProperties"] is False
    assert page["additionalProperties"] is False
    assert set(page["required"]) == set(page["properties"])


def test_parse_keeps_only_pages_of_the_segment_in_order() -> None:
    raw = json.dumps({"paginas": [_page(4), _page(9), _page(3), _page(3, "repetida")]})

    pages = parse_transcription(raw, 3, 5)

    assert [(p.page_number, p.content) for p in pages] == [(3, "texto"), (4, "texto")]


def test_parse_fixes_pages_numbered_from_one_inside_the_segment() -> None:
    """Gemini numeró el tramo 6-10 como 1-5 (segunda ronda del spike)."""
    raw = {"paginas": [_page(1, "seis"), _page(2, "siete"), _page(3, "ocho")]}

    pages = parse_transcription(raw, 6, 10)

    assert [(p.page_number, p.content) for p in pages] == [(6, "seis"), (7, "siete"), (8, "ocho")]


def test_parse_does_not_shift_when_some_page_is_already_in_range() -> None:
    raw = {"paginas": [_page(1), _page(6)]}
    assert [p.page_number for p in parse_transcription(raw, 6, 10)] == [6]


def test_parse_accepts_an_already_decoded_dict() -> None:
    assert parse_transcription({"paginas": [_page(1)]}, 1, 1)[0].page_number == 1


def test_an_empty_page_is_never_legible() -> None:
    page = parse_transcription({"paginas": [_page(1, "   ", legible=True)]}, 1, 1)[0]
    assert (page.content, page.legible) == ("", False)


@pytest.mark.parametrize(
    "raw",
    [
        "esto no es json",
        json.dumps({"otra": []}),
        json.dumps({"paginas": [{"numero": 1, "tipo": "poema", "contenido": "", "legible": True}]}),
        json.dumps({"paginas": [_page(7)]}),  # ninguna página del tramo
    ],
)
def test_invalid_answers_are_retryable_json_errors(raw: str) -> None:
    with pytest.raises(AiReadingError) as info:
        parse_transcription(raw, 1, 2)
    assert (info.value.code, info.value.retryable) == (AiReadErrorCode.INVALID_JSON, True)


def test_retry_message_reminds_the_format() -> None:
    assert "formato" not in user_message(1, 5)
    assert "formato" in user_message(1, 5, retry=True)
    assert "Página 3 del documento" in user_message(3, 3)


def test_prompt_keeps_the_rules_found_in_the_spike() -> None:
    assert "4.000 se escribe 4.000" in SYSTEM_PROMPT
    assert "CamScanner" in SYSTEM_PROMPT


# ── Errores de proveedor ───────────────────────────────────────────────────


class _HttpError(Exception):
    def __init__(self, status_code: int, body: Any = None) -> None:
        super().__init__("mensaje del proveedor con contenido del pedido")
        self.status_code = status_code
        self.body = body


class _GeminiError(Exception):
    def __init__(self, code: int) -> None:
        super().__init__("error")
        self.code = code


@pytest.mark.parametrize(
    ("error", "code", "retryable"),
    [
        (_HttpError(429), AiReadErrorCode.RATE_LIMITED, True),
        (_HttpError(429, {"code": "insufficient_quota"}), AiReadErrorCode.UNAVAILABLE, False),
        (_HttpError(401), AiReadErrorCode.UNAVAILABLE, False),
        (_HttpError(413), AiReadErrorCode.PAGE_TOO_LARGE, False),
        (_HttpError(500), AiReadErrorCode.PROVIDER_ERROR, True),
        (_HttpError(400), AiReadErrorCode.PROVIDER_ERROR, False),
        (_GeminiError(503), AiReadErrorCode.PROVIDER_ERROR, True),
        (TimeoutError(), AiReadErrorCode.TIMEOUT, True),
        (ConnectionError(), AiReadErrorCode.PROVIDER_ERROR, True),
    ],
)
def test_provider_errors_are_classified(
    error: Exception, code: AiReadErrorCode, retryable: bool
) -> None:
    mapped = to_reading_error(error)
    assert (mapped.code, mapped.retryable) == (code, retryable)
    # Nunca copia el mensaje del proveedor: puede traer contenido.
    assert "contenido del pedido" not in str(mapped)


# ── OpenAI ─────────────────────────────────────────────────────────────────


class _Usage:
    input_tokens = 3000
    output_tokens = 500


class _OpenAiResponse:
    def __init__(self, text: str) -> None:
        self.output_text = text
        self.usage = _Usage()


class _FakeResponses:
    def __init__(self, text: str) -> None:
        self.text = text
        self.requests: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        return _OpenAiResponse(self.text)


class _FakeOpenAi:
    def __init__(self, text: str) -> None:
        self.responses = _FakeResponses(text)


async def test_openai_reader_sends_the_pdf_with_a_strict_schema() -> None:
    client = _FakeOpenAi(json.dumps({"paginas": [_page(2), _page(3)]}))
    reader = OpenAiPdfReader(
        model="gpt-6-luna", api_key="k", price=ModelPrice(input=0.1, output=0.5), client=client
    )

    result = await reader.read(b"%PDF-fake", 2, 3)

    request = client.responses.requests[0]
    file_part, text_part = request["input"][0]["content"]
    assert file_part["type"] == "input_file"
    assert file_part["file_data"].startswith("data:application/pdf;base64,")
    assert "Páginas 2 a 3" in text_part["text"]
    assert request["text"]["format"]["strict"] is True
    assert request["reasoning"] == {"effort": "low"}
    assert request["instructions"] == SYSTEM_PROMPT
    assert [p.page_number for p in result.pages] == [2, 3]
    assert result.usage.cost_usd == pytest.approx((3000 * 0.1 + 500 * 0.5) / 1e6)


async def test_openai_reader_without_price_reports_unknown_cost() -> None:
    reader = OpenAiPdfReader(
        model="m", api_key="k", price=None, client=_FakeOpenAi(json.dumps({"paginas": [_page(1)]}))
    )
    assert (await reader.read(b"x", 1, 1)).usage.cost_usd is None


# ── Gemini ─────────────────────────────────────────────────────────────────


class _Metadata:
    prompt_token_count = 800
    candidates_token_count = 300
    thoughts_token_count = None


class _GeminiResponse:
    def __init__(self, text: str) -> None:
        self.text = text
        self.usage_metadata = _Metadata()


class _FakeModels:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[dict[str, Any]] = []

    async def generate_content(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return _GeminiResponse(self.text)


async def test_gemini_reader_uses_the_schema_and_no_thinking_config() -> None:
    models = _FakeModels(json.dumps({"paginas": [_page(1)]}))
    reader = GeminiPdfReader(
        model="gemini-flash-lite-latest",
        api_key="k",
        price=ModelPrice(input=0.3, output=2.5),
        models=models,
    )

    result = await reader.read(b"%PDF-fake", 1, 1)

    config = models.calls[0]["config"]
    assert config.response_json_schema == TRANSCRIPTION_SCHEMA
    # `thinking_budget=0` devuelve 400 en los Flash-Lite nuevos (spike).
    assert config.thinking_config is None
    part = models.calls[0]["contents"][0]
    assert part.inline_data.mime_type == "application/pdf"
    assert result.usage.cost_usd == pytest.approx((800 * 0.3 + 300 * 2.5) / 1e6)


def test_gemini_reader_keeps_its_client_alive() -> None:
    """Regresión: `genai.Client.__del__` cierra las conexiones.

    El lector guardaba solo `client.aio.models`; el recolector de basura
    liberaba el cliente y todos los tramos después del primero fallaban.
    """
    import gc
    import weakref

    from google import genai

    reader = GeminiPdfReader(model="m", api_key="k", price=None)
    client = reader._client  # pyright: ignore[reportPrivateUsage]
    assert isinstance(client, genai.Client)
    ref = weakref.ref(client)
    del client
    gc.collect()
    assert ref() is not None


# ── Qué lector se arma ─────────────────────────────────────────────────────


class _Resolver(ActiveProviderResolver):
    def __init__(self, provider: ActiveProvider | None) -> None:
        self._provider = provider

    async def resolve(self) -> ActiveProvider:
        if self._provider is None:
            raise LlmProviderUnavailableError("No hay un proveedor de IA activo.")
        return self._provider


def _provider(kind: str, **overrides: Any) -> ActiveProvider:
    values: dict[str, Any] = {
        "kind": kind,
        "chat_model": "chat",
        "title_model": "title",
        "credential_kind": "api_key",
        "credential": "k",
        "document_model": "docs",
        "pricing": {"docs": ModelPrice(input=1.0, output=5.0)},
    }
    values.update(overrides)
    return ActiveProvider(**values)


@pytest.mark.parametrize(
    ("kind", "reader_type"),
    [("openai", OpenAiPdfReader), ("gemini", GeminiPdfReader), ("claude", ClaudePdfReader)],
)
async def test_the_reader_follows_the_active_provider_and_document_model(
    kind: str, reader_type: type
) -> None:
    readers = ActiveProviderAiReaderProvider(_Resolver(_provider(kind)))

    reader = await readers.build_reader()
    availability = await readers.availability()

    assert isinstance(reader, reader_type)
    assert reader.model == "docs"
    assert (availability.available, availability.model, availability.input_price) == (
        True,
        "docs",
        1.0,
    )


async def test_without_document_model_the_chat_model_reads() -> None:
    readers = ActiveProviderAiReaderProvider(_Resolver(_provider("openai", document_model="")))
    reader = await readers.build_reader()
    assert reader is not None and reader.model == "chat"


async def test_no_active_provider_means_no_reader() -> None:
    readers = ActiveProviderAiReaderProvider(_Resolver(None))
    assert await readers.build_reader() is None
    availability = await readers.availability()
    assert (availability.available, availability.reason) == (
        False,
        "No hay un proveedor de IA activo.",
    )
