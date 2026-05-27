from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from app.modules.conversations.domain.value_objects import (
    MessageFinishReason,
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
    created_at: datetime = field(default_factory=_utc_now)
