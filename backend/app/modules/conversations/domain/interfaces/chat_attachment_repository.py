from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from app.modules.conversations.domain.entities import ChatAttachment
from app.modules.conversations.domain.value_objects import ConversationOwner


class ChatAttachmentRepository(ABC):
    @abstractmethod
    async def add(self, attachment: ChatAttachment, content: bytes) -> ChatAttachment:
        """Guarda la metadata y los bytes (en tabla aparte) en la misma transacción."""

    @abstractmethod
    async def get(self, attachment_id: UUID) -> ChatAttachment | None:
        """Solo metadata."""

    @abstractmethod
    async def get_content(self, attachment_id: UUID) -> bytes | None: ...

    @abstractmethod
    async def delete_stale_unlinked(self, owner: ConversationOwner, older_than: datetime) -> int:
        """Borra los adjuntos subidos por `owner` que nunca se enviaron en un
        mensaje (`message_id IS NULL`) y son anteriores a `older_than`.
        Devuelve cuántos borró."""
