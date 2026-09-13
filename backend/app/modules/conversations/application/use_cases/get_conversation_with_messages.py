from uuid import UUID

from app.modules.conversations.application.dtos import ConversationWithMessagesDTO
from app.modules.conversations.application.mappers import ConversationMapper
from app.modules.conversations.domain.exceptions import ConversationNotFoundError
from app.modules.conversations.domain.interfaces import ConversationRepository
from app.modules.conversations.domain.value_objects import ConversationOwner


class GetConversationWithMessagesUseCase:
    def __init__(self, repository: ConversationRepository):
        self._repository = repository

    async def execute(
        self,
        conversation_id: UUID,
        *,
        expected_owner: ConversationOwner | None = None,
        include_superseded: bool = False,
    ) -> ConversationWithMessagesDTO:
        conversation = await self._repository.get_by_id(conversation_id)
        if conversation is None or conversation.is_deleted:
            raise ConversationNotFoundError(conversation_id)
        # Ownership: si se pasa el owner esperado y no coincide, tratamos
        # como "no existe" — no le damos pistas al atacante sobre la
        # existencia de conversaciones ajenas.
        if expected_owner is not None and not expected_owner.owns(
            conversation.user_id, conversation.owner_erp_database_id
        ):
            raise ConversationNotFoundError(conversation_id)

        messages = await self._repository.list_messages(
            conversation_id,
            include_superseded=include_superseded,
        )

        return ConversationWithMessagesDTO(
            conversation=ConversationMapper.to_dto(conversation),
            messages=[ConversationMapper.message_to_dto(m) for m in messages],
        )
