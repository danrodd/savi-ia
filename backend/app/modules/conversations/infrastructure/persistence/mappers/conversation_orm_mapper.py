from app.modules.conversations.domain.entities import Conversation, Message, MessageRole
from app.modules.conversations.infrastructure.persistence.models import (
    ConversationModel,
    MessageModel,
)


class ConversationOrmMapper:
    @staticmethod
    def to_entity(model: ConversationModel) -> Conversation:
        return Conversation(
            id=model.id,
            user_id=model.user_id,
            title=model.title,
            created_at=model.created_at,
            updated_at=model.updated_at,
            deleted_at=model.deleted_at,
        )

    @staticmethod
    def to_model(entity: Conversation) -> ConversationModel:
        return ConversationModel(
            id=entity.id,
            user_id=entity.user_id,
            title=entity.title,
            deleted_at=entity.deleted_at,
        )

    @staticmethod
    def message_to_entity(model: MessageModel) -> Message:
        return Message(
            id=model.id,
            conversation_id=model.conversation_id,
            role=MessageRole(model.role),
            content=model.content,
            created_at=model.created_at,
        )

    @staticmethod
    def message_to_model(entity: Message) -> MessageModel:
        return MessageModel(
            id=entity.id,
            conversation_id=entity.conversation_id,
            role=entity.role.value,
            content=entity.content,
        )
