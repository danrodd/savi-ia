from uuid import UUID

from app.modules.conversations.application.dtos import ConversationWithMessagesDTO
from app.modules.conversations.application.mappers import ConversationMapper
from app.modules.conversations.domain.exceptions import ConversationNotFoundError
from app.modules.conversations.domain.interfaces import ConversationRepository


class GetConversationWithMessagesUseCase:
    def __init__(self, repository: ConversationRepository):
        self._repository = repository

    async def execute(
        self,
        conversation_id: UUID,
        *,
        include_superseded: bool = False,
    ) -> ConversationWithMessagesDTO:
        conversation = await self._repository.get_by_id(conversation_id)
        if conversation is None or conversation.is_deleted:
            raise ConversationNotFoundError(conversation_id)

        messages = await self._repository.list_messages(
            conversation_id,
            include_superseded=include_superseded,
        )

        return ConversationWithMessagesDTO(
            conversation=ConversationMapper.to_dto(conversation),
            messages=[ConversationMapper.message_to_dto(m) for m in messages],
        )
