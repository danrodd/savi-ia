"""Conjunto de resultados: lo que devolvió una consulta al ERP, guardado completo.

El modelo ve una muestra; el usuario puede exportar todo (ver
`docs/plataforma/11-resultados-completos.md`). La tabla del chat y los archivos
salen de acá, de los datos de la base, nunca del texto del modelo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID, uuid4

# Filas que se guardan para exportar. Más que esto se vuelve un problema para
# la carga del ERP y para generar el PDF; se informa "primeras N de más".
EXPORT_MAX_ROWS = 10_000
# Cuánto vive un conjunto (y se borra antes si se borra la conversación).
RETENTION = timedelta(days=90)

ColumnKind = Literal["text", "number", "date"]


@dataclass(frozen=True)
class ResultColumn:
    key: str
    label: str
    kind: ColumnKind = "text"


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class ResultSet:
    conversation_id: UUID
    title: str
    columns: list[ResultColumn]
    rows: list[list[Any]]
    # Filas totales de la consulta. Si `total_is_lower_bound`, hay más de las
    # guardadas y `total_rows` es el tope.
    total_rows: int
    total_is_lower_bound: bool = False
    has_personal_data: bool = False
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_utc_now)

    @property
    def expires_at(self) -> datetime:
        return self.created_at + RETENTION


def plain_value(value: Any) -> Any:
    """Un valor de la base en algo que se guarda en JSON sin perder su tipo."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, bytes | bytearray | memoryview):
        return None  # binarios (fotos, huellas) nunca viajan
    return str(value)


def infer_kind(values: list[Any]) -> ColumnKind:
    present = [v for v in values if v is not None]
    if present and all(isinstance(v, int | float) and not isinstance(v, bool) for v in present):
        return "number"
    if present and all(isinstance(v, str) and _looks_like_date(v) for v in present):
        return "date"
    return "text"


def _looks_like_date(text: str) -> bool:
    try:
        date.fromisoformat(text[:10])
    except ValueError:
        return False
    return len(text) in (10, 19, 25, 26, 32) or "T" in text


def build_result_set(
    *,
    conversation_id: UUID,
    title: str,
    keys: list[str],
    labels: dict[str, str],
    raw_rows: list[dict[str, Any]],
    has_personal_data: bool,
) -> ResultSet:
    """Arma el conjunto a partir de las filas crudas (hasta `EXPORT_MAX_ROWS + 1`)."""
    lower_bound = len(raw_rows) > EXPORT_MAX_ROWS
    kept = raw_rows[:EXPORT_MAX_ROWS]
    rows = [[plain_value(row.get(key)) for key in keys] for row in kept]
    columns = [
        ResultColumn(key, labels.get(key, key), infer_kind([r[i] for r in rows]))
        for i, key in enumerate(keys)
    ]
    return ResultSet(
        conversation_id=conversation_id,
        title=title,
        columns=columns,
        rows=rows,
        total_rows=len(kept),
        total_is_lower_bound=lower_bound,
        has_personal_data=has_personal_data,
    )
