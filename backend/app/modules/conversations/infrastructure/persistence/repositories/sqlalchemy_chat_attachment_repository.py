from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.conversations.domain.entities import ChatAttachment
from app.modules.conversations.domain.interfaces import ChatAttachmentRepository
from app.modules.conversations.domain.value_objects import ConversationOwner
from app.modules.conversations.infrastructure.persistence.mappers import ConversationOrmMapper
from app.modules.conversations.infrastructure.persistence.models import (
    ChatAttachmentBlobModel,
    ChatAttachmentModel,
)


class SqlAlchemyChatAttachmentRepository(ChatAttachmentRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, attachment: ChatAttachment, content: bytes) -> ChatAttachment:
        model = ConversationOrmMapper.attachment_to_model(attachment)
        self._session.add(model)
        # La fila tiene que existir antes que su blob (FK).
        await self._session.flush()
        self._session.add(ChatAttachmentBlobModel(attachment_id=attachment.id, content=content))
        await self._session.flush()
        return attachment

    async def get(self, attachment_id: UUID) -> ChatAttachment | None:
        result = await self._session.execute(
            select(ChatAttachmentModel).where(ChatAttachmentModel.id == attachment_id)
        )
        model = result.scalar_one_or_none()
        return ConversationOrmMapper.attachment_to_entity(model) if model else None

    async def get_content(self, attachment_id: UUID) -> bytes | None:
        result = await self._session.execute(
            select(ChatAttachmentBlobModel.content).where(
                ChatAttachmentBlobModel.attachment_id == attachment_id
            )
        )
        return result.scalar_one_or_none()

    async def delete_stale_unlinked(self, owner: ConversationOwner, older_than: datetime) -> int:
        stale = select(ChatAttachmentModel.id).where(
            ChatAttachmentModel.user_id == owner.user_id,
            ChatAttachmentModel.owner_erp_database_id == owner.erp_database_id,
            ChatAttachmentModel.message_id.is_(None),
            ChatAttachmentModel.created_at < older_than,
        )
        ids = list((await self._session.execute(stale)).scalars().all())
        if not ids:
            return 0
        # Los bytes primero, sin depender de que el motor aplique el
        # ON DELETE CASCADE.
        await self._session.execute(
            delete(ChatAttachmentBlobModel).where(ChatAttachmentBlobModel.attachment_id.in_(ids))
        )
        await self._session.execute(
            delete(ChatAttachmentModel).where(
                ChatAttachmentModel.id.in_(ids),
                ChatAttachmentModel.message_id.is_(None),
            )
        )
        return len(ids)
