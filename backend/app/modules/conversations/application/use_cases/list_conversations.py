from app.modules.conversations.application.dtos import ConversationDTO
from app.modules.conversations.application.mappers import ConversationMapper
from app.modules.conversations.domain.interfaces import ConversationRepository


class ListConversationsUseCase:
    def __init__(self, repository: ConversationRepository):
        self._repository = repository

    async def execute(
        self,
        user_id: int | None,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ConversationDTO]:
        conversations = await self._repository.list_for_user(
            user_id,
            limit=limit,
            offset=offset,
        )
        return [ConversationMapper.to_dto(c) for c in conversations]
