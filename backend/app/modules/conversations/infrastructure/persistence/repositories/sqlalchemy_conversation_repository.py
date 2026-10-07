from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.conversations.domain.entities import ChatAttachment, Conversation, Message
from app.modules.conversations.domain.exceptions import ChatAttachmentUnavailableError
from app.modules.conversations.domain.interfaces import ConversationRepository
from app.modules.conversations.infrastructure.persistence.mappers import ConversationOrmMapper
from app.modules.conversations.infrastructure.persistence.models import (
    ChatAttachmentBlobModel,
    ChatAttachmentModel,
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
        owner_erp_database_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Conversation]:
        stmt = select(ConversationModel).where(ConversationModel.deleted_at.is_(None))
        if user_id is not None:
            stmt = stmt.where(ConversationModel.user_id == user_id)
            # Scope por identidad, NO por la base consultada: el `idUsuario`
            # se repite entre clientes, así que sin este filtro el usuario 5
            # del cliente B vería las conversaciones del usuario 5 del
            # cliente A. Con D10, además, filtrar por la base consultada
            # ocultaría las conversaciones que el propio dueño abrió contra
            # OTROS clientes.
            if owner_erp_database_id is not None:
                stmt = stmt.where(
                    ConversationModel.owner_erp_database_id == owner_erp_database_id
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

    async def add_user_message_with_attachments(
        self,
        message: Message,
        *,
        link_attachment_ids: Sequence[UUID] = (),
        copy_attachment_ids: Sequence[UUID] = (),
    ) -> Message:
        model = ConversationOrmMapper.message_to_model(message)
        self._session.add(model)
        await self._session.flush()

        if link_attachment_ids:
            # `message_id IS NULL` hace que dos mensajes no puedan quedarse
            # con la misma imagen: el que llega segundo no encuentra la fila.
            result = await self._session.execute(
                update(ChatAttachmentModel)
                .where(
                    ChatAttachmentModel.id.in_(link_attachment_ids),
                    ChatAttachmentModel.message_id.is_(None),
                )
                .values(message_id=message.id)
                .returning(ChatAttachmentModel.id)
            )
            if len(result.scalars().all()) != len(set(link_attachment_ids)):
                raise ChatAttachmentUnavailableError(
                    "Alguna de las imágenes adjuntas ya no está disponible."
                )

        if copy_attachment_ids:
            await self._copy_attachments(copy_attachment_ids, to_message_id=message.id)

        await self._session.refresh(model)
        entity = ConversationOrmMapper.message_to_entity(model)
        entity.attachments = await self._message_attachments(message.id)
        return entity

    async def _copy_attachments(
        self, attachment_ids: Sequence[UUID], *, to_message_id: UUID
    ) -> None:
        rows = await self._session.execute(
            select(ChatAttachmentModel, ChatAttachmentBlobModel.content)
            .join(
                ChatAttachmentBlobModel,
                ChatAttachmentBlobModel.attachment_id == ChatAttachmentModel.id,
            )
            .where(ChatAttachmentModel.id.in_(attachment_ids))
            .order_by(ChatAttachmentModel.created_at.asc())
        )
        found = rows.all()
        if len(found) != len(set(attachment_ids)):
            raise ChatAttachmentUnavailableError(
                "Alguna de las imágenes adjuntas ya no está disponible."
            )
        for source, content in found:
            copy_id = uuid4()
            self._session.add(
                ChatAttachmentModel(
                    id=copy_id,
                    user_id=source.user_id,
                    owner_erp_database_id=source.owner_erp_database_id,
                    message_id=to_message_id,
                    mime=source.mime,
                    filename=source.filename,
                    size_bytes=source.size_bytes,
                    width=source.width,
                    height=source.height,
                    # Conserva el orden relativo de las imágenes originales.
                    created_at=source.created_at,
                )
            )
            # La fila del adjunto tiene que existir antes que su blob (FK).
            await self._session.flush()
            self._session.add(ChatAttachmentBlobModel(attachment_id=copy_id, content=content))
        await self._session.flush()

    async def _message_attachments(self, message_id: UUID) -> list[ChatAttachment]:
        result = await self._session.execute(
            select(ChatAttachmentModel)
            .where(ChatAttachmentModel.message_id == message_id)
            .order_by(ChatAttachmentModel.created_at.asc())
        )
        return [ConversationOrmMapper.attachment_to_entity(m) for m in result.scalars().all()]

    async def get_attachments(self, attachment_ids: Sequence[UUID]) -> list[ChatAttachment]:
        if not attachment_ids:
            return []
        result = await self._session.execute(
            select(ChatAttachmentModel).where(ChatAttachmentModel.id.in_(attachment_ids))
        )
        return [ConversationOrmMapper.attachment_to_entity(m) for m in result.scalars().all()]

    async def get_attachment_contents(self, attachment_ids: Sequence[UUID]) -> dict[UUID, bytes]:
        if not attachment_ids:
            return {}
        result = await self._session.execute(
            select(ChatAttachmentBlobModel.attachment_id, ChatAttachmentBlobModel.content).where(
                ChatAttachmentBlobModel.attachment_id.in_(attachment_ids)
            )
        )
        return dict(result.tuples().all())

    async def list_messages(
        self,
        conversation_id: UUID,
        *,
        include_superseded: bool = False,
        limit: int | None = None,
    ) -> list[Message]:
        stmt = select(MessageModel).where(
            MessageModel.conversation_id == conversation_id
        )
        if not include_superseded:
            stmt = stmt.where(MessageModel.superseded_at.is_(None))
        if limit is None:
            stmt = stmt.order_by(MessageModel.created_at.asc())
            result = await self._session.execute(stmt)
            rows = list(result.scalars().all())
        else:
            # Los N más recientes: se piden en descendente (que es lo que el
            # índice puede cortar) y se invierten en memoria. Ordenar
            # ascendente con LIMIT devolvería los N más VIEJOS.
            stmt = stmt.order_by(MessageModel.created_at.desc()).limit(limit)
            result = await self._session.execute(stmt)
            rows = list(reversed(result.scalars().all()))
        return [ConversationOrmMapper.message_to_entity(m) for m in rows]

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
