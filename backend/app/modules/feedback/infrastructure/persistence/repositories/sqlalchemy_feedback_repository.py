"""Persistencia del feedback del propio usuario."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.conversations.infrastructure.persistence.models import (
    ConversationModel,
    MessageModel,
)
from app.modules.feedback.domain.entities import MessageFeedback
from app.modules.feedback.domain.interfaces import FeedbackRepository, FeedbackTarget
from app.modules.feedback.domain.value_objects import FeedbackRating, FeedbackReason
from app.modules.feedback.infrastructure.persistence.models import MessageFeedbackModel

_Model = MessageFeedbackModel


def to_entity(model: MessageFeedbackModel) -> MessageFeedback:
    return MessageFeedback(
        id=model.id,
        message_id=model.message_id,
        user_id=model.user_id,
        owner_erp_database_id=model.owner_erp_database_id,
        rating=FeedbackRating(model.rating),
        reason=FeedbackReason(model.reason) if model.reason else None,
        comment=model.comment,
        user_login=model.user_login,
        user_name=model.user_name,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class SqlAlchemyFeedbackRepository(FeedbackRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_target(self, conversation_id: UUID, message_id: UUID) -> FeedbackTarget | None:
        stmt = (
            select(
                MessageModel.id,
                MessageModel.conversation_id,
                MessageModel.role,
                MessageModel.superseded_at,
                ConversationModel.deleted_at,
                ConversationModel.user_id,
                ConversationModel.owner_erp_database_id,
            )
            .join(ConversationModel, MessageModel.conversation_id == ConversationModel.id)
            .where(
                MessageModel.id == message_id,
                MessageModel.conversation_id == conversation_id,
            )
        )
        row = (await self._session.execute(stmt)).one_or_none()
        if row is None:
            return None
        return FeedbackTarget(
            message_id=row[0],
            conversation_id=row[1],
            role=row[2],
            is_superseded=row[3] is not None,
            conversation_deleted=row[4] is not None,
            conversation_user_id=row[5],
            conversation_owner_database_id=row[6],
        )

    async def _find(
        self, message_id: UUID, user_id: int, owner_erp_database_id: UUID
    ) -> MessageFeedbackModel | None:
        stmt = select(_Model).where(
            _Model.message_id == message_id,
            _Model.user_id == user_id,
            _Model.owner_erp_database_id == owner_erp_database_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    @staticmethod
    def _apply(model: MessageFeedbackModel, feedback: MessageFeedback) -> None:
        model.rating = feedback.rating.value
        model.reason = feedback.reason.value if feedback.reason else None
        model.comment = feedback.comment
        model.user_login = feedback.user_login
        model.user_name = feedback.user_name
        model.updated_at = datetime.now(UTC)

    async def upsert(self, feedback: MessageFeedback) -> MessageFeedback:
        existing = await self._find(
            feedback.message_id, feedback.user_id, feedback.owner_erp_database_id
        )
        if existing is None:
            model = _Model(
                id=feedback.id,
                message_id=feedback.message_id,
                user_id=feedback.user_id,
                owner_erp_database_id=feedback.owner_erp_database_id,
                created_at=feedback.created_at,
                updated_at=feedback.updated_at,
            )
            self._apply(model, feedback)
            try:
                # SAVEPOINT: dos PUT simultáneos del mismo usuario chocan contra
                # el UNIQUE; el que pierde reemplaza en vez de fallar con 500.
                async with self._session.begin_nested():
                    self._session.add(model)
                    await self._session.flush()
            except IntegrityError:
                self._session.expunge(model)
                existing = await self._find(
                    feedback.message_id, feedback.user_id, feedback.owner_erp_database_id
                )
                if existing is None:
                    raise
            else:
                await self._session.refresh(model)
                return to_entity(model)
        self._apply(existing, feedback)
        await self._session.flush()
        await self._session.refresh(existing)
        return to_entity(existing)

    async def delete(self, message_id: UUID, *, user_id: int, owner_erp_database_id: UUID) -> None:
        await self._session.execute(
            delete(_Model).where(
                _Model.message_id == message_id,
                _Model.user_id == user_id,
                _Model.owner_erp_database_id == owner_erp_database_id,
            )
        )

    async def list_for_messages(
        self,
        message_ids: Sequence[UUID],
        *,
        user_id: int,
        owner_erp_database_id: UUID,
    ) -> dict[UUID, MessageFeedback]:
        if not message_ids:
            return {}
        stmt = select(_Model).where(
            _Model.message_id.in_(list(message_ids)),
            _Model.user_id == user_id,
            _Model.owner_erp_database_id == owner_erp_database_id,
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return {row.message_id: to_entity(row) for row in rows}
