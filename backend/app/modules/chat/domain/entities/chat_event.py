from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ChatEventType(StrEnum):
    TEXT_DELTA = "text_delta"
    THINKING_DELTA = "thinking_delta"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    TITLE_UPDATE = "title_update"
    SUPERSEDED = "superseded"
    SOURCES = "sources"
    DONE = "done"
    ERROR = "error"


@dataclass(slots=True)
class TextDeltaEvent:
    text: str
    type: ChatEventType = ChatEventType.TEXT_DELTA


@dataclass(slots=True)
class ThinkingDeltaEvent:
    text: str
    type: ChatEventType = ChatEventType.THINKING_DELTA


@dataclass(slots=True)
class ToolUseEvent:
    id: str
    name: str
    input: dict[str, Any]
    type: ChatEventType = ChatEventType.TOOL_USE


@dataclass(slots=True)
class ToolResultEvent:
    tool_use_id: str
    is_error: bool
    type: ChatEventType = ChatEventType.TOOL_RESULT


@dataclass(slots=True)
class TitleUpdateEvent:
    title: str
    type: ChatEventType = ChatEventType.TITLE_UPDATE


@dataclass(slots=True)
class SupersededEvent:
    """Lista de IDs que pasan a ser superseded al iniciar este turno.

    El frontend los oculta del hilo activo. Aún quedan en BD para
    auditoría/trazabilidad y se devuelven cuando el cliente pide
    `GET /conversations/{id}?include_superseded=true`.
    """

    message_ids: list[str]
    type: ChatEventType = ChatEventType.SUPERSEDED


@dataclass(slots=True)
class SourcesEvent:
    """Documentos de la empresa citados en la respuesta.

    Llega justo antes de `done`, solo si la respuesta citó referencias
    válidas. Cada fuente es `MessageSource.to_dict()`.
    """

    sources: list[dict[str, Any]]
    type: ChatEventType = ChatEventType.SOURCES


@dataclass(slots=True)
class DoneEvent:
    usage: dict[str, Any] | None = None
    cost_usd: float | None = None
    finish_reason: str = "complete"
    provider: str | None = None
    model: str | None = None
    type: ChatEventType = ChatEventType.DONE


@dataclass(slots=True)
class ErrorEvent:
    message: str
    type: ChatEventType = ChatEventType.ERROR


ChatEvent = (
    TextDeltaEvent
    | ThinkingDeltaEvent
    | ToolUseEvent
    | ToolResultEvent
    | TitleUpdateEvent
    | SupersededEvent
    | SourcesEvent
    | DoneEvent
    | ErrorEvent
)
