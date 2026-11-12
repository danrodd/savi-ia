"""Las consultas al esquema no se guardan como conjunto ni llegan al chat."""

from __future__ import annotations

import pytest

from app.modules.chat.infrastructure.llm.tools.consultar_libre import is_schema_lookup


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
