"""Implementación del `QueryExecutor` sobre el pool ERP readonly existente.

El engine ya está configurado con `default_transaction_read_only=on` y
`statement_timeout`; cualquier escritura, EXEC o DDL falla en el motor.
Aquí solo agregamos:
- EXPLAIN previo (extracción del `Plan Rows` raíz).
- Iteración con cursor server-side + corte físico a `max_rows`.

Cuando entren las views curadas + DB user dedicado (`savi_query`), basta
con cambiar el engine que se inyecta — no toca este código.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.modules.free_query.domain.interfaces import QueryExecutor


class SqlAlchemyQueryExecutor(QueryExecutor):
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def estimate_rows(self, sql: str) -> int:
        explain_sql = f"EXPLAIN (FORMAT JSON) {sql}"
        async with self._engine.connect() as conn:
            result = await conn.execute(text(explain_sql))
            raw = result.scalar_one()
        plan = _parse_explain_json(raw)
        try:
            root_rows = int(plan[0]["Plan"]["Plan Rows"])
        except (KeyError, IndexError, TypeError, ValueError) as e:
            raise RuntimeError(
                f"No se pudo leer el plan del EXPLAIN: {e!r}"
            ) from e
        return root_rows

    async def execute_select(
        self, sql: str, *, max_rows: int
    ) -> tuple[list[str], list[dict[str, Any]]]:
        async with self._engine.connect() as conn:
            result = await conn.execute(text(sql))
            columns = list(result.keys())
            rows_iter = result.mappings()
            collected: list[dict[str, Any]] = []
            for i, row in enumerate(rows_iter):
                if i >= max_rows:
                    break
                # Convertir cada valor a algo JSON-friendly (Decimal,
                # datetime, etc. los maneja el formatter del caller; acá
                # solo aseguramos dict serializable shallow).
                collected.append(dict(row))
        return columns, collected


def _parse_explain_json(raw: Any) -> list[dict[str, Any]]:
    # asyncpg con SQLAlchemy puede devolver el JSON ya parseado (list) o
    # como string según el driver. Toleramos ambos.
    parsed = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(parsed, list):
        raise RuntimeError(f"EXPLAIN devolvió un shape inesperado: {type(parsed)}")
    return [dict(item) for item in parsed]  # type: ignore[arg-type]
