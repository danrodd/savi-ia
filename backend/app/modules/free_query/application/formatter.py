"""Formateo del resultado de una consulta libre para el LLM.

Devolvemos **JSON estructurado**, no markdown listo para mostrar. La
diferencia es importante: si le pasamos al LLM una tabla markdown, el
camino más fácil es transcribirla literal al usuario (respuesta rígida
y monótona). Si le pasamos datos crudos, tiene que decidir cómo
presentarlos según el caso (1 fila → prosa, listados → tabla, agregados
→ prosa con número resaltado).

Las reglas de presentación (cuándo prosa vs tabla) están en el system
prompt. Acá solo hacemos los datos JSON-serializable: Decimal, datetime,
date y bytes se vuelven representaciones legibles.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.modules.free_query.domain.query_result import QueryResult


def format_result(result: QueryResult) -> str:
    payload: dict[str, Any] = {
        "row_count": result.returned_rows,
        "estimated_rows": result.estimated_rows,
        "duration_ms": result.duration_ms,
        "truncated": result.truncated,
        "columns": result.columns,
        "rows": result.rows,
    }
    return json.dumps(
        payload, ensure_ascii=False, default=_json_default, indent=2
    )


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        # Sin notación científica; respeta los decimales de la columna.
        return format(value, "f")
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bytes):
        return f"<binary:{len(value)} bytes>"
    raise TypeError(f"Tipo no serializable: {type(value).__name__}")
