from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.conversations.application.dtos import (
    ConversationDTO,
    ConversationWithMessagesDTO,
    MessageDTO,
)


def _empty_input() -> dict[str, Any]:
    return {}


def _empty_tool_invocations() -> list["ToolInvocationResponse"]:
    return []


class ToolInvocationResponse(BaseModel):
    id: str
    name: str
    input: dict[str, Any] = Field(default_factory=_empty_input)
    status: str


class TokenUsageResponse(BaseModel):
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int


class ConversationResponse(BaseModel):
    id: UUID
    user_id: UUID | None
    title: str
    title_locked: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_dto(cls, dto: ConversationDTO) -> "ConversationResponse":
        return cls(
            id=dto.id,
            user_id=dto.user_id,
            title=dto.title,
            title_locked=dto.title_locked,
            created_at=dto.created_at,
            updated_at=dto.updated_at,
        )


class MessageResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    role: str
    content: str
    created_at: datetime
    finish_reason: str | None = None
    tool_invocations: list[ToolInvocationResponse] = Field(
        default_factory=_empty_tool_invocations
    )
    usage: TokenUsageResponse | None = None
    cost_usd: Decimal | None = None
    superseded_at: datetime | None = None
    superseded_by_id: UUID | None = None

    @classmethod
    def from_dto(cls, dto: MessageDTO) -> "MessageResponse":
        return cls(
            id=dto.id,
            conversation_id=dto.conversation_id,
            role=dto.role,
            content=dto.content,
            created_at=dto.created_at,
            finish_reason=dto.finish_reason.value if dto.finish_reason else None,
            tool_invocations=[
                ToolInvocationResponse(
                    id=t.id,
                    name=t.name,
                    input=t.input,
                    status=t.status.value,
                )
                for t in dto.tool_invocations
            ],
            usage=TokenUsageResponse(**dto.usage.to_dict()) if dto.usage else None,
            cost_usd=dto.cost_usd,
            superseded_at=dto.superseded_at,
            superseded_by_id=dto.superseded_by_id,
        )


class ConversationWithMessagesResponse(BaseModel):
    conversation: ConversationResponse
    messages: list[MessageResponse]

    @classmethod
    def from_dto(cls, dto: ConversationWithMessagesDTO) -> "ConversationWithMessagesResponse":
        return cls(
            conversation=ConversationResponse.from_dto(dto.conversation),
            messages=[MessageResponse.from_dto(m) for m in dto.messages],
        )
