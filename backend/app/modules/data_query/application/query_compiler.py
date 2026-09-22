"""Compilador determinístico: SemanticQuery → SQL parametrizado.

**Aquí vive la seguridad.** Reglas:
- El LLM solo aporta NOMBRES (validados contra el modelo) y VALORES
  (parametrizados). Nunca fragmentos de SQL.
- Toda expresión SQL (métrica, dimensión, campo, columna de filtro) sale
  del catálogo escrito por nosotros.
- El `limite` se clampea al tope del modo (no se confía en el LLM).
- Si el LLM nombra algo inexistente, se rechaza con error accionable.
- Todos los valores van como bind params (`:p0`, `:p1`, …) — cero
  interpolación de strings, cero inyección posible.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any, cast

from app.modules.data_query.domain.exceptions import (
    FilterOpNotAllowedError,
    InvalidQueryError,
    UnknownFieldError,
)
from app.modules.data_query.domain.semantic_model import FilterValueType, SemanticEntity
from app.modules.data_query.domain.semantic_query import (
    FilterOp,
    QueryFilter,
    QueryMode,
    SemanticQuery,
)

_SCALAR_OPS = {
    FilterOp.EQ: "=",
    FilterOp.NE: "!=",
    FilterOp.GT: ">",
    FilterOp.GTE: ">=",
    FilterOp.LT: "<",
    FilterOp.LTE: "<=",
}


def _empty_params() -> dict[str, Any]:
    return {}


def _empty_labels() -> dict[str, str]:
    return {}


@dataclass(slots=True)
class CompiledQuery:
    sql: str
    params: dict[str, Any] = field(default_factory=_empty_params)
    select_labels: dict[str, str] = field(default_factory=_empty_labels)  # alias → label


class _ParamCounter:
    def __init__(self) -> None:
        self._n = 0
        self.params: dict[str, Any] = {}

    def add(self, value: Any) -> str:
        key = f"p{self._n}"
        self._n += 1
        self.params[key] = value
        return f":{key}"


def compile_query(query: SemanticQuery, entity: SemanticEntity) -> CompiledQuery:
    if query.modo == QueryMode.AGGREGATE:
        return _compile_aggregate(query, entity)
    if query.modo == QueryMode.DETAIL:
        return _compile_detail(query, entity)
    return _compile_record(query, entity)


# ── helpers de validación ───────────────────────────────────────────────
def _resolve_metrics(query: SemanticQuery, entity: SemanticEntity) -> list[str]:
    out: list[str] = []
    for m in query.metricas:
        if m not in entity.metrics:
            raise UnknownFieldError("métrica", m, entity.name, list(entity.metrics))
        out.append(m)
    return out


def _resolve_dimensions(query: SemanticQuery, entity: SemanticEntity) -> list[str]:
    out: list[str] = []
    for d in query.dimensiones:
        if d not in entity.dimensions:
            raise UnknownFieldError(
                "dimensión", d, entity.name, list(entity.dimensions)
            )
        out.append(d)
    return out


def _resolve_fields(query: SemanticQuery, entity: SemanticEntity) -> list[str]:
    if not entity.fields:
        raise InvalidQueryError(
            f"La entidad '{entity.name}' no soporta consultas de detalle/registro; "
            "usá modo 'agregado'."
        )
    if not query.campos:
        return list(entity.fields)  # todos los campos por default
    out: list[str] = []
    for c in query.campos:
        if c not in entity.fields:
            raise UnknownFieldError("campo", c, entity.name, list(entity.fields))
        out.append(c)
    return out


def _clamp(limite: int, cap: int) -> int:
    if limite < 1:
        return 1
    return min(limite, cap)


def _coerce_value(value: Any, value_type: FilterValueType, campo: str) -> Any:
    """Convierte el valor del LLM (texto u/o número crudo) al tipo real de
    la columna. asyncpg es estricto con los tipos y rechaza un string donde
    espera un `date` — el LLM solo sabe escribir fechas como texto ISO.
    """
    if value_type != "date":
        return value
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise InvalidQueryError(
        f"El filtro '{campo}' espera una fecha en formato AAAA-MM-DD, recibí '{value}'."
    )


def _build_where(
    query: SemanticQuery,
    entity: SemanticEntity,
    pc: _ParamCounter,
    required_joins: set[str],
) -> str:
    clauses: list[str] = list(entity.base_filters)
    for flt in query.filtros:
        clauses.append(_compile_filter(flt, entity, pc, required_joins))
    return " AND ".join(clauses) if clauses else ""


def _compile_filter(
    flt: QueryFilter,
    entity: SemanticEntity,
    pc: _ParamCounter,
    required_joins: set[str],
) -> str:
    fdef = entity.filters.get(flt.campo)
    if fdef is None:
        raise UnknownFieldError("filtro", flt.campo, entity.name, list(entity.filters))
    if flt.op not in fdef.allowed_ops:
        raise FilterOpNotAllowedError(
            flt.campo, flt.op.value, [o.value for o in fdef.allowed_ops]
        )
    required_joins.update(fdef.requires)
    col = fdef.sql_column
    valor: Any = flt.valor

    if flt.op in _SCALAR_OPS:
        valor = _coerce_value(valor, fdef.value_type, flt.campo)
        return f"{col} {_SCALAR_OPS[flt.op]} {pc.add(valor)}"
    if flt.op == FilterOp.CONTAINS:
        return f"{col} ILIKE {pc.add(f'%{valor}%')}"
    if flt.op == FilterOp.BETWEEN:
        if not isinstance(valor, (list, tuple)):
            raise InvalidQueryError(
                f"El filtro '{flt.campo}' con 'entre' requiere [inicio, fin]."
            )
        pair: Sequence[Any] = cast(Sequence[Any], valor)
        if len(pair) != 2:
            raise InvalidQueryError(
                f"El filtro '{flt.campo}' con 'entre' requiere [inicio, fin]."
            )
        inicio = _coerce_value(pair[0], fdef.value_type, flt.campo)
        fin = _coerce_value(pair[1], fdef.value_type, flt.campo)
        return f"{col} BETWEEN {pc.add(inicio)} AND {pc.add(fin)}"
    if flt.op == FilterOp.IN:
        if isinstance(valor, (list, tuple)):
            values: list[Any] = list(cast(Sequence[Any], valor))
        else:
            values = [valor]
        if not values:
            raise InvalidQueryError(f"El filtro '{flt.campo}' con 'en' requiere valores.")
        values = [_coerce_value(v, fdef.value_type, flt.campo) for v in values]
        placeholders = ", ".join(pc.add(v) for v in values)
        return f"{col} IN ({placeholders})"
    raise InvalidQueryError(f"Operador no soportado: {flt.op}")


def _emit_joins(entity: SemanticEntity, required: set[str]) -> str:
    # Emite los joins necesarios en el orden de declaración del catálogo
    # (Python preserva orden de inserción del dict) — así las dependencias
    # entre joins (ej. producto requiere detalle) salen ordenadas.
    parts = [j.sql for name, j in entity.joins.items() if name in required]
    return ("\n  " + "\n  ".join(parts)) if parts else ""


def _order_clause(
    query: SemanticQuery, valid_aliases: set[str]
) -> str:
    if query.orden is None:
        return ""
    if query.orden.campo not in valid_aliases:
        # Orden por un alias no seleccionado: lo ignoramos en silencio en vez
        # de fallar — el LLM a veces pide ordenar por algo que no trajo.
        return ""
    direction = "DESC" if query.orden.dir == "desc" else "ASC"
    return f'\nORDER BY "{query.orden.campo}" {direction}'


# ── modos ─────────────────────────────────────────────────────────────────
def _compile_aggregate(query: SemanticQuery, entity: SemanticEntity) -> CompiledQuery:
    metrics = _resolve_metrics(query, entity)
    if not metrics:
        raise InvalidQueryError(
            "El modo 'agregado' requiere al menos una métrica "
            f"(disponibles: {', '.join(entity.metrics)})."
        )
    dimensions = _resolve_dimensions(query, entity)

    pc = _ParamCounter()
    required_joins: set[str] = set()
    select_parts: list[str] = []
    labels: dict[str, str] = {}
    group_exprs: list[str] = []

    for d in dimensions:
        ddef = entity.dimensions[d]
        required_joins.update(ddef.requires)
        select_parts.append(f'{ddef.sql} AS "{d}"')
        group_exprs.append(ddef.sql)
        labels[d] = ddef.label
    for m in metrics:
        mdef = entity.metrics[m]
        required_joins.update(mdef.requires)
        select_parts.append(f'{mdef.sql} AS "{m}"')
        labels[m] = mdef.label

    where = _build_where(query, entity, pc, required_joins)
    joins = _emit_joins(entity, required_joins)
    valid_aliases = set(dimensions) | set(metrics)

    sql = f"SELECT {', '.join(select_parts)}\nFROM {entity.base_table}{joins}"
    if where:
        sql += f"\nWHERE {where}"
    if group_exprs:
        sql += "\nGROUP BY " + ", ".join(group_exprs)
    sql += _order_clause(query, valid_aliases)
    sql += f"\nLIMIT {_clamp(query.limite, entity.aggregate_max_rows)}"

    return CompiledQuery(sql=sql, params=pc.params, select_labels=labels)


def _compile_detail(query: SemanticQuery, entity: SemanticEntity) -> CompiledQuery:
    fields = _resolve_fields(query, entity)

    pc = _ParamCounter()
    required_joins: set[str] = set()
    select_parts: list[str] = []
    labels: dict[str, str] = {}
    for c in fields:
        fdef = entity.fields[c]
        required_joins.update(fdef.requires)
        select_parts.append(f'{fdef.sql} AS "{c}"')
        labels[c] = fdef.label

    where = _build_where(query, entity, pc, required_joins)
    joins = _emit_joins(entity, required_joins)

    sql = f"SELECT {', '.join(select_parts)}\nFROM {entity.base_table}{joins}"
    if where:
        sql += f"\nWHERE {where}"
    sql += _order_clause(query, set(fields))
    sql += f"\nLIMIT {_clamp(query.limite, entity.detail_max_rows)}"

    return CompiledQuery(sql=sql, params=pc.params, select_labels=labels)


def _compile_record(query: SemanticQuery, entity: SemanticEntity) -> CompiledQuery:
    if entity.record_key is None:
        raise InvalidQueryError(
            f"La entidad '{entity.name}' no soporta el modo 'registro'."
        )
    has_key_filter = any(f.campo == entity.record_key for f in query.filtros)
    if not has_key_filter:
        raise InvalidQueryError(
            f"El modo 'registro' requiere un filtro sobre '{entity.record_key}' "
            "para identificar un único registro."
        )
    fields = _resolve_fields(query, entity)

    pc = _ParamCounter()
    required_joins: set[str] = set()
    select_parts: list[str] = []
    labels: dict[str, str] = {}
    for c in fields:
        fdef = entity.fields[c]
        required_joins.update(fdef.requires)
        select_parts.append(f'{fdef.sql} AS "{c}"')
        labels[c] = fdef.label

    where = _build_where(query, entity, pc, required_joins)
    joins = _emit_joins(entity, required_joins)

    sql = f"SELECT {', '.join(select_parts)}\nFROM {entity.base_table}{joins}"
    if where:
        sql += f"\nWHERE {where}"
    sql += "\nLIMIT 1"

    return CompiledQuery(sql=sql, params=pc.params, select_labels=labels)
