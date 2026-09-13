from typing import Any

from app.modules.conversations.domain.entities import Conversation, Message, MessageRole
from app.modules.conversations.domain.value_objects import (
    MessageFinishReason,
    TokenUsage,
    ToolInvocation,
)
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
            erp_database_id=model.erp_database_id,
            owner_erp_database_id=model.owner_erp_database_id,
            title=model.title,
            title_locked=model.title_locked,
            created_at=model.created_at,
            updated_at=model.updated_at,
            deleted_at=model.deleted_at,
        )

    @staticmethod
    def to_model(entity: Conversation) -> ConversationModel:
        return ConversationModel(
            id=entity.id,
            user_id=entity.user_id,
            erp_database_id=entity.erp_database_id,
            owner_erp_database_id=entity.owner_erp_database_id,
            title=entity.title,
            title_locked=entity.title_locked,
            deleted_at=entity.deleted_at,
        )

    @staticmethod
    def message_to_entity(model: MessageModel) -> Message:
        raw_tools = model.tool_invocations or []
        tools = [ToolInvocation.from_dict(t) for t in raw_tools]
        usage = TokenUsage.from_dict(model.usage) if model.usage else None
        finish = (
            MessageFinishReason(model.finish_reason) if model.finish_reason else None
        )
        return Message(
            id=model.id,
            conversation_id=model.conversation_id,
            role=MessageRole(model.role),
            content=model.content,
            finish_reason=finish,
            tool_invocations=tools,
            usage=usage,
            cost_usd=model.cost_usd,
            superseded_at=model.superseded_at,
            superseded_by_id=model.superseded_by_id,
            created_at=model.created_at,
        )

    @staticmethod
    def message_to_model(entity: Message) -> MessageModel:
        tool_payload: list[dict[str, Any]] | None = (
            [t.to_dict() for t in entity.tool_invocations]
            if entity.tool_invocations
            else None
        )
        usage_payload: dict[str, Any] | None = (
            entity.usage.to_dict() if entity.usage else None
        )
        return MessageModel(
            id=entity.id,
            conversation_id=entity.conversation_id,
            role=entity.role.value,
            content=entity.content,
            finish_reason=entity.finish_reason.value if entity.finish_reason else None,
            tool_invocations=tool_payload,
            usage=usage_payload,
            cost_usd=entity.cost_usd,
            superseded_at=entity.superseded_at,
            superseded_by_id=entity.superseded_by_id,
        )
