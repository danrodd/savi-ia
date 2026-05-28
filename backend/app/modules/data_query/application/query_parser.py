"""Parsea el dict crudo que arma el LLM a un SemanticQuery tipado.

Defensivo: valida enums y estructura, da errores accionables. No toca la
BD ni el modelo semántico (eso es el compilador) — solo forma el objeto.
"""
from __future__ import annotations

from typing import Any, cast

from app.modules.data_query.domain.exceptions import InvalidQueryError
from app.modules.data_query.domain.semantic_query import (
    FilterOp,
    QueryFilter,
    QueryMode,
    SemanticQuery,
    SortSpec,
)


def _as_str_list(value: Any, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise InvalidQueryError(f"'{field_name}' debe ser una lista de nombres.")
    return [str(v) for v in cast(list[Any], value)]


def _parse_mode(raw: Any) -> QueryMode:
    try:
        return QueryMode(str(raw))
    except ValueError:
        raise InvalidQueryError(
            f"Modo inválido '{raw}'. Usá: agregado, detalle o registro."
        ) from None


def _parse_op(raw: Any) -> FilterOp:
    try:
        return FilterOp(str(raw))
    except ValueError:
        raise InvalidQueryError(
            f"Operador de filtro inválido '{raw}'. Usá: =, !=, >, >=, <, <=, "
            "entre, contiene, en."
        ) from None


def _parse_filters(raw: Any) -> list[QueryFilter]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise InvalidQueryError("'filtros' debe ser una lista.")
    out: list[QueryFilter] = []
    for raw_item in cast(list[Any], raw):
        if not isinstance(raw_item, dict):
            raise InvalidQueryError(
                "Cada filtro debe ser un objeto {campo, op, valor}."
            )
        item = cast(dict[str, Any], raw_item)
        campo = item.get("campo")
        if not campo:
            raise InvalidQueryError("Cada filtro requiere 'campo'.")
        out.append(
            QueryFilter(
                campo=str(campo),
                op=_parse_op(item.get("op", "=")),
                valor=item.get("valor"),
            )
        )
    return out


def _parse_orden(raw: Any) -> SortSpec | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise InvalidQueryError("'orden' debe ser un objeto {campo, dir}.")
    d = cast(dict[str, Any], raw)
    campo = d.get("campo")
    if not campo:
        return None
    direction = str(d.get("dir", "desc")).lower()
    if direction not in ("asc", "desc"):
        direction = "desc"
    return SortSpec(campo=str(campo), dir=direction)  # type: ignore[arg-type]


def parse_semantic_query(raw: dict[str, Any]) -> SemanticQuery:
    entidad = raw.get("entidad")
    if not entidad:
        raise InvalidQueryError("La consulta requiere 'entidad'.")

    limite_raw = raw.get("limite", 20)
    try:
        limite = int(limite_raw)
    except (TypeError, ValueError):
        limite = 20

    return SemanticQuery(
        entidad=str(entidad),
        modo=_parse_mode(raw.get("modo", "agregado")),
        metricas=_as_str_list(raw.get("metricas"), "metricas"),
        dimensiones=_as_str_list(raw.get("dimensiones"), "dimensiones"),
        campos=_as_str_list(raw.get("campos"), "campos"),
        filtros=_parse_filters(raw.get("filtros")),
        orden=_parse_orden(raw.get("orden")),
        limite=limite,
    )
