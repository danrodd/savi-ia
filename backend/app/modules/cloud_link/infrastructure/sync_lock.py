"""Un sincronizador activo por BD (S8)."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.modules.cloud_link.domain.interfaces import SyncLock

_LOCK_KEY = "hashtext('savi_cloud_sync')"


class NoopSyncLock(SyncLock):
    """SQLite: hay un solo proceso, no hace falta lock."""

    def acquire(self) -> AbstractAsyncContextManager[bool]:
        return self._always()

    @asynccontextmanager
    async def _always(self) -> AsyncGenerator[bool]:
        yield True


class PostgresAdvisorySyncLock(SyncLock):
    """`pg_try_advisory_lock` por ciclo. El lock es de sesión: se toma y se
    suelta en la MISMA conexión, que queda reservada mientras dura el ciclo."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    def acquire(self) -> AbstractAsyncContextManager[bool]:
        return self._hold()

    @asynccontextmanager
    async def _hold(self) -> AsyncGenerator[bool]:
        async with self._engine.connect() as connection:
            result = await connection.execute(text(f"SELECT pg_try_advisory_lock({_LOCK_KEY})"))
            acquired = bool(result.scalar())
            try:
                yield acquired
            finally:
                if acquired:
                    try:
                        await connection.execute(text(f"SELECT pg_advisory_unlock({_LOCK_KEY})"))
                    except BaseException:
                        # Si no se pudo soltar, la conexión no puede volver al
                        # pool conservando el lock: se descarta.
                        await connection.invalidate()
                        raise
