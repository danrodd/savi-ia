from app.modules.conversations.application.dtos import ConversationDTO, CreateConversationDTO
from app.modules.conversations.application.mappers import ConversationMapper
from app.modules.conversations.domain.entities import Conversation
from app.modules.conversations.domain.interfaces import ConversationRepository


class CreateConversationUseCase:
    def __init__(self, repository: ConversationRepository):
        self._repository = repository

    async def execute(self, dto: CreateConversationDTO) -> ConversationDTO:
        conversation = Conversation(
            user_id=dto.user_id,
            erp_database_id=dto.erp_database_id,
            owner_erp_database_id=dto.owner_erp_database_id,
            title=dto.title.strip() if dto.title else "Nueva conversación",
        )
        saved = await self._repository.save(conversation)
        return ConversationMapper.to_dto(saved)
