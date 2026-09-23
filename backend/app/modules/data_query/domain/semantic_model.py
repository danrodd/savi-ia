"""Definición del modelo semántico.

El catálogo declara, por entidad, qué métricas/dimensiones/campos/filtros
existen y a qué SQL mapean. **Las expresiones SQL viven aquí, escritas por
nosotros** — el LLM nunca las provee, solo elige nombres. Esto es lo que
hace imposible la inyección: el LLM no puede nombrar nada que el modelo no
declare.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.modules.data_query.domain.semantic_query import FilterOp

# Tipo de dato real de la columna filtrada. El compilador lo usa para
# convertir el valor que manda el LLM (siempre texto u/o número crudo)
# antes de bindearlo — asyncpg es estricto y rechaza un string donde
# espera un `date`.
FilterValueType = Literal["text", "date", "number", "bool"]


@dataclass(frozen=True, slots=True)
class MetricDef:
    """Una métrica agregable. `sql` es una expresión de agregación."""

    name: str
    sql: str          # ej. 'SUM(f."total")'
    label: str
    requires: tuple[str, ...] = ()  # joins necesarios (por nombre)


@dataclass(frozen=True, slots=True)
class DimensionDef:
    """Una dimensión para agrupar. `sql` es una expresión escalar."""

    name: str
    sql: str          # ej. 'DATE_TRUNC(\'month\', f."fecha")'
    label: str
    requires: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FieldDef:
    """Un campo seleccionable en modo detalle/registro."""

    name: str
    sql: str          # ej. 'f."numero"'
    label: str
    requires: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FilterDef:
    """Un filtro permitido. `sql_column` es la columna sobre la que aplica."""

    name: str
    sql_column: str   # ej. 'f."idTercero"'
    allowed_ops: tuple[FilterOp, ...]
    requires: tuple[str, ...] = ()
    value_type: FilterValueType = "text"


@dataclass(frozen=True, slots=True)
class JoinDef:
    """Un join disponible, identificado por nombre. `sql` es el JOIN entero."""

    name: str
    sql: str


def _no_metrics() -> dict[str, MetricDef]:
    return {}


def _no_dimensions() -> dict[str, DimensionDef]:
    return {}


def _no_fields() -> dict[str, FieldDef]:
    return {}


def _no_filters() -> dict[str, FilterDef]:
    return {}


def _no_joins() -> dict[str, JoinDef]:
    return {}


@dataclass(frozen=True, slots=True)
class SemanticEntity:
    name: str
    base_table: str                       # ej. '"CuentaCobrar"."Factura" f'
    metrics: dict[str, MetricDef] = field(default_factory=_no_metrics)
    dimensions: dict[str, DimensionDef] = field(default_factory=_no_dimensions)
    fields: dict[str, FieldDef] = field(default_factory=_no_fields)
    filters: dict[str, FilterDef] = field(default_factory=_no_filters)
    joins: dict[str, JoinDef] = field(default_factory=_no_joins)
    # Filtros SQL siempre aplicados (ej. 'f."anulada" = false'). NO
    # parametrizados — son constantes del modelo.
    base_filters: tuple[str, ...] = ()
    # Topes de filas por modo.
    aggregate_max_rows: int = 100
    detail_max_rows: int = 30
    # Nombre del filtro que identifica un registro único (modo RECORD).
    record_key: str | None = None
    # Dimensiones que un agregado DEBE usar (agrupando o filtrando) para
    # que el resultado signifique algo. Sin esto, `cartera` devolvía un
    # total que sumaba lo que deben los clientes con lo que la empresa
    # debe a proveedores: un número que nadie puede usar.
    #
    # Se valida en el compilador y no en la descripción de la tool porque
    # pedírselo al modelo solo funciona si el modelo hace caso: medido,
    # Gemini y OpenAI respetaban la regla escrita y Claude la ignoraba.
    require_dimensions: tuple[str, ...] = ()
    description: str = ""
