"""Reproduce el bug real de fechas contra un Postgres real (asyncpg).

Con SQLite, un `str` como bind param de una columna DATE se convierte solo:
el bug queda invisible. asyncpg es estricto — rechaza el string con
`DataError: invalid input for query argument $1 (expected a datetime.date
or datetime.datetime instance, got 'str')` — que es exactamente lo que
tiró la consulta a `ventas` en las pruebas con Claude (52 fallos, ver
`docs/hallazgos-pruebas-proveedores.md`).

Se salta si no hay un Postgres alcanzable en `localhost:5432` con
`postgres`/`1234` (mismo host que `test_postgres_connection_tester.py`).
Crea y borra su propia tabla de prueba; no toca ninguna base de un cliente.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.modules.data_query.application.query_compiler import compile_query
from app.modules.data_query.domain.semantic_model import (
    FilterDef,
    MetricDef,
    SemanticEntity,
)
from app.modules.data_query.domain.semantic_query import (
    FilterOp,
    QueryFilter,
    QueryMode,
    SemanticQuery,
)

_HOST = "localhost"
_PORT = 5432
_USER = "postgres"
_PASSWORD = "1234"

_ENTIDAD = SemanticEntity(
    name="ventas_test",
    base_table='"ventas_test"',
    metrics={"total": MetricDef("total", "SUM(total)", "Total")},
    filters={
        "fecha": FilterDef("fecha", '"fecha"', (FilterOp.GTE, FilterOp.BETWEEN), value_type="date"),
        "cliente_id": FilterDef("cliente_id", '"cliente_id"', (FilterOp.EQ,), value_type="number"),
        "activo": FilterDef("activo", '"activo"', (FilterOp.EQ,), value_type="bool"),
    },
)


@pytest_asyncio.fixture
async def temp_table() -> AsyncIterator[AsyncEngine]:
    try:
        admin = await asyncpg.connect(
            host=_HOST,
            port=_PORT,
            user=_USER,
            password=_PASSWORD,
            database="postgres",
            timeout=3,
        )
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"No hay Postgres alcanzable en {_HOST}:{_PORT}: {e}")
    name = f"test_date_filter_{uuid4().hex[:12]}"
    await admin.execute(f'CREATE DATABASE "{name}"')
    await admin.close()

    engine = create_async_engine(f"postgresql+asyncpg://{_USER}:{_PASSWORD}@{_HOST}:{_PORT}/{name}")
    async with engine.begin() as conn:
        # Los tipos importan: `bigint` y `boolean` son justo donde asyncpg
        # rechaza un string, igual que `date`.
        await conn.execute(
            text(
                'CREATE TABLE "ventas_test" ('
                "fecha DATE NOT NULL, total NUMERIC NOT NULL, "
                "cliente_id BIGINT NOT NULL, activo BOOLEAN NOT NULL)"
            )
        )
        await conn.execute(
            text('INSERT INTO "ventas_test" VALUES (:f, :t, :c, :a)'),
            {"f": date(2026, 3, 15), "t": 1000, "c": 12345, "a": True},
        )
    try:
        yield engine
    finally:
        await engine.dispose()
        admin = await asyncpg.connect(
            host=_HOST,
            port=_PORT,
            user=_USER,
            password=_PASSWORD,
            database="postgres",
            timeout=3,
        )
        await admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        await admin.close()


@pytest.mark.asyncio
async def test_date_filter_binds_against_real_asyncpg(temp_table: AsyncEngine) -> None:
    """Antes del fix, `flt.valor` viajaba como str y esto tiraba
    `asyncpg.exceptions.DataError`. Ahora `compile_query` lo convierte a
    `datetime.date` y el bind funciona."""
    query = SemanticQuery(
        entidad="ventas_test",
        modo=QueryMode.AGGREGATE,
        metricas=["total"],
        filtros=[QueryFilter("fecha", FilterOp.GTE, "2026-01-01")],
    )
    compiled = compile_query(query, _ENTIDAD)

    async with temp_table.connect() as conn:
        result = await conn.execute(text(compiled.sql), compiled.params)
        row = result.mappings().one()

    assert float(row["total"]) == 1000.0


@pytest.mark.asyncio
async def test_number_filter_binds_against_a_bigint_column(temp_table: AsyncEngine) -> None:
    """Sin conversión, `'12345'` contra `BIGINT` tira
    `DataError: 'str' object cannot be interpreted as an integer`."""
    query = SemanticQuery(
        entidad="ventas_test",
        modo=QueryMode.AGGREGATE,
        metricas=["total"],
        filtros=[QueryFilter("cliente_id", FilterOp.EQ, "12345")],
    )
    compiled = compile_query(query, _ENTIDAD)

    async with temp_table.connect() as conn:
        result = await conn.execute(text(compiled.sql), compiled.params)
        row = result.mappings().one()

    assert float(row["total"]) == 1000.0


@pytest.mark.asyncio
async def test_bool_filter_binds_against_a_boolean_column(temp_table: AsyncEngine) -> None:
    """Sin conversión, `'true'` contra `BOOLEAN` tira `DataError` — y `1`
    tampoco cuela: asyncpg no acepta enteros donde espera booleano."""
    query = SemanticQuery(
        entidad="ventas_test",
        modo=QueryMode.AGGREGATE,
        metricas=["total"],
        filtros=[QueryFilter("activo", FilterOp.EQ, "true")],
    )
    compiled = compile_query(query, _ENTIDAD)

    async with temp_table.connect() as conn:
        result = await conn.execute(text(compiled.sql), compiled.params)
        row = result.mappings().one()

    assert float(row["total"]) == 1000.0
