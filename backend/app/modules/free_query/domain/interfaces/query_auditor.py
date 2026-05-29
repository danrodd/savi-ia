"""Puerto del audit log de queries.

Persiste el resultado de cada intento de SQL libre (ok o rechazado).
Igual que el resto de writers del proyecto, usa una sesión independiente
del request para sobrevivir a la cancelación del cliente.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from app.modules.free_query.domain.errors import RejectionReason


class QueryAuditor(ABC):
    @abstractmethod
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
    ) -> None: ...
