from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, update
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
        user_id: int | None,
        *,
        erp_database_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Conversation]:
        stmt = select(ConversationModel).where(ConversationModel.deleted_at.is_(None))
        if user_id is not None:
            stmt = stmt.where(ConversationModel.user_id == user_id)
            # Scope por base: el `idUsuario` se repite entre clientes, así
            # que sin este filtro el usuario 5 del cliente B vería las
            # conversaciones del usuario 5 del cliente A.
            if erp_database_id is not None:
                stmt = stmt.where(
                    ConversationModel.erp_database_id == erp_database_id
                )
        else:
            stmt = stmt.where(ConversationModel.user_id.is_(None))
        stmt = stmt.order_by(ConversationModel.updated_at.desc()).limit(limit).offset(offset)

        result = await self._session.execute(stmt)
        return [ConversationOrmMapper.to_entity(m) for m in result.scalars().all()]

    async def update_title(
        self,
        conversation_id: UUID,
        new_title: str,
        *,
        respect_lock: bool = True,
        lock: bool = False,
    ) -> str | None:
        clean = new_title.strip()[:200]
        if not clean:
            return None
        stmt = update(ConversationModel).where(
            ConversationModel.id == conversation_id,
            ConversationModel.deleted_at.is_(None),
        )
        if respect_lock:
            stmt = stmt.where(ConversationModel.title_locked.is_(False))
        values: dict[str, str | bool] = {"title": clean}
        if lock:
            values["title_locked"] = True
        stmt = stmt.values(**values).returning(ConversationModel.id)
        result = await self._session.execute(stmt)
        returned_id = result.scalar_one_or_none()
        return clean if returned_id is not None else None

    async def soft_delete(self, conversation_id: UUID) -> bool:
        # COALESCE garantiza idempotencia: si ya estaba eliminada, deja
        # el `deleted_at` original; si era NULL, asigna ahora. RETURNING
        # nos dice si la fila existía.
        stmt = (
            update(ConversationModel)
            .where(ConversationModel.id == conversation_id)
            .values(
                deleted_at=func.coalesce(
                    ConversationModel.deleted_at, func.now()
                )
            )
            .returning(ConversationModel.id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def add_message(self, message: Message) -> Message:
        model = ConversationOrmMapper.message_to_model(message)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return ConversationOrmMapper.message_to_entity(model)

    async def list_messages(
        self,
        conversation_id: UUID,
        *,
        include_superseded: bool = False,
    ) -> list[Message]:
        stmt = select(MessageModel).where(
            MessageModel.conversation_id == conversation_id
        )
        if not include_superseded:
            stmt = stmt.where(MessageModel.superseded_at.is_(None))
        stmt = stmt.order_by(MessageModel.created_at.asc())
        result = await self._session.execute(stmt)
        return [ConversationOrmMapper.message_to_entity(m) for m in result.scalars().all()]

    async def get_last_active_message(
        self,
        conversation_id: UUID,
    ) -> Message | None:
        stmt = (
            select(MessageModel)
            .where(
                MessageModel.conversation_id == conversation_id,
                MessageModel.superseded_at.is_(None),
            )
            .order_by(MessageModel.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return ConversationOrmMapper.message_to_entity(model) if model else None

    async def supersede_messages(
        self,
        message_ids: list[UUID],
        *,
        superseded_by_id: UUID | None = None,
    ) -> None:
        if not message_ids:
            return
        stmt = (
            update(MessageModel)
            .where(
                MessageModel.id.in_(message_ids),
                MessageModel.superseded_at.is_(None),
            )
            .values(
                superseded_at=datetime.now(UTC),
                superseded_by_id=superseded_by_id,
            )
        )
        await self._session.execute(stmt)
