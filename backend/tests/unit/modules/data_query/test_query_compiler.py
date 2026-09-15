"""Compilador de `consultar_datos`: del objeto que arma el modelo al SQL.

Es la otra frontera que decide qué SQL toca el ERP, y tampoco tenía tests. La
garantía a sostener: **los identificadores salen de un catálogo cerrado y los
valores viajan como parámetros**, así lo que el modelo escriba en un filtro no
puede cambiar la forma de la consulta.
"""

from __future__ import annotations

import pytest

from app.modules.data_query.application.query_compiler import compile_query
from app.modules.data_query.domain.exceptions import (
    InvalidQueryError,
    UnknownFieldError,
)
from app.modules.data_query.domain.semantic_model import (
    DimensionDef,
    FieldDef,
    FilterDef,
    JoinDef,
    MetricDef,
    SemanticEntity,
)
from app.modules.data_query.domain.semantic_query import (
    FilterOp,
    QueryFilter,
    QueryMode,
    SemanticQuery,
    SortSpec,
)

ENTIDAD = SemanticEntity(
    name="ventas",
    base_table='"Venta"."Factura" f',
    metrics={
        "total": MetricDef("total", 'SUM(f."total")', "Total"),
        "cantidad": MetricDef("cantidad", "COUNT(*)", "Cantidad"),
        "con_join": MetricDef("con_join", 'SUM(d."cant")', "Con join", requires=("detalle",)),
    },
    dimensions={
        "mes": DimensionDef("mes", "DATE_TRUNC('month', f.\"fecha\")", "Mes"),
        "cliente": DimensionDef("cliente", 't."nombre"', "Cliente", requires=("tercero",)),
    },
    fields={
        "numero": FieldDef("numero", 'f."numero"', "Número"),
        "fecha": FieldDef("fecha", 'f."fecha"', "Fecha"),
    },
    filters={
        "fecha": FilterDef("fecha", 'f."fecha"', (FilterOp.BETWEEN, FilterOp.GTE)),
        "cliente": FilterDef("cliente", 't."nombre"', (FilterOp.CONTAINS, FilterOp.EQ)),
        "numero": FilterDef("numero", 'f."numero"', (FilterOp.EQ,)),
        "estado": FilterDef("estado", 'f."estado"', (FilterOp.IN,)),
    },
    joins={
        "tercero": JoinDef("tercero", 'JOIN "Tercero" t ON t."id" = f."idTercero"'),
        "detalle": JoinDef("detalle", 'JOIN "Detalle" d ON d."idFactura" = f."id"'),
    },
    base_filters=('f."anulada" = false',),
    aggregate_max_rows=100,
    detail_max_rows=30,
    record_key="numero",
)


def _agregado(**kwargs: object) -> SemanticQuery:
    base: dict[str, object] = {
        "entidad": "ventas",
        "modo": QueryMode.AGGREGATE,
        "metricas": ["total"],
    }
    return SemanticQuery(**{**base, **kwargs})  # pyright: ignore[reportArgumentType]


# ── Lo que el modelo NO puede elegir ─────────────────────────────────────


def test_unknown_metric_is_rejected() -> None:
    with pytest.raises(UnknownFieldError):
        compile_query(_agregado(metricas=["inventada"]), ENTIDAD)


def test_unknown_dimension_is_rejected() -> None:
    with pytest.raises(UnknownFieldError):
        compile_query(_agregado(dimensiones=["inventada"]), ENTIDAD)


def test_unknown_filter_is_rejected() -> None:
    query = _agregado(filtros=[QueryFilter("inventado", FilterOp.EQ, "x")])

    with pytest.raises(UnknownFieldError):
        compile_query(query, ENTIDAD)


def test_operator_not_allowed_for_the_filter_is_rejected() -> None:
    """`numero` solo admite `=`: pedirle un rango es un error, no un `BETWEEN`
    improvisado."""
    query = _agregado(filtros=[QueryFilter("numero", FilterOp.BETWEEN, [1, 9])])

    with pytest.raises(Exception, match="(?i)operador|permitid"):
        compile_query(query, ENTIDAD)


def test_aggregate_without_metrics_is_rejected() -> None:
    with pytest.raises(InvalidQueryError):
        compile_query(_agregado(metricas=[]), ENTIDAD)


# ── Los valores viajan como parámetros ───────────────────────────────────


def test_filter_values_are_bound_not_interpolated() -> None:
    """Lo importante de todo este módulo: un valor no puede cambiar la forma
    de la consulta."""
    malicioso = '\'; DROP TABLE "Factura"; --'
    query = _agregado(filtros=[QueryFilter("cliente", FilterOp.EQ, malicioso)])

    compilada = compile_query(query, ENTIDAD)

    assert "DROP TABLE" not in compilada.sql
    assert malicioso in compilada.params.values()


def test_contains_wraps_the_value_with_wildcards() -> None:
    query = _agregado(filtros=[QueryFilter("cliente", FilterOp.CONTAINS, "acme")])

    compilada = compile_query(query, ENTIDAD)

    assert "ILIKE" in compilada.sql.upper()
    assert "%acme%" in compilada.params.values()


def test_between_needs_two_values() -> None:
    query = _agregado(filtros=[QueryFilter("fecha", FilterOp.BETWEEN, ["2026-01-01"])])

    with pytest.raises(InvalidQueryError, match="entre"):
        compile_query(query, ENTIDAD)


def test_in_with_no_values_is_rejected() -> None:
    query = _agregado(filtros=[QueryFilter("estado", FilterOp.IN, [])])

    with pytest.raises(InvalidQueryError, match="en"):
        compile_query(query, ENTIDAD)


def test_in_binds_every_value() -> None:
    query = _agregado(filtros=[QueryFilter("estado", FilterOp.IN, ["A", "B", "C"])])

    compilada = compile_query(query, ENTIDAD)

    assert len(compilada.params) == 3
    assert set(compilada.params.values()) == {"A", "B", "C"}


# ── Topes y forma del SQL ────────────────────────────────────────────────


def test_limit_is_capped_by_the_entity() -> None:
    compilada = compile_query(_agregado(limite=99999), ENTIDAD)

    assert "LIMIT 100" in compilada.sql


def test_detail_mode_has_its_own_cap() -> None:
    query = SemanticQuery(entidad="ventas", modo=QueryMode.DETAIL, campos=["numero"], limite=99999)

    compilada = compile_query(query, ENTIDAD)

    assert "LIMIT 30" in compilada.sql


def test_base_filters_are_always_applied() -> None:
    """La factura anulada no se cuenta aunque el modelo no lo pida."""
    compilada = compile_query(_agregado(), ENTIDAD)

    assert 'f."anulada" = false' in compilada.sql


def test_joins_are_emitted_only_when_needed() -> None:
    sin_join = compile_query(_agregado(), ENTIDAD)
    con_join = compile_query(_agregado(dimensiones=["cliente"]), ENTIDAD)

    assert "JOIN" not in sin_join.sql
    assert '"Tercero"' in con_join.sql


def test_sort_by_a_column_not_selected_is_ignored() -> None:
    """El modelo a veces pide ordenar por algo que no trajo: se ignora en
    silencio en lugar de romper el turno."""
    query = _agregado(orden=SortSpec("inventada", "desc"))

    compilada = compile_query(query, ENTIDAD)

    assert "ORDER BY" not in compilada.sql.upper()


def test_sort_by_a_selected_alias_works() -> None:
    compilada = compile_query(_agregado(orden=SortSpec("total", "desc")), ENTIDAD)

    assert "ORDER BY" in compilada.sql.upper()
    assert "DESC" in compilada.sql.upper()


def test_record_mode_requires_the_key_filter() -> None:
    query = SemanticQuery(entidad="ventas", modo=QueryMode.RECORD, campos=["numero"])

    with pytest.raises(InvalidQueryError, match="registro"):
        compile_query(query, ENTIDAD)


def test_record_mode_with_the_key_filter_compiles() -> None:
    query = SemanticQuery(
        entidad="ventas",
        modo=QueryMode.RECORD,
        campos=["numero", "fecha"],
        filtros=[QueryFilter("numero", FilterOp.EQ, "F-001")],
    )

    compilada = compile_query(query, ENTIDAD)

    assert "F-001" in compilada.params.values()
