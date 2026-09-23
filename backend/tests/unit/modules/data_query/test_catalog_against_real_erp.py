"""El catálogo REAL contra el schema REAL del ERP, de punta a punta.

Los otros tests de `data_query` usan entidades sintéticas: prueban el
compilador, no el catálogo. Este cierra el hueco — compila las entidades
que realmente usa SAVI (`ventas`, `terceros`, con sus joins, base_filters
y nombres de columna entre comillas) y las ejecuta contra la base del ERP.

Es el test que atrapa un nombre de columna mal escrito en el catálogo:
un typo ahí no lo ve ni Ruff ni Pyright ni ningún test con tablas
inventadas — solo revienta en producción cuando un usuario pregunta.

Se salta si no hay un ERP de desarrollo alcanzable, con el mismo criterio
que `test_postgres_connection_tester.py`: credenciales locales fijas, no
las del `.env` del desarrollador (la suite las pisa a propósito en
`tests/conftest.py` para no depender de la máquina de cada uno).

Solo hace SELECT: no escribe nada.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from app.modules.data_query.application.query_compiler import compile_query
from app.modules.data_query.domain.semantic_query import (
    FilterOp,
    QueryFilter,
    QueryMode,
    SemanticQuery,
)
from app.modules.data_query.infrastructure.catalog import get_entity

_HOST = "localhost"
_PORT = 5432
_USER = "postgres"
_PASSWORD = "1234"
# Un ERP por cliente. El catálogo es UNO para todos, así que tiene que
# funcionar contra los tres: cuando corría solo contra farmacias_similares
# se escaparon dos bugs que solo existían en los otros (nombres vacíos de
# personas naturales y un `tipoDocumento` sin mapear).
_DATABASES = ("farmacias_similares", "frami", "sur_andina")


@pytest.fixture(params=_DATABASES)
def erp_name(request: pytest.FixtureRequest) -> str:
    return str(request.param)


@pytest_asyncio.fixture
async def erp_engine(erp_name: str) -> AsyncIterator[AsyncEngine]:
    url = f"postgresql+asyncpg://{_USER}:{_PASSWORD}@{_HOST}:{_PORT}/{erp_name}"
    # `NullPool`: cada test de pytest-asyncio corre en su propio event loop y
    # una conexión pooleada de asyncpg no sobrevive el cambio — se cae con
    # "connection was closed in the middle of operation".
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as e:  # noqa: BLE001
        await engine.dispose()
        pytest.skip(f"ERP no alcanzable: {e}")
    try:
        yield engine
    finally:
        await engine.dispose()


async def _run(engine: AsyncEngine, query: SemanticQuery) -> list[dict[str, Any]]:
    entity = get_entity(query.entidad)
    assert entity is not None, f"'{query.entidad}' no está en el catálogo"
    compiled = compile_query(query, entity)
    async with engine.connect() as conn:
        result = await conn.execute(text(compiled.sql), compiled.params)
        return [dict(row) for row in result.mappings()]


@pytest.mark.asyncio
async def test_ventas_with_a_date_range_runs_against_the_real_schema(
    erp_engine: AsyncEngine,
) -> None:
    """La consulta que rompía siempre antes del fix de tipado: ventas
    agregadas por mes, acotadas por un rango de fechas."""
    query = SemanticQuery(
        entidad="ventas",
        modo=QueryMode.AGGREGATE,
        metricas=["monto_total", "num_facturas"],
        dimensiones=["mes"],
        filtros=[QueryFilter("fecha", FilterOp.BETWEEN, ["2025-06-01", "2025-08-31"])],
    )

    rows = await _run(erp_engine, query)

    assert rows, "el período de prueba debería traer datos del ERP de desarrollo"
    assert "monto_total" in rows[0]
    assert "mes" in rows[0]


@pytest.mark.asyncio
async def test_ventas_detalle_by_product_runs_with_its_joins(
    erp_engine: AsyncEngine,
) -> None:
    """`ventas_detalle` emite joins encadenados (detalle → producto): un
    orden mal declarado en el catálogo se ve solo ejecutando."""
    query = SemanticQuery(
        entidad="ventas_detalle",
        modo=QueryMode.AGGREGATE,
        metricas=["unidades"],
        dimensiones=["producto"],
        filtros=[QueryFilter("fecha", FilterOp.BETWEEN, ["2025-06-01", "2025-06-30"])],
        limite=5,
    )

    rows = await _run(erp_engine, query)

    assert rows
    assert "producto" in rows[0]


@pytest.mark.asyncio
async def test_cartera_splits_receivables_from_payables(
    erp_engine: AsyncEngine, erp_name: str
) -> None:
    """El caso que motivó la entidad: "cartera vencida" daba números
    distintos según el proveedor de IA porque cada uno decidía por su
    cuenta si incluía las cuentas por pagar. Agrupada por `lado`, la
    respuesta dice de qué está hablando."""
    query = SemanticQuery(
        entidad="cartera",
        modo=QueryMode.AGGREGATE,
        metricas=["saldo_vencido", "documentos"],
        dimensiones=["lado"],
        filtros=[QueryFilter("vencida", FilterOp.EQ, True)],
    )

    rows = await _run(erp_engine, query)

    lados = {str(r["lado"]) for r in rows}
    assert "Por cobrar a clientes" in lados
    assert "Por pagar a proveedores" in lados
    # Las notas crédito NO se suman a lo por cobrar: tienen saldo positivo
    # pero reducen la deuda del cliente, así que van en su propio bucket.
    # Solo farmacias_similares emite notas crédito con saldo vivo.
    if erp_name == "farmacias_similares":
        assert "Notas crédito a clientes" in lados
    assert all(float(r["saldo_vencido"]) >= 0 for r in rows)


@pytest.mark.asyncio
async def test_cartera_by_type_covers_every_document_kind(erp_engine: AsyncEngine) -> None:
    """Los seis `tipoDocumento` tienen etiqueta: ninguno cae en
    'Sin clasificar', que es la señal de que apareció uno nuevo."""
    query = SemanticQuery(
        entidad="cartera",
        modo=QueryMode.AGGREGATE,
        metricas=["saldo"],
        dimensiones=["tipo"],
        limite=20,
    )

    rows = await _run(erp_engine, query)

    assert rows
    sin_clasificar = [r for r in rows if str(r["tipo"]) == "Sin clasificar"]
    assert not sin_clasificar, (
        "apareció un tipoDocumento no mapeado en cartera.py — hay que "
        f"identificarlo y agregarlo: {sin_clasificar}"
    )


@pytest.mark.asyncio
async def test_cartera_by_tercero_emits_its_join(erp_engine: AsyncEngine) -> None:
    """La dimensión `tercero` necesita el join a `Tercero.Tercero`."""
    query = SemanticQuery(
        entidad="cartera",
        modo=QueryMode.AGGREGATE,
        metricas=["saldo"],
        dimensiones=["tercero"],
        filtros=[QueryFilter("tipo_documento", FilterOp.EQ, "2")],
        limite=5,
    )

    rows = await _run(erp_engine, query)

    assert rows
    assert "tercero" in rows[0]


@pytest.mark.asyncio
async def test_terceros_with_a_boolean_filter_runs(erp_engine: AsyncEngine) -> None:
    """Filtro booleano contra la columna real: el modelo escribe "true"
    como texto y antes del fix asyncpg lo rechazaba."""
    query = SemanticQuery(
        entidad="terceros",
        modo=QueryMode.AGGREGATE,
        metricas=["cantidad"],
        filtros=[QueryFilter("es_cliente", FilterOp.EQ, "true")],
    )

    rows = await _run(erp_engine, query)

    assert rows
    assert int(rows[0]["cantidad"]) > 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("entidad", "dimension", "metrica"),
    [
        ("ventas", "cliente", "monto_total"),
        ("cartera", "tercero", "saldo"),
    ],
)
async def test_every_tercero_resolves_to_a_name(
    erp_engine: AsyncEngine, entidad: str, dimension: str, metrica: str
) -> None:
    """Ningún tercero agrupado queda sin nombre.

    El ERP guarda los campos vacíos como '' y no como NULL. Cuando el
    nombre no saltaba un `razonSocial` vacío, las personas naturales
    resolvían a '' y el GROUP BY las fundía en una sola fila: en frami esa
    fila "sin nombre" era el cliente #1 con el 61% de la facturación.
    """
    query = SemanticQuery(
        entidad=entidad,
        modo=QueryMode.AGGREGATE,
        metricas=[metrica],
        dimensiones=[dimension],
        filtros=(
            [QueryFilter("lado", FilterOp.CONTAINS, "clientes")] if entidad == "cartera" else []
        ),
        limite=1000,
    )

    rows = await _run(erp_engine, query)

    assert rows
    sin_nombre = [r for r in rows if not str(r[dimension] or "").strip()]
    assert not sin_nombre, f"terceros sin nombre: {sin_nombre[:3]}"
