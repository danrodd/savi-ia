"""Las consultas al esquema no se guardan como conjunto ni llegan al chat."""

from __future__ import annotations

import pytest

from app.modules.chat.infrastructure.llm.tools.consultar_libre import (
    is_exploration,
    is_schema_lookup,
)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'Factura' LIMIT 50",
        'SELECT "COLUMN_NAME" FROM "INFORMATION_SCHEMA"."COLUMNS" LIMIT 50',
        "select table_name from Information_Schema.tables limit 10",
    ],
)
def test_schema_queries_are_lookups(sql: str) -> None:
    assert is_schema_lookup(sql)


@pytest.mark.parametrize(
    "sql",
    [
        'SELECT "razonSocial" FROM "Tercero"."Tercero" LIMIT 50',
        "SELECT information FROM ventas LIMIT 5",
    ],
)
def test_business_queries_are_not_lookups(sql: str) -> None:
    assert not is_schema_lookup(sql)


_VALUES = 'SELECT DISTINCT "naturaleza" FROM "Contabilidad"."PlanContable"'


def test_a_query_marked_as_exploration_does_not_reach_the_chat() -> None:
    # Prueba del 2026-11-25: dos consultas para ver los valores de "naturaleza"
    # salieron como tarjetas con true/false junto al plan de cuentas.
    assert is_exploration(_VALUES, {"sql": _VALUES, "exploracion": True})


def test_the_answer_query_reaches_the_chat() -> None:
    assert not is_exploration(_VALUES, {"sql": _VALUES})
    # Solo el booleano cuenta: un texto no la oculta.
    assert not is_exploration(_VALUES, {"sql": _VALUES, "exploracion": "true"})
