"""Paginación por keyset `(created_at, id)` portable (SQLite y Postgres).

La comparación de tuplas `(a, b) > (x, y)` no está garantizada en todas las
versiones de SQLite, así que se expande a la forma explícita. El conjunto
`created_at >= :at` delante es redundante a propósito: le da al planner de
Postgres una cota inferior sobre el índice `(created_at, id)`; sin ella, el
`OR` se evalúa como filtro sobre todo el índice en cada lote.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

from app.modules.cloud_link.domain.entities import Cursor

NIL_UUID = UUID(int=0)


def parse_cursor_id(raw: str) -> UUID:
    """El cursor inicial lleva `id` vacío: todo UUID real es mayor que el nulo."""
    if not raw:
        return NIL_UUID
    try:
        return UUID(raw)
    except ValueError:
        return NIL_UUID


def keyset_after(
    created_at: InstrumentedAttribute[Any], row_id: InstrumentedAttribute[Any], cursor: Cursor
) -> ColumnElement[bool]:
    after_id = parse_cursor_id(cursor.id)
    return and_(
        created_at >= cursor.at,
        or_(created_at > cursor.at, and_(created_at == cursor.at, row_id > after_id)),
    )
