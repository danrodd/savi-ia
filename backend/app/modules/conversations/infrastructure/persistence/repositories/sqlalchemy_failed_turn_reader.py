from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.conversations.domain.interfaces.failed_turn_reader import (
    FailedTurn,
    FailedTurnReader,
)
from app.modules.conversations.domain.value_objects import MessageFinishReason
from app.modules.conversations.infrastructure.persistence.models.conversation_model import (
    ConversationModel,
    MessageModel,
)

# Tools que consultan el ERP: las que cuentan para entender qué alcanzó a hacer.
_ERP_TOOLS = ("consultar_datos", "consultar_libre")


def _erp_queries(tools: list[dict[str, Any]] | None) -> int:
    return sum(1 for tool in tools or [] if tool.get("name") in _ERP_TOOLS)


class SqlAlchemyFailedTurnReader(FailedTurnReader):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def recent(self, owner_erp_database_id: UUID, limit: int) -> list[FailedTurn]:
        stmt = (
            select(MessageModel, ConversationModel.title, ConversationModel.user_id)
            .join(ConversationModel, ConversationModel.id == MessageModel.conversation_id)
            .where(
                MessageModel.finish_reason == MessageFinishReason.ERROR.value,
                ConversationModel.owner_erp_database_id == owner_erp_database_id,
            )
            .order_by(MessageModel.created_at.desc())
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            FailedTurn(
                message_id=message.id,
                conversation_id=message.conversation_id,
                conversation_title=title,
                user_id=user_id,
                created_at=message.created_at,
                error_code=message.error_code,
                error_message=message.error_message,
                support_code=message.support_code,
                provider=message.provider,
                model=message.model,
                erp_queries=_erp_queries(message.tool_invocations),
            )
            for message, title, user_id in rows
        ]
