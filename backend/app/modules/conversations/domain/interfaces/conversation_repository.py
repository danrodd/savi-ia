from abc import ABC, abstractmethod
from uuid import UUID

from app.modules.conversations.domain.entities import Conversation, Message


class ConversationRepository(ABC):
    @abstractmethod
    async def save(self, conversation: Conversation) -> Conversation: ...

    @abstractmethod
    async def get_by_id(self, conversation_id: UUID) -> Conversation | None: ...

    @abstractmethod
    async def list_for_user(
        self,
        user_id: UUID | None,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Conversation]: ...

    @abstractmethod
    async def add_message(self, message: Message) -> Message: ...

    @abstractmethod
    async def list_messages(self, conversation_id: UUID) -> list[Message]: ...
