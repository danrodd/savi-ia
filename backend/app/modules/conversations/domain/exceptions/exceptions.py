from uuid import UUID

from app.shared.exceptions.base import NotFoundError


class ConversationNotFoundError(NotFoundError):
    def __init__(self, conversation_id: UUID):
        super().__init__(f"Conversación {conversation_id} no encontrada")
        self.conversation_id = conversation_id
