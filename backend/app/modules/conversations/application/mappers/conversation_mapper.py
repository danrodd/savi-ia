from app.modules.conversations.application.dtos import ConversationDTO, MessageDTO
from app.modules.conversations.domain.entities import Conversation, Message


class ConversationMapper:
    @staticmethod
    def to_dto(entity: Conversation) -> ConversationDTO:
        return ConversationDTO(
            id=entity.id,
            user_id=entity.user_id,
            erp_database_id=entity.erp_database_id,
            owner_erp_database_id=entity.owner_erp_database_id,
            title=entity.title,
            title_locked=entity.title_locked,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    @staticmethod
    def message_to_dto(entity: Message) -> MessageDTO:
        return MessageDTO(
            id=entity.id,
            conversation_id=entity.conversation_id,
            role=entity.role.value,
            content=entity.content,
            created_at=entity.created_at,
            tool_invocations=list(entity.tool_invocations),
            finish_reason=entity.finish_reason,
            usage=entity.usage,
            cost_usd=entity.cost_usd,
            superseded_at=entity.superseded_at,
            superseded_by_id=entity.superseded_by_id,
        )
