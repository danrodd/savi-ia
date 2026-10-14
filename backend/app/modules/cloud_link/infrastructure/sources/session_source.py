"""Stream `session/1`: inicio de sesión (§4.3).

Origen: `refresh_token.created_at`; `source_id` es el `jti`. Se seleccionan
solo `jti`, fecha, usuario y base. El login (`user_login`) **solo se carga** cuando Cloud
lo autorizó con `identity_mode = named` (la organización interna); en cualquier otro caso
nunca sale de esta base ni se lee.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.auth.infrastructure.persistence.models import RefreshTokenModel
from app.modules.cloud_link.application.pseudonymizer import PseudonymizerProvider
from app.modules.cloud_link.domain.entities import Cursor, SyncEvent
from app.modules.cloud_link.domain.interfaces import EventSource
from app.modules.cloud_link.domain.value_objects import SyncStream
from app.modules.cloud_link.domain.value_objects.sync_policy import IDENTITY_NAMED
from app.modules.cloud_link.infrastructure.sources.keyset import keyset_after


class SessionSource(EventSource):
    stream = SyncStream.SESSION

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        pseudonymizers: PseudonymizerProvider,
        identity_mode: Callable[[], Awaitable[str]] | None = None,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._pseudonymizers = pseudonymizers
        # Se consulta en cada lote: la política puede cambiar entre un ciclo y otro.
        self._identity_mode = identity_mode

    async def read_batch(self, after: Cursor, limit: int) -> list[SyncEvent]:
        t = RefreshTokenModel
        named = self._identity_mode is not None and await self._identity_mode() == IDENTITY_NAMED
        columns: list[Any] = [t.jti, t.created_at, t.user_id, t.erp_database_id]
        if named:
            columns.append(t.user_login)
        statement = (
            select(*columns)
            .where(keyset_after(t.created_at, t.jti, after))
            .order_by(t.created_at, t.jti)
            .limit(limit)
        )
        pseudonymizer = await self._pseudonymizers.get()
        async with self._sessionmaker() as session:
            rows = (await session.execute(statement)).all()

        def data_of(r: Any) -> dict[str, Any]:
            data: dict[str, Any] = {
                "user_ref": pseudonymizer.user_ref(r.erp_database_id, r.user_id),
                "database_ref": str(r.erp_database_id) if r.erp_database_id else None,
            }
            if named and r.user_login:
                data["user_label"] = str(r.user_login).strip().upper()[:64]
            return data

        return [
            SyncEvent(
                schema=SyncStream.SESSION.schema,
                source_id=str(r.jti),
                occurred_at=r.created_at,
                data=data_of(r),
                cursor_id=str(r.jti),
            )
            for r in rows
        ]
