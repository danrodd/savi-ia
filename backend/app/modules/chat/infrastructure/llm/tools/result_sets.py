"""Guarda el resultado completo de una consulta al ERP para el usuario.

El modelo recibe una muestra y el total; el usuario ve la vista previa en el
chat y exporta todo (ver `docs/plataforma/11-resultados-completos.md`).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from app.infrastructure.database import get_agent_sessionmaker
from app.modules.documents.domain.result_set import EXPORT_MAX_ROWS, build_result_set
from app.modules.documents.infrastructure.repository import SqlAlchemyResultSetRepository

# Se leen una fila más que las que se guardan, para saber si hay más.
FULL_FETCH = EXPORT_MAX_ROWS + 1

Recorder = Callable[
    [str, list[str], dict[str, str], list[dict[str, Any]], bool, int | None], Awaitable[str]
]


def make_recorder(conversation_id: UUID | None) -> Recorder | None:
    """`None` sin conversación: no hay dueño al que atar el resultado."""
    if conversation_id is None:
        return None

    async def record(
        title: str,
        keys: list[str],
        labels: dict[str, str],
        rows: list[dict[str, Any]],
        has_personal_data: bool,
        exact_total: int | None = None,
    ) -> str:
        result_set = build_result_set(
            conversation_id=conversation_id,
            title=title,
            keys=keys,
            labels=labels,
            raw_rows=rows,
            has_personal_data=has_personal_data,
            exact_total=exact_total,
        )
        await SqlAlchemyResultSetRepository(get_agent_sessionmaker()).add(result_set)
        return str(result_set.id)

    return record
