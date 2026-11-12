from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from app.modules.conversations.domain.entities.chat_attachment import ChatAttachment
from app.modules.conversations.domain.value_objects import (
    MessageFinishReason,
    MessageSource,
    TokenUsage,
    ToolInvocation,
)


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


def _empty_tool_invocations() -> list[ToolInvocation]:
    return []


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class Message:
    id: UUID = field(default_factory=uuid4)
    conversation_id: UUID = field(default_factory=uuid4)
    role: MessageRole = MessageRole.USER
    content: str = ""
    finish_reason: MessageFinishReason | None = None
    tool_invocations: list[ToolInvocation] = field(default_factory=_empty_tool_invocations)
    usage: TokenUsage | None = None
    cost_usd: Decimal | None = None
    provider: str | None = None
    model: str | None = None
    # Documentos de la empresa citados. Vacío si la respuesta no citó ninguno.
    sources: list[MessageSource] = field(default_factory=list[MessageSource])
    # Turno que terminó en error: la categoría (`provider_busy`,
    # `internal_error`...), el texto que vio el usuario y el código de soporte
    # que también quedó en el log. `None` si el turno no falló.
    error_code: str | None = None
    error_message: str | None = None
    support_code: str | None = None
    # Conjuntos de resultados que acompañan a la respuesta (id, título, filas):
    # el chat los muestra con su vista previa y su botón Exportar.
    data_tables: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    # Archivos que SAVI generó para la respuesta (Excel, PDF, CSV, Word).
    files: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    # Imágenes adjuntas (solo metadata). Solo los mensajes del usuario las tienen.
    attachments: list[ChatAttachment] = field(default_factory=list[ChatAttachment])
    # Revisiones: si `superseded_at` está set, este mensaje ya no es parte
    # del hilo activo de la conversación. `superseded_by_id` apunta al
    # mensaje que lo reemplazó (puede ser None si el reemplazo aún no se
    # persistió — caso del assistant viejo justo después de `regenerate`).
    superseded_at: datetime | None = None
    superseded_by_id: UUID | None = None
    created_at: datetime = field(default_factory=_utc_now)

    @property
    def is_active(self) -> bool:
        return self.superseded_at is None
