from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

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
    tool_invocations: list[ToolInvocation] = field(
        default_factory=_empty_tool_invocations
    )
    usage: TokenUsage | None = None
    cost_usd: Decimal | None = None
    provider: str | None = None
    model: str | None = None
    # Documentos de la empresa citados. Vacío si la respuesta no citó ninguno.
    sources: list[MessageSource] = field(default_factory=list[MessageSource])
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
