from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.modules.conversations.domain.value_objects import (
    MessageFinishReason,
    TokenUsage,
    ToolInvocation,
)


@dataclass(frozen=True)
class CreateConversationDTO:
    title: str | None
    user_id: UUID | None


@dataclass(frozen=True)
class ConversationDTO:
    id: UUID
    user_id: UUID | None
    title: str
    title_locked: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class MessageDTO:
    id: UUID
    conversation_id: UUID
    role: str
    content: str
    created_at: datetime
    tool_invocations: list[ToolInvocation]
    finish_reason: MessageFinishReason | None = None
    usage: TokenUsage | None = None
    cost_usd: Decimal | None = None
    superseded_at: datetime | None = None
    superseded_by_id: UUID | None = None


@dataclass(frozen=True)
class ConversationWithMessagesDTO:
    conversation: ConversationDTO
    messages: list[MessageDTO]
