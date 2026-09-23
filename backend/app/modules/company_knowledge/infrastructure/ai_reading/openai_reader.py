"""Lectura de PDF con OpenAI (Responses API).

El PDF va como `input_file` en base64: la API manda al modelo el texto y la
imagen de cada página. La salida estructurada es `json_schema` estricto.
"""

import base64
from typing import Any, Protocol, cast

from openai import AsyncOpenAI, BadRequestError

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

# `none` y `low` dieron la misma calidad en el spike con `gpt-6-luna`; `low`
# costó ~15 % más pero con `none` coló un carácter cirílico en un código.
# `minimal` no existe en los modelos GPT-6 (400).
_REASONING_EFFORT = "low"


class _Responses(Protocol):
    async def create(self, **kwargs: Any) -> Any: ...


class _Client(Protocol):
    responses: _Responses


class OpenAiPdfReader(PdfPageReader):
    def __init__(
        self,
        *,
        model: str,
        api_key: str | None,
        price: ModelPrice | None,
        client: _Client | None = None,
    ) -> None:
        self._model = model
        self._price = price
        self._client: _Client = client or cast(_Client, AsyncOpenAI(api_key=api_key))

    @property
    def provider(self) -> str:
        return "openai"

    @property
    def model(self) -> str:
        return self._model

    async def read(
        self, segment: bytes, first_page: int, last_page: int, *, attempt: int = 0
    ) -> AiReadResult:
        data = base64.b64encode(segment).decode("ascii")
        request: dict[str, Any] = {
            "model": self._model,
            "instructions": SYSTEM_PROMPT,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_file",
                            "filename": f"paginas-{first_page}-{last_page}.pdf",
                            "file_data": f"data:application/pdf;base64,{data}",
                        },
                        {
                            "type": "input_text",
                            "text": user_message(first_page, last_page, retry=attempt > 0),
                        },
                    ],
                }
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "transcripcion",
                    "schema": TRANSCRIPTION_SCHEMA,
                    "strict": True,
                }
            },
            "reasoning": {"effort": _REASONING_EFFORT},
        }
        try:
            response = await self._create(request)
        except Exception as exc:  # noqa: BLE001
            raise to_reading_error(exc) from exc

        pages = parse_transcription(
            str(getattr(response, "output_text", "") or ""), first_page, last_page
        )
        return AiReadResult(pages=pages, usage=self._usage(response))

    async def _create(self, request: dict[str, Any]) -> Any:
        try:
            return await self._client.responses.create(**request)
        except BadRequestError as exc:
            # Modelos sin razonamiento rechazan el parámetro: se repite sin él.
            if "reasoning" not in str(getattr(exc, "body", "") or exc):
                raise
            request = {key: value for key, value in request.items() if key != "reasoning"}
            return await self._client.responses.create(**request)

    def _usage(self, response: Any) -> AiReadUsage:
        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        # `output_tokens` ya incluye los de razonamiento.
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        cost = None
        if self._price is not None:
            cost = (input_tokens * self._price.input + output_tokens * self._price.output) / 1e6
        return AiReadUsage(input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=cost)
