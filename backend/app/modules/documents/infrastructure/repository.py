from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.conversations.infrastructure.persistence.models.conversation_model import (
    ConversationModel,
)
from app.modules.documents.domain.interfaces import ResultSetRepository
from app.modules.documents.domain.result_set import ResultColumn, ResultSet
from app.modules.documents.infrastructure.models import ResultSetModel


def _to_entity(model: ResultSetModel) -> ResultSet:
    return ResultSet(
        id=model.id,
        conversation_id=model.conversation_id,
        title=model.title,
        columns=[ResultColumn(c["key"], c["label"], c.get("kind", "text")) for c in model.columns],
        rows=model.rows,
        total_rows=model.total_rows,
        total_is_lower_bound=model.total_is_lower_bound,
        has_personal_data=model.has_personal_data,
        created_at=model.created_at,
    )


class SqlAlchemyResultSetRepository(ResultSetRepository):
    """Con su propio sessionmaker: las tools guardan en medio de un turno, fuera
    de la sesión de cualquier request (mismo patrón que los writers del chat)."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def add(self, result_set: ResultSet) -> None:
        async with self._sessionmaker() as session:
            session.add(
                ResultSetModel(
                    id=result_set.id,
                    conversation_id=result_set.conversation_id,
                    title=result_set.title[:200],
                    columns=[
                        {"key": c.key, "label": c.label, "kind": c.kind} for c in result_set.columns
                    ],
                    rows=result_set.rows,
                    total_rows=result_set.total_rows,
                    total_is_lower_bound=result_set.total_is_lower_bound,
                    has_personal_data=result_set.has_personal_data,
                    created_at=result_set.created_at,
                    expires_at=result_set.expires_at,
                )
            )
            await session.commit()

    async def get_owned(
        self, result_set_id: UUID, *, user_id: int, owner_erp_database_id: UUID
    ) -> ResultSet | None:
        async with self._sessionmaker() as session:
            stmt = (
                select(ResultSetModel)
                .join(ConversationModel, ConversationModel.id == ResultSetModel.conversation_id)
                .where(
                    ResultSetModel.id == result_set_id,
                    ResultSetModel.expires_at > datetime.now(UTC),
                    ConversationModel.user_id == user_id,
                    ConversationModel.owner_erp_database_id == owner_erp_database_id,
                    ConversationModel.deleted_at.is_(None),
                )
            )
            model = (await session.execute(stmt)).scalar_one_or_none()
        return _to_entity(model) if model is not None else None

    async def created_since(self, conversation_id: UUID, since: datetime) -> list[ResultSet]:
        async with self._sessionmaker() as session:
            stmt = (
                select(ResultSetModel)
                .where(
                    ResultSetModel.conversation_id == conversation_id,
                    ResultSetModel.created_at >= since,
                )
                .order_by(ResultSetModel.created_at)
            )
            models = (await session.execute(stmt)).scalars().all()
        return [_to_entity(m) for m in models]
