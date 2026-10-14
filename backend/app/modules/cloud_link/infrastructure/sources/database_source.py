"""Stream `database/1`: inventario de sucursales (§4.5), un snapshot.

`name` y `code` sí viajan: son etiquetas que pone el administrador ("Sede
Norte"), no datos del ERP. **Nunca** host, puerto, usuario ni nombre físico de
la base: esas columnas no se seleccionan.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.cloud_link.domain.entities import SyncEvent, iso_utc
from app.modules.cloud_link.domain.interfaces import SnapshotSource
from app.modules.cloud_link.domain.value_objects import SyncStream
from app.modules.erp_databases.infrastructure.persistence.models import ErpDatabaseModel


class DatabaseSource(SnapshotSource):
    stream = SyncStream.DATABASE

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def snapshot(self, now: datetime) -> list[SyncEvent]:
        d = ErpDatabaseModel
        statement = (
            select(
                d.id, d.code, d.name, d.is_active, d.credentials_unreadable, d.last_connection_ok_at
            )
            .where(d.deleted_at.is_(None))
            .order_by(d.id)
        )
        async with self._sessionmaker() as session:
            rows = (await session.execute(statement)).all()

        day = now.astimezone(UTC).date().isoformat()
        return [
            SyncEvent(
                schema=SyncStream.DATABASE.schema,
                source_id=f"{r.id}:{day}",
                occurred_at=now,
                data={
                    "database_ref": str(r.id),
                    "code": (r.code or "")[:64] or "sin_codigo",
                    "name": (r.name or r.code or "")[:200] or "sin_nombre",
                    "is_active": bool(r.is_active),
                    "is_usable": bool(r.is_active) and not bool(r.credentials_unreadable),
                    "credentials_unreadable": bool(r.credentials_unreadable),
                    "last_connection_ok_at": (
                        iso_utc(r.last_connection_ok_at) if r.last_connection_ok_at else None
                    ),
                },
            )
            for r in rows
        ]
