"""Use case: ejecuta una consulta semántica de punta a punta.

Flujo: dict del LLM → parse → validar entidad → compilar → ejecutar →
formatear a texto legible. Captura errores de dominio y los devuelve como
texto accionable (el LLM lo usa para corregir o explicar al usuario);
nunca propaga stack traces ni detalle de la BD.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from app.modules.data_query.application.query_compiler import compile_query
from app.modules.data_query.application.query_parser import parse_semantic_query
from app.modules.data_query.domain.exceptions import (
    SemanticQueryError,
    UnknownEntityError,
)
from app.modules.data_query.domain.query_result import QueryResult
from app.modules.data_query.domain.semantic_query import QueryMode
from app.modules.data_query.infrastructure.catalog import entity_names, get_entity
from app.modules.data_query.infrastructure.erp_query_executor import execute_compiled

log = logging.getLogger(__name__)


async def run_semantic_query(raw: dict[str, Any]) -> str:
    """Devuelve texto markdown listo para que el LLM lo presente, o un
    mensaje de error accionable (también texto)."""
    try:
        query = parse_semantic_query(raw)
        entity = get_entity(query.entidad)
        if entity is None:
            raise UnknownEntityError(query.entidad, entity_names())
        compiled = compile_query(query, entity)
    except SemanticQueryError as e:
        return f"No pude armar la consulta: {e}"

    try:
        result = await execute_compiled(compiled, query.entidad, query.modo)
    except Exception:
        log.exception("semantic_query_execution_failed entity=%s", query.entidad)
        return (
            "Hubo un problema técnico al consultar la información. "
            "Intentá reformular la pregunta o pedí menos detalle."
        )

    return _format_result(result, compiled.select_labels)


def _fmt_value(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "Sí" if v else "No"
    if isinstance(v, Decimal | float):
        # Montos/números: separador de miles, sin decimales si es entero.
        num = float(v)
        if num == int(num):
            return f"{int(num):,}"
        return f"{num:,.2f}"
    return str(v)


def _format_result(result: QueryResult, labels: dict[str, str]) -> str:
    if not result.rows:
        return "No encontré datos que coincidan con esa consulta."

    headers = [labels.get(c, c) for c in result.columns]

    if result.modo == QueryMode.RECORD or (
        result.row_count == 1 and result.modo != QueryMode.DETAIL
    ):
        # Formato clave-valor para un registro único.
        row = result.rows[0]
        lines = [
            f"- **{labels.get(c, c)}**: {_fmt_value(row[c])}" for c in result.columns
        ]
        return "\n".join(lines)

    # Tabla markdown para agregados y detalle.
    sep = " | "
    out = [sep.join(headers), sep.join("---" for _ in headers)]
    for row in result.rows:
        out.append(sep.join(_fmt_value(row[c]) for c in result.columns))
    table = "\n".join(out)

    note = ""
    if result.truncated:
        note = (
            f"\n\n_(Mostrando los primeros {result.row_count}. Para ver algo "
            "puntual, dame un criterio más específico.)_"
        )
    return table + note
