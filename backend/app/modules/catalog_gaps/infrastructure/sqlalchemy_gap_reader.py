"""Lee las señales de vacío de la auditoría de consultas libres y de los turnos.

- `audit_query`: cada consulta libre, con su resultado y su SQL (para las tablas).
  Las de esquema (`information_schema`) no cuentan: son el modelo buscando
  columnas, no una pregunta del usuario.
- `messages.tool_invocations`: el turno que gastó el cupo de consultas al ERP
  termina con la consulta rechazada (`status = "error"`).

La pregunta es el mensaje del usuario de ese turno, no la `pregunta_usuario`
que escribe el modelo (a veces la resume o le suma lo de turnos anteriores).
"""

from __future__ import annotations

import re
from bisect import bisect_right
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog_gaps.domain.interfaces import GapEventReader
from app.modules.catalog_gaps.domain.value_objects import GapEvent, GapKind
from app.modules.conversations.infrastructure.persistence.models.conversation_model import (
    ConversationModel,
    MessageModel,
)
from app.modules.free_query.application.referenced_tables import referenced_tables
from app.modules.free_query.infrastructure.models import AuditQueryModel

_SCHEMA_LOOKUP = re.compile(r"\binformation_schema\b", re.IGNORECASE)
_DATA_TOOLS = ("consultar_datos", "consultar_libre")
# Tope de filas leídas por periodo: protege la consulta si el periodo es enorme.
_MAX_ROWS = 20_000


def _sql_of(tool: dict[str, Any]) -> str:
    raw: object = tool.get("input")
    if not isinstance(raw, dict):
        return ""
    value = cast(dict[str, object], raw).get("sql")
    return value if isinstance(value, str) else ""


def hit_query_limit(tools: Sequence[dict[str, Any]] | None, query_limit: int) -> bool:
    """El turno hizo más consultas al ERP que el cupo y la última se rechazó.

    Cuenta todas las consultas al ERP, también las de esquema: hasta el
    2026-11-25 gastaban el mismo cupo (el turno de la retención en la fuente
    llegó al tope con nueve). Desde entonces tienen el suyo, y un turno que
    pasa de `query_limit` igual tuvo que haber gastado el de datos.
    """
    erp = [t for t in tools or () if t.get("name") in _DATA_TOOLS]
    return len(erp) > query_limit and erp[-1].get("status") == "error"


def _tables_of(tools: Iterable[dict[str, Any]]) -> tuple[str, ...]:
    found: set[str] = set()
    for tool in tools:
        if tool.get("name") == "consultar_libre":
            found.update(referenced_tables(_sql_of(tool)))
    return tuple(sorted(found))


class _UserQuestions:
    """El último mensaje del usuario antes de un momento, por conversación."""

    def __init__(self, rows: Iterable[tuple[UUID, datetime, str]]) -> None:
        self._by_conversation: dict[UUID, tuple[list[datetime], list[str]]] = {}
        for conversation_id, created_at, content in sorted(rows, key=lambda r: r[1]):
            times, texts = self._by_conversation.setdefault(conversation_id, ([], []))
            times.append(created_at)
            texts.append(content)

    def before(self, conversation_id: UUID, moment: datetime) -> str | None:
        entry = self._by_conversation.get(conversation_id)
        if entry is None:
            return None
        times, texts = entry
        i = bisect_right(times, moment)
        return texts[i - 1] if i else None


class SqlAlchemyGapEventReader(GapEventReader):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def events(
        self,
        owner_erp_database_id: UUID,
        start: datetime,
        end: datetime,
        query_limit: int,
    ) -> list[GapEvent]:
        owned = (
            ConversationModel.owner_erp_database_id == owner_erp_database_id,
            ConversationModel.deleted_at.is_(None),
        )
        audit = (
            await self._session.execute(
                select(
                    AuditQueryModel.conversation_id,
                    AuditQueryModel.created_at,
                    AuditQueryModel.result,
                    AuditQueryModel.sql,
                    AuditQueryModel.user_question,
                )
                .join(ConversationModel, ConversationModel.id == AuditQueryModel.conversation_id)
                .where(
                    *owned, AuditQueryModel.created_at >= start, AuditQueryModel.created_at < end
                )
                .order_by(AuditQueryModel.created_at)
                .limit(_MAX_ROWS)
            )
        ).all()
        turns = (
            await self._session.execute(
                select(
                    MessageModel.conversation_id,
                    MessageModel.created_at,
                    MessageModel.tool_invocations,
                )
                .join(ConversationModel, ConversationModel.id == MessageModel.conversation_id)
                .where(
                    *owned,
                    MessageModel.role == "assistant",
                    MessageModel.created_at >= start,
                    MessageModel.created_at < end,
                )
                .order_by(MessageModel.created_at)
                .limit(_MAX_ROWS)
            )
        ).all()
        capped = [t for t in turns if hit_query_limit(t.tool_invocations, query_limit)]

        conversation_ids = {r.conversation_id for r in audit} | {t.conversation_id for t in capped}
        questions = _UserQuestions(
            (
                await self._session.execute(
                    select(
                        MessageModel.conversation_id, MessageModel.created_at, MessageModel.content
                    )
                    .where(
                        MessageModel.role == "user",
                        MessageModel.conversation_id.in_(conversation_ids),
                        MessageModel.created_at < end,
                    )
                    .limit(_MAX_ROWS)
                )
            ).tuples()
            if conversation_ids
            else ()
        )

        events: list[GapEvent] = []
        for row in audit:
            if row.conversation_id is None or _SCHEMA_LOOKUP.search(row.sql):
                continue
            question = questions.before(row.conversation_id, row.created_at) or row.user_question
            if not question:
                continue
            events.append(
                GapEvent(
                    kind=GapKind.FREE_QUERY if row.result == "ok" else GapKind.FAILED_QUERY,
                    question=question,
                    conversation_id=row.conversation_id,
                    occurred_at=row.created_at,
                    tables=tuple(referenced_tables(row.sql)),
                )
            )
        for turn in capped:
            question = questions.before(turn.conversation_id, turn.created_at)
            if not question:
                continue
            events.append(
                GapEvent(
                    kind=GapKind.QUERY_LIMIT,
                    question=question,
                    conversation_id=turn.conversation_id,
                    occurred_at=turn.created_at,
                    tables=_tables_of(turn.tool_invocations or ()),
                )
            )
        return events
