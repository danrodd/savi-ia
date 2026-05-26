from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.conversations.domain.entities import Conversation, Message
from app.modules.conversations.domain.interfaces import ConversationRepository
from app.modules.conversations.infrastructure.persistence.mappers import ConversationOrmMapper
from app.modules.conversations.infrastructure.persistence.models import (
    ConversationModel,
    MessageModel,
)


class SqlAlchemyConversationRepository(ConversationRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def save(self, conversation: Conversation) -> Conversation:
        model = ConversationOrmMapper.to_model(conversation)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return ConversationOrmMapper.to_entity(model)

    async def get_by_id(self, conversation_id: UUID) -> Conversation | None:
        stmt = select(ConversationModel).where(ConversationModel.id == conversation_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return ConversationOrmMapper.to_entity(model)

    async def list_for_user(
        self,
        user_id: UUID | None,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Conversation]:
        stmt = select(ConversationModel).where(ConversationModel.deleted_at.is_(None))
        if user_id is not None:
            stmt = stmt.where(ConversationModel.user_id == user_id)
        else:
            stmt = stmt.where(ConversationModel.user_id.is_(None))
        stmt = stmt.order_by(ConversationModel.updated_at.desc()).limit(limit).offset(offset)

        result = await self._session.execute(stmt)
        return [ConversationOrmMapper.to_entity(m) for m in result.scalars().all()]

    async def add_message(self, message: Message) -> Message:
        model = ConversationOrmMapper.message_to_model(message)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return ConversationOrmMapper.message_to_entity(model)

    async def list_messages(self, conversation_id: UUID) -> list[Message]:
        stmt = (
            select(MessageModel)
            .where(MessageModel.conversation_id == conversation_id)
            .order_by(MessageModel.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return [ConversationOrmMapper.message_to_entity(m) for m in result.scalars().all()]
