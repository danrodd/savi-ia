"""Implementación de `QueryAuditor` con sessionmaker independiente.

Igual que `AssistantMessageWriter` y `ConversationTitleUpdater`: abre una
sesión nueva por cada `record()` y la cierra. Eso permite que el audit
sobreviva a la cancelación del request HTTP, y desacopla el audit del
ciclo del request.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.free_query.domain.errors import RejectionReason
from app.modules.free_query.domain.interfaces import QueryAuditor
from app.modules.free_query.infrastructure.models import AuditQueryModel


class SqlAlchemyQueryAuditor(QueryAuditor):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

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
        # Trunca a límites de la tabla para nunca fallar el INSERT por
        # tamaño (la pregunta del usuario es libre y puede venir muy
        # larga).
        question_trimmed = user_question[:500] if user_question else None
        async with self._sessionmaker() as session:
            session.add(
                AuditQueryModel(
                    conversation_id=conversation_id,
                    user_question=question_trimmed,
                    sql=sql,
                    result=result.value,
                    estimated_rows=estimated_rows,
                    returned_rows=returned_rows,
                    duration_ms=duration_ms,
                    error_message=error_message,
                )
            )
            await session.commit()
