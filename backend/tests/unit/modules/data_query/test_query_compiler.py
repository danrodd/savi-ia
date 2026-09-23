"""Compilador de `consultar_datos`: del objeto que arma el modelo al SQL.

Es la otra frontera que decide qué SQL toca el ERP, y tampoco tenía tests. La
garantía a sostener: **los identificadores salen de un catálogo cerrado y los
valores viajan como parámetros**, así lo que el modelo escriba en un filtro no
puede cambiar la forma de la consulta.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

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
        "fecha": FilterDef(
            "fecha", 'f."fecha"', (FilterOp.BETWEEN, FilterOp.GTE), value_type="date"
        ),
        "cliente": FilterDef("cliente", 't."nombre"', (FilterOp.CONTAINS, FilterOp.EQ)),
        "numero": FilterDef("numero", 'f."numero"', (FilterOp.EQ,)),
        "estado": FilterDef("estado", 'f."estado"', (FilterOp.IN,)),
        "cliente_id": FilterDef(
            "cliente_id", 'f."idTercero"', (FilterOp.EQ, FilterOp.IN), value_type="number"
        ),
        "activo": FilterDef("activo", 't."activo"', (FilterOp.EQ,), value_type="bool"),
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


def test_the_applied_limit_travels_with_the_query() -> None:
    """El executor lo necesita para avisar que el resultado se cortó.

    Sin esto el modelo recibía N filas sin saber si eran todas, sumaba esa
    página y la presentaba como total del negocio — medido: $82 M sobre 19
    documentos cuando el total real eran $9.120 M sobre 1.491.
    """
    assert compile_query(_agregado(limite=99999), ENTIDAD).limit == 100
    assert compile_query(_agregado(limite=5), ENTIDAD).limit == 5

    detalle = SemanticQuery(
        entidad="ventas", modo=QueryMode.DETAIL, campos=["numero"], limite=99999
    )
    assert compile_query(detalle, ENTIDAD).limit == 30


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


# ── Filtros tipados: fechas se convierten, no se bindean como texto ──────
#
# Regresión del bug real de las pruebas con Claude: el LLM manda fechas como
# string ISO ("2026-03-01"), y asyncpg rechaza un string donde espera un
# `datetime.date`. El compilador tiene que convertir según `value_type`,
# no confiar en el tipo que trajo el filtro.


def test_date_filter_value_is_coerced_to_a_date_object() -> None:
    query = _agregado(filtros=[QueryFilter("fecha", FilterOp.GTE, "2026-03-01")])

    compilada = compile_query(query, ENTIDAD)

    assert date(2026, 3, 1) in compilada.params.values()
    assert "2026-03-01" not in compilada.params.values()


def test_date_filter_between_includes_the_whole_last_day() -> None:
    """`entre 2025-01-01 y 2025-12-31` incluye TODO el 31 de diciembre.

    Las columnas de fecha del ERP son timestamp con hora: un `BETWEEN` con
    '2025-12-31' corta en la medianoche y deja afuera el último día. Se
    compila como rango semiabierto hasta el día siguiente.
    """
    query = _agregado(
        filtros=[QueryFilter("fecha", FilterOp.BETWEEN, ["2025-01-01", "2025-12-31"])]
    )

    compilada = compile_query(query, ENTIDAD)

    assert "BETWEEN" not in compilada.sql
    assert 'f."fecha" >= ' in compilada.sql
    assert 'f."fecha" < ' in compilada.sql
    assert date(2025, 1, 1) in compilada.params.values()
    assert date(2026, 1, 1) in compilada.params.values()


_ENTIDAD_FECHAS = replace(
    ENTIDAD,
    filters={
        **ENTIDAD.filters,
        "fecha": FilterDef(
            "fecha",
            'f."fecha"',
            (FilterOp.EQ, FilterOp.NE, FilterOp.GT, FilterOp.GTE, FilterOp.LT, FilterOp.LTE),
            value_type="date",
        ),
    },
)


@pytest.mark.parametrize(
    ("op", "fragmento", "fechas"),
    [
        (
            FilterOp.EQ,
            'f."fecha" >= :p0 AND f."fecha" < :p1',
            [date(2026, 8, 31), date(2026, 9, 1)],
        ),
        (FilterOp.NE, 'f."fecha" < :p0 OR f."fecha" >= :p1', [date(2026, 8, 31), date(2026, 9, 1)]),
        (FilterOp.LTE, 'f."fecha" < :p0', [date(2026, 9, 1)]),
        (FilterOp.GT, 'f."fecha" >= :p0', [date(2026, 9, 1)]),
        (FilterOp.GTE, 'f."fecha" >= :p0', [date(2026, 8, 31)]),
        (FilterOp.LT, 'f."fecha" < :p0', [date(2026, 8, 31)]),
    ],
)
def test_scalar_date_filter_treats_a_date_as_the_whole_day(
    op: FilterOp, fragmento: str, fechas: list[date]
) -> None:
    query = _agregado(filtros=[QueryFilter("fecha", op, "2026-08-31")])

    compilada = compile_query(query, _ENTIDAD_FECHAS)

    assert fragmento in compilada.sql
    assert list(compilada.params.values()) == fechas


def test_invalid_date_filter_value_raises_actionable_error() -> None:
    query = _agregado(filtros=[QueryFilter("fecha", FilterOp.GTE, "no es una fecha")])

    with pytest.raises(InvalidQueryError, match="AAAA-MM-DD"):
        compile_query(query, ENTIDAD)


def test_text_filter_value_is_not_coerced() -> None:
    """Sin `value_type="date"` el valor viaja tal cual: no todo filtro es fecha."""
    query = _agregado(filtros=[QueryFilter("cliente", FilterOp.EQ, "2026-03-01")])

    compilada = compile_query(query, ENTIDAD)

    assert "2026-03-01" in compilada.params.values()


# ── Filtros numéricos y booleanos ────────────────────────────────────────
#
# Misma clase de bug que las fechas: las columnas del ERP son `bigint` y
# `boolean`, y asyncpg rechaza un string en ambas. Verificado contra
# Postgres real: `'123'` contra bigint y `'true'` contra boolean tiran
# `DataError`. El modelo manda strings con frecuencia, así que sin
# conversión la consulta muere igual que moría con `fecha`.


def test_number_filter_coerces_a_numeric_string_to_int() -> None:
    query = _agregado(filtros=[QueryFilter("cliente_id", FilterOp.EQ, "12345")])

    compilada = compile_query(query, ENTIDAD)

    assert 12345 in compilada.params.values()
    assert "12345" not in compilada.params.values()


def test_number_filter_accepts_an_int_unchanged() -> None:
    query = _agregado(filtros=[QueryFilter("cliente_id", FilterOp.EQ, 99)])

    compilada = compile_query(query, ENTIDAD)

    assert 99 in compilada.params.values()


def test_number_filter_coerces_every_value_of_an_in_list() -> None:
    query = _agregado(filtros=[QueryFilter("cliente_id", FilterOp.IN, ["1", "2", 3])])

    compilada = compile_query(query, ENTIDAD)

    assert set(compilada.params.values()) == {1, 2, 3}


def test_number_filter_rejects_a_non_numeric_value() -> None:
    query = _agregado(filtros=[QueryFilter("cliente_id", FilterOp.EQ, "no soy un número")])

    with pytest.raises(InvalidQueryError, match="número"):
        compile_query(query, ENTIDAD)


def test_number_filter_rejects_a_boolean() -> None:
    """`bool` es subclase de `int`: sin el corte explícito, `True` entraría
    como el número 1 y filtraría por algo que nadie pidió."""
    query = _agregado(filtros=[QueryFilter("cliente_id", FilterOp.EQ, True)])

    with pytest.raises(InvalidQueryError, match="número"):
        compile_query(query, ENTIDAD)


def test_bool_filter_coerces_the_words_the_model_writes() -> None:
    for entrada, esperado in (("true", True), ("sí", True), ("no", False), ("false", False)):
        query = _agregado(filtros=[QueryFilter("activo", FilterOp.EQ, entrada)])

        compilada = compile_query(query, ENTIDAD)

        assert esperado in compilada.params.values(), entrada


def test_bool_filter_accepts_a_real_boolean_unchanged() -> None:
    query = _agregado(filtros=[QueryFilter("activo", FilterOp.EQ, False)])

    compilada = compile_query(query, ENTIDAD)

    assert False in compilada.params.values()


def test_bool_filter_rejects_a_value_that_is_not_yes_or_no() -> None:
    query = _agregado(filtros=[QueryFilter("activo", FilterOp.EQ, "quizás")])

    with pytest.raises(InvalidQueryError, match="booleano"):
        compile_query(query, ENTIDAD)


# ── Entidades que no se pueden sumar sin separar ─────────────────────────
#
# `cartera` junta lo que los clientes deben con lo que la empresa debe: un
# total sin agrupar no significa nada. La regla escrita en la descripción
# de la tool no alcanzó — medido con la misma pregunta, Gemini y OpenAI la
# respetaban y Claude devolvía el total mezclado igual. El compilador lo
# rechaza para que la respuesta no dependa de qué proveedor esté activo.

_AMBIGUA = SemanticEntity(
    name="cartera_test",
    base_table='"Cartera" c',
    metrics={"saldo": MetricDef("saldo", 'SUM(c."saldo")', "Saldo")},
    dimensions={"lado": DimensionDef("lado", 'c."lado"', "Lado")},
    filters={"lado": FilterDef("lado", 'c."lado"', (FilterOp.EQ,))},
    require_dimensions=("lado",),
)


def test_aggregate_without_the_required_dimension_is_rejected() -> None:
    query = SemanticQuery(entidad="cartera_test", modo=QueryMode.AGGREGATE, metricas=["saldo"])

    with pytest.raises(InvalidQueryError, match="no significa nada"):
        compile_query(query, _AMBIGUA)


def test_grouping_by_the_required_dimension_is_enough() -> None:
    query = SemanticQuery(
        entidad="cartera_test",
        modo=QueryMode.AGGREGATE,
        metricas=["saldo"],
        dimensiones=["lado"],
    )

    compilada = compile_query(query, _AMBIGUA)

    assert "GROUP BY" in compilada.sql.upper()


def test_filtering_by_the_required_dimension_is_also_enough() -> None:
    """Si el usuario pidió una sola punta, el scope ya es inequívoco."""
    query = SemanticQuery(
        entidad="cartera_test",
        modo=QueryMode.AGGREGATE,
        metricas=["saldo"],
        filtros=[QueryFilter("lado", FilterOp.EQ, "Clientes")],
    )

    compilada = compile_query(query, _AMBIGUA)

    assert "Clientes" in compilada.params.values()


def test_entities_without_the_rule_are_untouched() -> None:
    """La restricción es opt-in: `ventas` sigue aceptando un total suelto."""
    compilada = compile_query(_agregado(), ENTIDAD)

    assert "SELECT" in compilada.sql.upper()


def test_record_mode_with_the_key_filter_compiles() -> None:
    query = SemanticQuery(
        entidad="ventas",
        modo=QueryMode.RECORD,
        campos=["numero", "fecha"],
        filtros=[QueryFilter("numero", FilterOp.EQ, "F-001")],
    )

    compilada = compile_query(query, ENTIDAD)

    assert "F-001" in compilada.params.values()


# ── `contiene` busca palabras, no la frase literal ────────────────────────


def test_contains_matches_every_word_ignoring_articles() -> None:
    """ "aceite de motor" tiene que encontrar "ACEITE MOTOR 15W40"."""
    query = _agregado(filtros=[QueryFilter("cliente", FilterOp.CONTAINS, "aceite de motor")])

    compilada = compile_query(query, ENTIDAD)

    assert set(compilada.params.values()) == {"%aceite%", "%motor%"}
    assert compilada.sql.count("ILIKE") == 2
    assert " AND " in compilada.sql


def test_contains_drops_the_plural() -> None:
    """ "tornillos" tiene que encontrar "TORNILLO MAD 6 * 2"."""
    query = _agregado(filtros=[QueryFilter("cliente", FilterOp.CONTAINS, "tornillos")])

    compilada = compile_query(query, ENTIDAD)

    assert list(compilada.params.values()) == ["%tornillo%"]


def test_contains_with_only_stopwords_keeps_the_raw_value() -> None:
    query = _agregado(filtros=[QueryFilter("cliente", FilterOp.CONTAINS, "de")])

    compilada = compile_query(query, ENTIDAD)

    assert list(compilada.params.values()) == ["%de%"]
