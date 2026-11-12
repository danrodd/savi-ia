"""Puerto del ejecutor de SQL contra el pool del ERP.

Abstrae el motor: hoy implementado con SQLAlchemy async + asyncpg sobre
el pool readonly del ERP; mañana podría apuntar a un user dedicado
(`savi_query`) o a otro engine.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class QueryExecutor(ABC):
    @abstractmethod
    async def estimate_rows(self, sql: str) -> int:
        """`EXPLAIN (FORMAT JSON) <sql>` y extrae el `Plan Rows` raíz.

        Devuelve la estimación del planner. Si falla la planificación
        (sintaxis, permisos, tabla no existe), levanta el error original
        para que el caller lo audite como `db_error`.
        """

    async def count_rows(self, sql: str) -> int | None:
        """Filas totales del SELECT sin su `LIMIT`. Por defecto no se cuenta."""
        return None

    async def estimate_cost(self, sql: str) -> float:
        """`Total Cost` raíz del plan. Por defecto 0: sin medición de costo."""
        return 0.0

    @abstractmethod
    async def execute_select(
        self, sql: str, *, max_rows: int
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """Ejecuta el SELECT y devuelve (columnas, filas).

        Itera con cursor y corta en `max_rows` (defensa en profundidad
        por si la BD igual mandó más). Filas vienen como dicts
        columna→valor para serialización directa a JSON / Markdown.
        """
