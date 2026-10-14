from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def iso_utc(value: datetime) -> str:
    """ISO-8601 en UTC con sufijo `Z`, como lo pide el contrato."""
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class Cursor:
    """Posición de keyset `(created_at, id)`. El `id` va como texto."""

    at: datetime
    id: str

    @property
    def key(self) -> tuple[datetime, str]:
        return (self.at, self.id)


@dataclass(frozen=True, slots=True)
class SyncEvent:
    """Un evento ya mapeado a la lista blanca del contrato."""

    schema: str
    source_id: str
    occurred_at: datetime
    data: dict[str, Any] = field(default_factory=dict[str, Any])
    # Id de la fila origen para el keyset (para `database` no se usa).
    cursor_id: str = ""

    def to_payload(self) -> dict[str, Any]:
        """Exactamente lo que viaja en `events[]` de `ingest`."""
        return {
            "schema": self.schema,
            "source_id": self.source_id,
            "occurred_at": iso_utc(self.occurred_at),
            "data": self.data,
        }

    @property
    def cursor(self) -> Cursor:
        return Cursor(self.occurred_at, self.cursor_id)
