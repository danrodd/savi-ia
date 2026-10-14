"""Stream `conversation/1` (§4.2). Sin título: se genera del contenido."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.cloud_link.application.pseudonymizer import PseudonymizerProvider
from app.modules.cloud_link.domain.entities import Cursor, SyncEvent
from app.modules.cloud_link.domain.interfaces import EventSource
from app.modules.cloud_link.domain.value_objects import SyncStream
from app.modules.cloud_link.infrastructure.sources.keyset import keyset_after
from app.modules.conversations.infrastructure.persistence.models.conversation_model import (
    ConversationModel,
)


class ConversationSource(EventSource):
    stream = SyncStream.CONVERSATION

    def __init__(
        self, sessionmaker: async_sessionmaker[AsyncSession], pseudonymizers: PseudonymizerProvider
    ) -> None:
        self._sessionmaker = sessionmaker
        self._pseudonymizers = pseudonymizers

    async def read_batch(self, after: Cursor, limit: int) -> list[SyncEvent]:
        c = ConversationModel
        # Se seleccionan solo estas columnas: el título nunca se carga.
        statement = (
            select(c.id, c.created_at, c.erp_database_id, c.owner_erp_database_id, c.user_id)
            .where(keyset_after(c.created_at, c.id, after))
            .order_by(c.created_at, c.id)
            .limit(limit)
        )
        pseudonymizer = await self._pseudonymizers.get()
        async with self._sessionmaker() as session:
            rows = (await session.execute(statement)).all()
        return [
            SyncEvent(
                schema=SyncStream.CONVERSATION.schema,
                source_id=str(r.id),
                occurred_at=r.created_at,
                data={
                    "conversation_ref": str(r.id),
                    "database_ref": str(r.erp_database_id) if r.erp_database_id else None,
                    "user_ref": pseudonymizer.user_ref(r.owner_erp_database_id, r.user_id),
                },
                cursor_id=str(r.id),
            )
            for r in rows
        ]
