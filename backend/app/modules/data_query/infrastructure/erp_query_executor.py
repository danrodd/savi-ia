"""Ejecuta SQL parametrizado contra el pool readonly del ERP.

El pool ya fuerza `default_transaction_read_only=on` + `statement_timeout`
(ver app/infrastructure/database/pool.py). Acá agregamos un cap absoluto
de filas como red de seguridad — el compilador ya pone LIMIT, esto es
defensa en profundidad por si algo se escapa.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.infrastructure.database.pool import get_erp_engine
from app.modules.data_query.application.query_compiler import CompiledQuery
from app.modules.data_query.domain.query_result import QueryResult
from app.modules.data_query.domain.semantic_query import QueryMode

# Tope absoluto de filas devueltas al modelo, independiente del LIMIT del
# compilador. Nunca debería alcanzarse (LIMIT máx es aggregate_max_rows=100).
_HARD_FETCH_CAP = 200


async def execute_compiled(
    compiled: CompiledQuery,
    entidad: str,
    modo: QueryMode,
) -> QueryResult:
    engine = get_erp_engine()
    async with engine.connect() as conn:
        result = await conn.execute(text(compiled.sql), compiled.params)
        mappings = result.mappings()
        rows: list[dict[str, Any]] = []
        truncated = False
        for i, row in enumerate(mappings):
            if i >= _HARD_FETCH_CAP:
                truncated = True
                break
            rows.append(dict(row))

    columns = list(rows[0].keys()) if rows else []
    return QueryResult(
        entidad=entidad,
        modo=modo,
        columns=columns,
        rows=rows,
        truncated=truncated,
        row_count=len(rows),
    )
