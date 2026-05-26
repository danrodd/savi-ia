from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class CreateConversationDTO:
    title: str | None
    user_id: UUID | None


@dataclass(frozen=True)
class ConversationDTO:
    id: UUID
    user_id: UUID | None
    title: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class MessageDTO:
    id: UUID
    conversation_id: UUID
    role: str
    content: str
    created_at: datetime


@dataclass(frozen=True)
class ConversationWithMessagesDTO:
    conversation: ConversationDTO
    messages: list[MessageDTO]
