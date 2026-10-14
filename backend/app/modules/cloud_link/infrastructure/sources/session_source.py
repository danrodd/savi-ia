"""Stream `session/1`: inicio de sesión (§4.3).

Origen: `refresh_token.created_at`; `source_id` es el `jti`. Se seleccionan
solo `jti`, fecha, usuario y base: el login (`user_login`) nunca se carga.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.auth.infrastructure.persistence.models import RefreshTokenModel
from app.modules.cloud_link.application.pseudonymizer import PseudonymizerProvider
from app.modules.cloud_link.domain.entities import Cursor, SyncEvent
from app.modules.cloud_link.domain.interfaces import EventSource
from app.modules.cloud_link.domain.value_objects import SyncStream
from app.modules.cloud_link.infrastructure.sources.keyset import keyset_after


class SessionSource(EventSource):
    stream = SyncStream.SESSION

    def __init__(
        self, sessionmaker: async_sessionmaker[AsyncSession], pseudonymizers: PseudonymizerProvider
    ) -> None:
        self._sessionmaker = sessionmaker
        self._pseudonymizers = pseudonymizers

    async def read_batch(self, after: Cursor, limit: int) -> list[SyncEvent]:
        t = RefreshTokenModel
        statement = (
            select(t.jti, t.created_at, t.user_id, t.erp_database_id)
            .where(keyset_after(t.created_at, t.jti, after))
            .order_by(t.created_at, t.jti)
            .limit(limit)
        )
        pseudonymizer = await self._pseudonymizers.get()
        async with self._sessionmaker() as session:
            rows = (await session.execute(statement)).all()
        return [
            SyncEvent(
                schema=SyncStream.SESSION.schema,
                source_id=str(r.jti),
                occurred_at=r.created_at,
                data={
                    "user_ref": pseudonymizer.user_ref(r.erp_database_id, r.user_id),
                    "database_ref": str(r.erp_database_id) if r.erp_database_id else None,
                },
                cursor_id=str(r.jti),
            )
            for r in rows
        ]
