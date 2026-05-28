from dataclasses import dataclass, field
from typing import Any

from app.modules.data_query.domain.semantic_query import QueryMode


def _empty_rows() -> list[dict[str, Any]]:
    return []


def _empty_columns() -> list[str]:
    return []


@dataclass(slots=True)
class QueryResult:
    """Resultado de ejecutar una consulta semántica."""

    entidad: str
    modo: QueryMode
    columns: list[str] = field(default_factory=_empty_columns)
    rows: list[dict[str, Any]] = field(default_factory=_empty_rows)
    truncated: bool = False  # si se alcanzó el tope de filas
    row_count: int = 0
