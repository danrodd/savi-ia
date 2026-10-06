"""Use case: ejecuta una consulta semántica de punta a punta.

Flujo: dict del LLM → parse → validar entidad → compilar → ejecutar →
formatear a texto legible. Captura errores de dominio y los devuelve como
texto accionable (el LLM lo usa para corregir o explicar al usuario);
nunca propaga stack traces ni detalle de la BD.
"""

from __future__ import annotations

import logging
from collections.abc import Collection, Sequence
from dataclasses import replace
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.modules.data_query.application.query_compiler import compile_query, search_terms
from app.modules.data_query.application.query_parser import parse_semantic_query
from app.modules.data_query.domain.exceptions import (
    SemanticQueryError,
    UnknownEntityError,
)
from app.modules.data_query.domain.query_result import QueryResult
from app.modules.data_query.domain.semantic_model import SemanticEntity
from app.modules.data_query.domain.semantic_query import (
    FilterOp,
    QueryFilter,
    QueryMode,
    SemanticQuery,
)
from app.modules.data_query.infrastructure.catalog import entity_names, get_entity
from app.modules.data_query.infrastructure.erp_query_executor import execute_compiled

log = logging.getLogger(__name__)


async def run_semantic_query(
    raw: dict[str, Any],
    *,
    erp_database_id: UUID | None = None,
    modules: Collection[str] | None = None,
) -> str:
    """Devuelve texto markdown listo para que el LLM lo presente, o un
    mensaje de error accionable (también texto)."""
    try:
        query = parse_semantic_query(raw)
        entity = get_entity(query.entidad)
        if entity is None:
            raise UnknownEntityError(query.entidad, entity_names())
        entity = entity.scoped_for(modules)
        if not entity.allowed_for(modules):
            # Defensa en profundidad: la descripción de la tool ya la oculta.
            needed = entity.required_modules or tuple(
                dict.fromkeys(m for scope in entity.row_scopes for m in scope.modules)
            )
            return (
                f"El usuario no tiene acceso a '{entity.name}' en el ERP (requiere el "
                f"módulo {' o '.join(needed)}). Decile que no tiene "
                "permiso para consultar esa información; no la estimes por otro camino."
            )
        compiled = compile_query(query, entity)
    except SemanticQueryError as e:
        return f"No pude armar la consulta: {e}"

    try:
        result = await execute_compiled(
            compiled, query.entidad, query.modo, erp_database_id=erp_database_id
        )
    except Exception:
        log.exception("semantic_query_execution_failed entity=%s", query.entidad)
        return (
            "Hubo un problema técnico al consultar la información. "
            "Intentá reformular la pregunta o pedí menos detalle."
        )

    if _is_empty(result):
        hint = _narrower_search_hint(query.filtros)
        if hint:
            return hint
        return _format_result(result, compiled.select_labels)
    note = await _mixed_matches_note(query, entity, erp_database_id)
    return _format_result(result, compiled.select_labels) + note


# Cuántos valores distintos se nombran en el aviso de coincidencias mezcladas.
_MIXED_MATCHES_SHOWN = 10


async def _mixed_matches_note(
    query: SemanticQuery, entity: SemanticEntity, erp_database_id: UUID | None
) -> str:
    """Avisa cuando un total sin desglose suma varias cosas que el usuario
    nombró como una sola.

    "contiene" exige todas las palabras, no la frase: "tornillo MAD 6 2"
    coincide con 6 * 2", 6 * 1 1/2" y ZINCADO 6 * 1/2. Medido con
    Gemini: respondió 27.115 unidades "del tornillo MAD 6 * 2" sumando cinco
    productos, cuando ese producto tiene 18.183. Se verifica acá con una
    segunda consulta, con el mismo filtro, agrupada por el campo buscado.

    Agrupar por otra cosa no alcanza: por sucursal, "TORNILLO MAD 6 * 2\""
    dio 28.883 en Bodega, que son el 6 * 2" y el 6 * 1 1/2" juntos.
    """
    if query.modo != QueryMode.AGGREGATE:
        return ""
    flt = next(
        (
            f
            for f in query.filtros
            if f.op == FilterOp.CONTAINS
            and f.campo in entity.dimensions
            and f.campo not in query.dimensiones
        ),
        None,
    )
    if flt is None:
        return ""
    probe = replace(query, dimensiones=[flt.campo], orden=None, limite=_MIXED_MATCHES_SHOWN + 1)
    try:
        compiled = compile_query(probe, entity)
        result = await execute_compiled(
            compiled, probe.entidad, probe.modo, erp_database_id=erp_database_id
        )
    except Exception:
        # El aviso es una ayuda: si falla, la respuesta principal sigue sirviendo.
        log.exception("mixed_matches_probe_failed entity=%s", query.entidad)
        return ""
    names = [_fmt_value(row.get(flt.campo)) for row in result.rows]
    if len(names) <= 1:
        return ""
    shown = ", ".join(names[:_MIXED_MATCHES_SHOWN])
    more = " y otros" if len(names) > _MIXED_MATCHES_SHOWN else ""
    return (
        f"\n\n_(Ojo: la búsqueda '{flt.valor}' en '{flt.campo}' coincidió con "
        f"varios valores distintos ({shown}{more}) y este total los SUMA a todos. "
        "Si el usuario preguntó por uno en particular, NO presentes este total "
        f"como suyo: repetí la consulta con '{flt.campo}' en 'dimensiones' y "
        "respondé solo el que corresponde, o mostrale las opciones.)_"
    )


def _is_empty(result: QueryResult) -> bool:
    """Sin filas, o un agregado sin coincidencias: `SUM` sobre nada da una
    fila con todo en NULL, y el modelo la leía como "no se puede saber"."""
    return not result.rows or all(value is None for row in result.rows for value in row.values())


def _narrower_search_hint(filters: Sequence[QueryFilter]) -> str | None:
    """Una búsqueda por nombre con muchas palabras exige TODAS: "acetaminofen
    500 mg 10 tabletas" no encuentra "ACETAMINOFEN 500MG 10TAB". Medido: el
    modelo, en vez de reintentar, le preguntaba al usuario cómo se llamaba el
    producto. La indicación va en el resultado porque es donde el modelo
    decide qué hacer después; en la descripción de la tool no alcanzó."""
    for flt in filters:
        if flt.op != FilterOp.CONTAINS:
            continue
        terms = search_terms(str(flt.valor))
        if len(terms) >= 3:
            # El nombre y el primer número ("acetaminofen 500", "tornillo 6"):
            # la presentación y las unidades son lo que más cambia de escritura.
            number = next((t for t in terms[1:] if any(c.isdigit() for c in t)), None)
            keywords = f"{terms[0]} {number}" if number else terms[0]
            return (
                f"No hubo coincidencias con TODAS estas palabras en '{flt.campo}': "
                f"{', '.join(terms)}. El nombre en el ERP suele estar abreviado "
                f"(ej. '10TAB', '500MG'). Reintentá la consulta con 1 o 2 palabras "
                f"clave, por ejemplo '{keywords}', antes de responder que no existe."
            )
    return None


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
        lines = [f"- **{labels.get(c, c)}**: {_fmt_value(row[c])}" for c in result.columns]
        return "\n".join(lines)

    # Tabla markdown para agregados y detalle.
    sep = " | "
    out = [sep.join(headers), sep.join("---" for _ in headers)]
    for row in result.rows:
        out.append(sep.join(_fmt_value(row[c]) for c in result.columns))
    table = "\n".join(out)

    note = ""
    if result.truncated:
        # El aviso tiene que decir QUÉ HACER, no solo que se cortó: sin la
        # instrucción, el modelo sumaba las filas visibles y presentaba ese
        # subtotal como el total del negocio.
        note = (
            f"\n\n_(Se cortó en {result.row_count} filas y hay más. NO sumes "
            "estas filas para dar un total: ese número sería solo de esta "
            "página. Para totales usá modo 'agregado' con métricas, o afiná "
            "los filtros para acotar la búsqueda.)_"
        )
    return table + note
