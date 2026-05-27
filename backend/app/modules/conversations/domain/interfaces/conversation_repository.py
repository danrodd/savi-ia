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
    async def update_title(
        self,
        conversation_id: UUID,
        new_title: str,
        *,
        respect_lock: bool = True,
        lock: bool = False,
    ) -> str | None:
        """Cambia el título de una conversación.

        - `respect_lock`: si True y la conversación tiene `title_locked`,
          NO se hace nada y devuelve None. Lo usan los autotítulos.
        - `lock`: si True, marca `title_locked=true` tras actualizar.
          Lo usa el endpoint manual de renombre.

        Devuelve el título efectivamente aplicado, o None si no se aplicó
        (por lock o por conversación inexistente).
        """

    @abstractmethod
    async def add_message(self, message: Message) -> Message: ...

    @abstractmethod
    async def list_messages(self, conversation_id: UUID) -> list[Message]: ...
