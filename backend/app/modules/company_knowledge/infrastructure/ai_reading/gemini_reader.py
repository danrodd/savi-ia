"""Lectura de PDF con Gemini.

El PDF va como `Part` `application/pdf` (258 tokens por página). No se envía
`thinking_config`: `thinking_budget=0` devuelve 400 en los Flash-Lite nuevos,
y sin configurar ya no razonan para esta tarea (spike).
"""

from typing import Any, Protocol, cast

from google import genai
from google.genai import types

from app.modules.chat.domain.interfaces import ModelPrice
from app.modules.company_knowledge.domain.entities.page_reading import (
    AiReadResult,
    AiReadUsage,
)
from app.modules.company_knowledge.domain.interfaces import PdfPageReader
from app.modules.company_knowledge.infrastructure.ai_reading.errors import to_reading_error
from app.modules.company_knowledge.infrastructure.ai_reading.prompt import (
    SYSTEM_PROMPT,
    user_message,
)
from app.modules.company_knowledge.infrastructure.ai_reading.schema import (
    TRANSCRIPTION_SCHEMA,
    parse_transcription,
)


class _Models(Protocol):
    async def generate_content(self, **kwargs: Any) -> Any: ...


class GeminiPdfReader(PdfPageReader):
    def __init__(
        self,
        *,
        model: str,
        api_key: str | None,
        price: ModelPrice | None,
        models: _Models | None = None,
    ) -> None:
        self._model = model
        self._price = price
        self._models: _Models = models or cast(_Models, genai.Client(api_key=api_key).aio.models)

    @property
    def provider(self) -> str:
        return "gemini"

    @property
    def model(self) -> str:
        return self._model

    async def read(
        self, segment: bytes, first_page: int, last_page: int, *, attempt: int = 0
    ) -> AiReadResult:
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_json_schema=TRANSCRIPTION_SCHEMA,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        try:
            response = await self._models.generate_content(
                model=self._model,
                contents=[
                    types.Part.from_bytes(data=segment, mime_type="application/pdf"),
                    user_message(first_page, last_page, retry=attempt > 0),
                ],
                config=config,
            )
        except Exception as exc:  # noqa: BLE001
            raise to_reading_error(exc) from exc

        pages = parse_transcription(str(getattr(response, "text", "") or ""), first_page, last_page)
        return AiReadResult(pages=pages, usage=self._usage(response))

    def _usage(self, response: Any) -> AiReadUsage:
        metadata = getattr(response, "usage_metadata", None)
        input_tokens = int(getattr(metadata, "prompt_token_count", 0) or 0)
        output_tokens = int(getattr(metadata, "candidates_token_count", 0) or 0) + int(
            getattr(metadata, "thoughts_token_count", 0) or 0
        )
        cost = None
        if self._price is not None:
            cost = (input_tokens * self._price.input + output_tokens * self._price.output) / 1e6
        return AiReadUsage(input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=cost)
