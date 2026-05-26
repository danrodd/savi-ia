from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.modules.conversations.application.dtos import (
    ConversationDTO,
    ConversationWithMessagesDTO,
    MessageDTO,
)


class ConversationResponse(BaseModel):
    id: UUID
    user_id: UUID | None
    title: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_dto(cls, dto: ConversationDTO) -> "ConversationResponse":
        return cls(
            id=dto.id,
            user_id=dto.user_id,
            title=dto.title,
            created_at=dto.created_at,
            updated_at=dto.updated_at,
        )


class MessageResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    role: str
    content: str
    created_at: datetime

    @classmethod
    def from_dto(cls, dto: MessageDTO) -> "MessageResponse":
        return cls(
            id=dto.id,
            conversation_id=dto.conversation_id,
            role=dto.role,
            content=dto.content,
            created_at=dto.created_at,
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
