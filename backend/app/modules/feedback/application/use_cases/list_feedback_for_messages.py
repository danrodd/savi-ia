from collections.abc import Sequence
from uuid import UUID

from app.modules.conversations.domain.value_objects import ConversationOwner
from app.modules.feedback.domain.entities import MessageFeedback
from app.modules.feedback.domain.interfaces import FeedbackRepository


class ListFeedbackForMessagesUseCase:
    """Calificaciones del usuario sobre un conjunto de mensajes."""

    def __init__(self, repository: FeedbackRepository) -> None:
        self._repository = repository

    async def execute(
        self, message_ids: Sequence[UUID], *, owner: ConversationOwner
    ) -> dict[UUID, MessageFeedback]:
        return await self._repository.list_for_messages(
            message_ids, user_id=owner.user_id, owner_erp_database_id=owner.erp_database_id
        )
