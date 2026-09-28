"""Lectura de PDF con Claude por el Agent SDK.

Verificado en el spike (`docs/company_knowledge/spike-lectura-ia.md`) con la
sesión local: el SDK acepta el bloque `document` en modo de entrada en
streaming y devuelve el esquema en `ResultMessage.structured_output`. Mismo
aislamiento que el generador de títulos: sin herramientas ni configuración
del equipo. El costo es el que informa el SDK (precio de lista).
"""

import base64
from collections.abc import AsyncIterator
from typing import Any

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, query

from app.infrastructure.claude_cli import ISOLATED_CLI_OPTIONS, resolve_cli_path
from app.infrastructure.claude_env import build_claude_env
from app.modules.chat.infrastructure.llm.claude.mcp_adapter import BUILTIN_TOOLS
from app.modules.company_knowledge.domain.entities.page_reading import (
    AiReadResult,
    AiReadUsage,
)
from app.modules.company_knowledge.domain.exceptions import AiReadingError
from app.modules.company_knowledge.domain.interfaces import PdfPageReader
from app.modules.company_knowledge.domain.value_objects import AiReadErrorCode
from app.modules.company_knowledge.infrastructure.ai_reading.errors import to_reading_error
from app.modules.company_knowledge.infrastructure.ai_reading.prompt import (
    SYSTEM_PROMPT,
    user_message,
)
from app.modules.company_knowledge.infrastructure.ai_reading.schema import (
    TRANSCRIPTION_SCHEMA,
    parse_transcription,
)

# La salida estructurada del SDK usa un turno interno además del de la
# respuesta; con 1 cortaba antes de devolver el JSON.
_MAX_TURNS = 3


class ClaudePdfReader(PdfPageReader):
    def __init__(
        self,
        *,
        model: str,
        credential_kind: str,
        credential: str | None,
        git_bash_path: str = "",
    ) -> None:
        self._model = model
        self._credential_kind = credential_kind
        self._credential = credential
        self._git_bash_path = git_bash_path

    @property
    def provider(self) -> str:
        return "claude"

    @property
    def model(self) -> str:
        return self._model

    async def read(
        self, segment: bytes, first_page: int, last_page: int, *, attempt: int = 0
    ) -> AiReadResult:
        options = ClaudeAgentOptions(
            model=self._model,
            system_prompt=SYSTEM_PROMPT,
            # El PDF es contenido del cliente: sin `tools=[]` el CLI traería
            # Bash, Read y compañía, aprobadas por `bypassPermissions`.
            tools=[],
            allowed_tools=[],
            disallowed_tools=list(BUILTIN_TOOLS),
            permission_mode="bypassPermissions",
            max_turns=_MAX_TURNS,
            # Transcribir no necesita razonar: sin esto tarda más y cuesta más
            # con la misma calidad (spike).
            thinking={"type": "disabled"},
            output_format={"type": "json_schema", "schema": TRANSCRIPTION_SCHEMA},
            cli_path=resolve_cli_path(),
            env=build_claude_env(
                credential_kind=self._credential_kind,
                credential=self._credential,
                git_bash_path=self._git_bash_path,
            ),
            **ISOLATED_CLI_OPTIONS,
        )
        prompt = _prompt_stream(segment, user_message(first_page, last_page, retry=attempt > 0))
        result: ResultMessage | None = None
        rejection: str | None = None
        try:
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, AssistantMessage) and message.error is not None:
                    rejection = message.error
                if isinstance(message, ResultMessage):
                    result = message
        except Exception as exc:  # noqa: BLE001
            raise to_reading_error(exc) from exc

        if rejection is not None:
            raise _rejection_error(rejection)
        if result is None or result.is_error:
            raise AiReadingError(AiReadErrorCode.PROVIDER_ERROR, retryable=True)
        raw: Any = (
            result.structured_output if result.structured_output is not None else result.result
        )
        if raw is None:
            raise AiReadingError(AiReadErrorCode.INVALID_JSON, retryable=True)
        pages = parse_transcription(raw, first_page, last_page)
        return AiReadResult(pages=pages, usage=_usage(result))


async def _prompt_stream(segment: bytes, text: str) -> AsyncIterator[dict[str, Any]]:
    data = base64.b64encode(segment).decode("ascii")
    yield {
        "type": "user",
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {"type": "base64", "media_type": "application/pdf", "data": data},
                },
                {"type": "text", "text": text},
            ],
        },
        "parent_tool_use_id": None,
        "session_id": "company-document",
    }


def _rejection_error(kind: str) -> AiReadingError:
    """El CLI no lanza excepción cuando Anthropic rechaza el pedido: lo marca en
    `AssistantMessage.error`. Sin saldo, reintentar solo demora el aviso."""
    if kind == "billing_error":
        return AiReadingError(AiReadErrorCode.NO_CREDITS, retryable=False)
    if kind == "authentication_failed":
        return AiReadingError(AiReadErrorCode.UNAVAILABLE, retryable=False)
    if kind == "rate_limit":
        return AiReadingError(AiReadErrorCode.RATE_LIMITED, retryable=True)
    return AiReadingError(AiReadErrorCode.PROVIDER_ERROR, retryable=True)


def _usage(result: ResultMessage) -> AiReadUsage:
    usage: dict[str, Any] = result.usage or {}

    def tokens(key: str) -> int:
        value = usage.get(key, 0)
        return value if isinstance(value, int) else 0

    return AiReadUsage(
        input_tokens=(
            tokens("input_tokens")
            + tokens("cache_creation_input_tokens")
            + tokens("cache_read_input_tokens")
        ),
        output_tokens=tokens("output_tokens"),
        cost_usd=result.total_cost_usd,
    )
