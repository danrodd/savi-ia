"""Stream `free_query/1` (§4.4).

Origen: `audit_query`. **Nunca** `sql`, `user_question` ni `error_message`: pueden
contener literales con datos del ERP. Esas columnas ni siquiera se seleccionan.
"""

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.cloud_link.domain.entities import Cursor, SyncEvent
from app.modules.cloud_link.domain.interfaces import EventSource
from app.modules.cloud_link.domain.value_objects import SyncStream
from app.modules.cloud_link.infrastructure.sources.keyset import keyset_after
from app.modules.free_query.infrastructure.models import AuditQueryModel

_NOT_CODE = re.compile(r"[^a-z0-9_]")


def result_code(raw: str) -> str:
    """El contrato exige `^[a-z0-9_]{1,32}$`; un valor fuera de eso no debe
    hacer rechazar el evento."""
    cleaned = _NOT_CODE.sub("_", raw.strip().lower())[:32]
    return cleaned or "unknown"


class FreeQuerySource(EventSource):
    stream = SyncStream.FREE_QUERY

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def read_batch(self, after: Cursor, limit: int) -> list[SyncEvent]:
        q = AuditQueryModel
        statement = (
            select(
                q.id,
                q.created_at,
                q.conversation_id,
                q.erp_database_id,
                q.result,
                q.estimated_rows,
                q.returned_rows,
                q.duration_ms,
            )
            .where(keyset_after(q.created_at, q.id, after))
            .order_by(q.created_at, q.id)
            .limit(limit)
        )
        async with self._sessionmaker() as session:
            rows = (await session.execute(statement)).all()
        return [
            SyncEvent(
                schema=SyncStream.FREE_QUERY.schema,
                source_id=str(r.id),
                occurred_at=r.created_at,
                data={
                    "conversation_ref": str(r.conversation_id) if r.conversation_id else None,
                    "database_ref": str(r.erp_database_id) if r.erp_database_id else None,
                    "result": result_code(r.result),
                    "estimated_rows": max(r.estimated_rows, 0)
                    if r.estimated_rows is not None
                    else None,
                    "returned_rows": max(r.returned_rows, 0)
                    if r.returned_rows is not None
                    else None,
                    "duration_ms": max(r.duration_ms, 0) if r.duration_ms is not None else None,
                },
                cursor_id=str(r.id),
            )
            for r in rows
        ]
