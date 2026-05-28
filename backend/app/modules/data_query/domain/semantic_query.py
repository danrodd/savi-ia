"""El objeto de consulta que arma el LLM (no escribe SQL).

Es lenguaje de negocio puro: nombra entidad, modo, métricas, dimensiones,
campos y filtros — todos validados después contra el modelo semántico.
Nunca contiene fragmentos de SQL: las expresiones SQL viven en el catálogo
(escrito por nosotros), el LLM solo elige nombres de un menú.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal


class QueryMode(StrEnum):
    AGGREGATE = "agregado"   # métricas agrupadas por dimensiones
    DETAIL = "detalle"       # filas individuales (tope duro de filas)
    RECORD = "registro"      # un único registro por clave


class FilterOp(StrEnum):
    EQ = "="
    NE = "!="
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    BETWEEN = "entre"
    CONTAINS = "contiene"   # LIKE %valor%
    IN = "en"


@dataclass(slots=True)
class QueryFilter:
    campo: str
    op: FilterOp
    valor: Any


@dataclass(slots=True)
class SortSpec:
    campo: str
    dir: Literal["asc", "desc"] = "desc"


def _empty_str_list() -> list[str]:
    return []


def _empty_filter_list() -> list[QueryFilter]:
    return []


@dataclass(slots=True)
class SemanticQuery:
    entidad: str
    modo: QueryMode
    metricas: list[str] = field(default_factory=_empty_str_list)
    dimensiones: list[str] = field(default_factory=_empty_str_list)
    campos: list[str] = field(default_factory=_empty_str_list)
    filtros: list[QueryFilter] = field(default_factory=_empty_filter_list)
    orden: SortSpec | None = None
    limite: int = 20
