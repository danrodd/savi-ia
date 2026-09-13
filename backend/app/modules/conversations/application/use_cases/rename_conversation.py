from uuid import UUID

from app.modules.conversations.application.dtos import ConversationDTO
from app.modules.conversations.application.mappers import ConversationMapper
from app.modules.conversations.domain.exceptions import ConversationNotFoundError
from app.modules.conversations.domain.interfaces import ConversationRepository
from app.modules.conversations.domain.value_objects import ConversationOwner


class RenameConversationUseCase:
    """Renombra manualmente una conversación.

    Marca `title_locked=True` para que los autotítulos posteriores no
    sobrescriban la decisión del usuario.
    """

    def __init__(self, repository: ConversationRepository) -> None:
        self._repository = repository

    async def execute(
        self,
        conversation_id: UUID,
        new_title: str,
        *,
        expected_owner: ConversationOwner | None = None,
    ) -> ConversationDTO:
        conversation = await self._repository.get_by_id(conversation_id)
        if conversation is None or conversation.is_deleted:
            raise ConversationNotFoundError(conversation_id)
        if expected_owner is not None and not expected_owner.owns(
            conversation.user_id, conversation.owner_erp_database_id
        ):
            raise ConversationNotFoundError(conversation_id)

        applied = await self._repository.update_title(
            conversation_id,
            new_title,
            respect_lock=False,
            lock=True,
        )
        if applied is None:
            # No debería pasar: el caller ya validó existencia + min_length.
            raise ConversationNotFoundError(conversation_id)

        updated = await self._repository.get_by_id(conversation_id)
        assert updated is not None  # noqa: S101
        return ConversationMapper.to_dto(updated)
