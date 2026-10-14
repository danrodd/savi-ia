from uuid import UUID

from app.modules.conversations.domain.value_objects import ConversationOwner
from app.modules.feedback.application.use_cases.set_message_feedback import resolve_owned_target
from app.modules.feedback.domain.interfaces import FeedbackRepository


class ClearMessageFeedbackUseCase:
    """Quita la calificación propia. Idempotente: sin calificación, no hace nada."""

    def __init__(self, repository: FeedbackRepository) -> None:
        self._repository = repository

    async def execute(
        self, *, conversation_id: UUID, message_id: UUID, owner: ConversationOwner
    ) -> None:
        await resolve_owned_target(
            self._repository,
            conversation_id=conversation_id,
            message_id=message_id,
            owner=owner,
        )
        await self._repository.delete(
            message_id, user_id=owner.user_id, owner_erp_database_id=owner.erp_database_id
        )
