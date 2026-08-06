"""Tipos de columna portables entre PostgreSQL y SQLite.

La BD del agente puede correr sobre Postgres (despliegue servidor) o
sobre SQLite (instalación de escritorio). Los modelos ORM usan estos
alias en vez de los tipos de `sqlalchemy.dialects.postgresql` para que
el mismo metadata sirva a los dos dialectos.

Sobre Postgres el DDL generado es idéntico al anterior (`UUID`, `JSONB`,
`TIMESTAMPTZ`), así que las instalaciones existentes no requieren
migración.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Dialect, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeDecorator

# UUID nativo en Postgres, CHAR(32) en SQLite. SQLAlchemy 2 hace la
# conversión a/desde `uuid.UUID` en ambos casos.
UuidType = Uuid(as_uuid=True)

# JSONB en Postgres (indexable, operadores nativos), JSON sobre TEXT en
# SQLite. El operador `->>` que usa el repositorio de usage existe en
# ambos motores (SQLite lo soporta desde 3.38, incluido en Python 3.12).
JsonType = JSON().with_variant(JSONB(), "postgresql")


class UtcDateTime(TypeDecorator[datetime]):
    """`TIMESTAMPTZ` que siempre entrega datetimes aware en UTC.

    SQLite no tiene tipo de fecha: guarda un string ISO y **descarta el
    offset sin avisar**. Sin este decorator, un `expires_at` escrito
    aware vuelve naive y cualquier comparación contra
    `datetime.now(UTC)` revienta con `TypeError`. Normalizamos en los
    dos sentidos para que el código de dominio nunca vea un naive.

    Sobre Postgres es un passthrough: los valores ya llegan aware.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        # Un naive que llega acá es un bug del caller; asumimos UTC en vez
        # de guardar una hora ambigua.
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, datetime):
            return value
        # SQLite devuelve naive, y su `CURRENT_TIMESTAMP` es UTC.
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
