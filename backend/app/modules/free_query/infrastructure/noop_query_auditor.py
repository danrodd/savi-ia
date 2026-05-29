"""Auditor no-op para arrancar el módulo sin la tabla de audit todavía.

Lo reemplazaremos por `SqlAlchemyQueryAuditor` cuando la tabla
`agent_db.audit_query` esté creada (sub-fase 1.4). Mientras tanto
loguea por stdlib para no perder visibilidad.
"""
from __future__ import annotations

import logging
from uuid import UUID

from app.modules.free_query.domain.errors import RejectionReason
from app.modules.free_query.domain.interfaces import QueryAuditor

log = logging.getLogger("free_query.audit")


class NoopQueryAuditor(QueryAuditor):
    async def record(
        self,
        *,
        conversation_id: UUID | None,
        user_question: str | None,
        sql: str,
        result: RejectionReason,
        estimated_rows: int | None,
        returned_rows: int | None,
        duration_ms: int | None,
        error_message: str | None,
    ) -> None:
        log.info(
            "free_query result=%s conv=%s est=%s ret=%s ms=%s sql=%r err=%r",
            result.value,
            conversation_id,
            estimated_rows,
            returned_rows,
            duration_ms,
            sql[:200],
            error_message[:200] if error_message else None,
        )
