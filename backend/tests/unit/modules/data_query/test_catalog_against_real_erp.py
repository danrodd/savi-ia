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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("palabra", "lado_esperado"),
    [
        ("clientes", "Por cobrar a clientes"),
        ("proveedores", "Por pagar a proveedores"),
    ],
)
async def test_cartera_lado_filter_matches_a_single_bucket(
    erp_engine: AsyncEngine, palabra: str, lado_esperado: str
) -> None:
    """`lado contiene 'clientes'` trae SOLO lo por cobrar.

    Filtraba contra la etiqueta, y "Notas crédito a clientes" también
    contiene 'clientes': "cuánto nos deben los clientes" sumaba las notas
    crédito a lo por cobrar ($2.291 M en vez de $2.194 M en
    farmacias_similares).
    """
    query = SemanticQuery(
        entidad="cartera",
        modo=QueryMode.AGGREGATE,
        metricas=["saldo"],
        dimensiones=["lado"],
        filtros=[QueryFilter("lado", FilterOp.CONTAINS, palabra)],
    )

    rows = await _run(erp_engine, query)

    assert {str(r["lado"]) for r in rows} == {lado_esperado}


@pytest.mark.asyncio
async def test_a_year_range_includes_its_last_day(erp_engine: AsyncEngine) -> None:
    """ "Facturación 2025" = la suma exacta del año, 31 de diciembre incluido.

    `fecha` es timestamptz con hora: con `BETWEEN ... AND '2025-12-31'` el
    último día quedaba afuera (farmacias_similares perdía $17,9 M).
    """
    query = SemanticQuery(
        entidad="ventas",
        modo=QueryMode.AGGREGATE,
        metricas=["monto_total"],
        filtros=[QueryFilter("fecha", FilterOp.BETWEEN, ["2025-01-01", "2025-12-31"])],
    )

    rows = await _run(erp_engine, query)
    async with erp_engine.connect() as conn:
        esperado = await conn.scalar(
            text(
                'SELECT COALESCE(SUM(total), 0) FROM "CuentaCobrar"."Factura" '
                "WHERE anulada = false AND fecha >= '2025-01-01' AND fecha < '2026-01-01'"
            )
        )

    assert float(rows[0]["monto_total"] or 0) == pytest.approx(float(esperado))


# ── Cada columna del catálogo existe en cada ERP ────────────────────────
#
# Los tests de arriba cubren consultas puntuales; estos recorren TODO el
# catálogo. Se escapó así un campo `activo` apuntando a `t."activo"`, que no
# existe (la columna es `estado`): cualquier búsqueda de terceros en modo
# detalle devolvía "problema técnico" y el modelo contestaba que el cliente
# no existía.

_SAMPLE_BY_TYPE: dict[str, Any] = {
    "date": "2025-06-01",
    "number": 1,
    "bool": True,
    "text": "x",
}


def _catalog_entities() -> list[str]:
    from app.modules.data_query.infrastructure.catalog import entity_names

    return entity_names()


def _sample_filter(entidad: str, nombre: str) -> QueryFilter:
    entity = get_entity(entidad)
    assert entity is not None
    fdef = entity.filters[nombre]
    op = fdef.allowed_ops[0]
    valor = _SAMPLE_BY_TYPE[fdef.value_type]
    if op == FilterOp.BETWEEN:
        return QueryFilter(nombre, op, [valor, valor])
    if op == FilterOp.IN:
        return QueryFilter(nombre, op, [valor])
    return QueryFilter(nombre, op, valor)


def _aggregate(entidad: str, **kwargs: Any) -> SemanticQuery:
    entity = get_entity(entidad)
    assert entity is not None
    dimensiones: list[str] = list(kwargs.pop("dimensiones", []))
    if entity.require_dimensions and not set(dimensiones) & set(entity.require_dimensions):
        dimensiones.append(entity.require_dimensions[0])
    return SemanticQuery(
        entidad=entidad,
        modo=QueryMode.AGGREGATE,
        metricas=kwargs.pop("metricas", [next(iter(entity.metrics))]),
        dimensiones=dimensiones,
        limite=1,
        **kwargs,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("entidad", _catalog_entities())
async def test_every_field_exists(erp_engine: AsyncEngine, entidad: str) -> None:
    entity = get_entity(entidad)
    assert entity is not None
    if not entity.fields:
        pytest.skip("sin campos de detalle")
    query = SemanticQuery(
        entidad=entidad, modo=QueryMode.DETAIL, campos=list(entity.fields), limite=1
    )

    await _run(erp_engine, query)


@pytest.mark.asyncio
@pytest.mark.parametrize("entidad", _catalog_entities())
async def test_every_metric_and_dimension_exists(erp_engine: AsyncEngine, entidad: str) -> None:
    entity = get_entity(entidad)
    assert entity is not None

    await _run(erp_engine, _aggregate(entidad, metricas=list(entity.metrics)))
    for dimension in entity.dimensions:
        await _run(erp_engine, _aggregate(entidad, dimensiones=[dimension]))


@pytest.mark.asyncio
@pytest.mark.parametrize("entidad", _catalog_entities())
async def test_every_filter_exists(erp_engine: AsyncEngine, entidad: str) -> None:
    entity = get_entity(entidad)
    assert entity is not None

    for nombre in entity.filters:
        await _run(erp_engine, _aggregate(entidad, filtros=[_sample_filter(entidad, nombre)]))


@pytest.mark.asyncio
async def test_ventas_by_client_name_matches_the_chained_lookup(
    erp_engine: AsyncEngine, erp_name: str
) -> None:
    """ "Cuánto nos compró X" en una consulta da lo mismo que buscar el id
    en `terceros` y filtrar por `cliente_id`."""
    marcador = {
        "farmacias_similares": "FARMA4NF",
        "frami": "MUEBLES PAOLA",
        "sur_andina": "EQUIRENT",
    }[erp_name]
    por_nombre = await _run(
        erp_engine,
        SemanticQuery(
            entidad="ventas",
            modo=QueryMode.AGGREGATE,
            metricas=["monto_total"],
            filtros=[QueryFilter("cliente", FilterOp.CONTAINS, marcador)],
        ),
    )
    async with erp_engine.connect() as conn:
        esperado = await conn.scalar(
            text(
                'SELECT SUM(f.total) FROM "CuentaCobrar"."Factura" f '
                'JOIN "Tercero"."Tercero" t ON t."idTercero" = f."idTercero" '
                "WHERE f.anulada = false AND "
                '(t."nombreComercial" ILIKE :m OR t."razonSocial" ILIKE :m)'
            ),
            {"m": f"%{marcador}%"},
        )

    assert float(por_nombre[0]["monto_total"]) == pytest.approx(float(esperado))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("erp", "busqueda", "patron"),
    [
        ("frami", "tornillos", "%TORNILLO%"),
        ("sur_andina", "aceite de motor", "%ACEITE%MOTOR%"),
    ],
)
async def test_product_search_by_words_matches_how_users_ask(
    erp_engine: AsyncEngine, erp_name: str, erp: str, busqueda: str, patron: str
) -> None:
    """Como pregunta la gente contra cómo están escritos los productos.

    Con la frase literal, "tornillos" en frami traía 49 unidades (solo los
    productos escritos en plural) en vez de 395.507, y "aceite de motor"
    en sur_andina no traía nada.
    """
    if erp_name != erp:
        pytest.skip("el caso es propio de otro cliente")
    rows = await _run(
        erp_engine,
        SemanticQuery(
            entidad="ventas_detalle",
            modo=QueryMode.AGGREGATE,
            metricas=["unidades"],
            filtros=[QueryFilter("producto", FilterOp.CONTAINS, busqueda)],
        ),
    )
    async with erp_engine.connect() as conn:
        esperado = await conn.scalar(
            text(
                'SELECT SUM(d.cantidad) FROM "CuentaCobrar"."Factura" f '
                'JOIN "CuentaCobrar"."DetalleFactura" d ON d."idFactura" = f."idFactura" '
                'JOIN "Inventario"."Producto" p ON p."idProducto" = d."idProducto" '
                "WHERE f.anulada = false AND p.descripcion ILIKE :p"
            ),
            {"p": patron},
        )

    assert esperado
    assert float(rows[0]["unidades"]) == pytest.approx(float(esperado))


# ── Inventario y compras: el número de SAVI contra SQL escrito a mano ───


@pytest.mark.asyncio
async def test_inventario_is_the_latest_balance_of_each_product_and_warehouse(
    erp_engine: AsyncEngine,
) -> None:
    """El ERP solo escribe el mes con movimiento: tomar "el último mes" deja
    afuera la mayoría del stock en frami y sur_andina."""
    rows = await _run(
        erp_engine,
        SemanticQuery(entidad="inventario", modo=QueryMode.AGGREGATE, metricas=["unidades"]),
    )
    async with erp_engine.connect() as conn:
        esperado = (
            await conn.execute(
                text(
                    """
                    SELECT SUM(u."cantidadActual") FROM (
                      SELECT DISTINCT ON (si."idProducto", si."idAlmacen") si."idProducto",
                             si."cantidadActual"
                      FROM "Inventario"."SaldoInventario" si
                      ORDER BY si."idProducto", si."idAlmacen", si.anio DESC, si.mes DESC
                    ) u JOIN "Inventario"."Producto" p ON p."idProducto" = u."idProducto"
                    WHERE p.tipo = 0
                    """
                )
            )
        ).scalar_one()

    assert float(rows[0]["unidades"] or 0) == pytest.approx(float(esperado or 0))


@pytest.mark.asyncio
async def test_inventario_leaves_services_out(erp_engine: AsyncEngine) -> None:
    rows = await _run(
        erp_engine,
        SemanticQuery(
            entidad="inventario",
            modo=QueryMode.AGGREGATE,
            metricas=["unidades"],
            dimensiones=["producto"],
            limite=100,
        ),
    )
    async with erp_engine.connect() as conn:
        servicios = {
            row[0]
            for row in await conn.execute(
                text('SELECT descripcion FROM "Inventario"."Producto" WHERE tipo = 1')
            )
        }

    assert not {row["producto"] for row in rows} & servicios


@pytest.mark.asyncio
async def test_compras_total_matches_the_non_voided_invoices(erp_engine: AsyncEngine) -> None:
    rows = await _run(
        erp_engine,
        SemanticQuery(
            entidad="compras",
            modo=QueryMode.AGGREGATE,
            metricas=["monto_total"],
            filtros=[QueryFilter("fecha", FilterOp.BETWEEN, ["2025-01-01", "2025-12-31"])],
        ),
    )
    async with erp_engine.connect() as conn:
        esperado = (
            await conn.execute(
                text(
                    """
                    SELECT SUM(total) FROM "CuentaPagar"."FacturaCompra"
                    WHERE NOT anulada AND fecha >= '2025-01-01' AND fecha < '2026-01-01'
                    """
                )
            )
        ).scalar_one()

    assert float(rows[0]["monto_total"] or 0) == pytest.approx(float(esperado or 0))


@pytest.mark.asyncio
async def test_compras_by_product_does_not_inflate_the_lines(erp_engine: AsyncEngine) -> None:
    rows = await _run(
        erp_engine,
        SemanticQuery(
            entidad="compras_detalle",
            modo=QueryMode.AGGREGATE,
            metricas=["unidades"],
            filtros=[QueryFilter("fecha", FilterOp.BETWEEN, ["2025-01-01", "2025-12-31"])],
        ),
    )
    async with erp_engine.connect() as conn:
        esperado = (
            await conn.execute(
                text(
                    """
                    SELECT SUM(df.cantidad) FROM "CuentaPagar"."DetalleFacturaCompra" df
                    JOIN "CuentaPagar"."FacturaCompra" fc
                      ON fc."idFacturaCompra" = df."idFacturaCompra"
                    WHERE NOT fc.anulada AND fc.fecha >= '2025-01-01' AND fc.fecha < '2026-01-01'
                    """
                )
            )
        ).scalar_one()

    assert float(rows[0]["unidades"] or 0) == pytest.approx(float(esperado or 0))


@pytest.mark.asyncio
async def test_cartera_scoped_to_receivables_only_returns_the_client_side(
    erp_engine: AsyncEngine,
) -> None:
    """Un usuario con Ventas ve la punta de clientes y nada de proveedores."""
    entity = get_entity("cartera")
    assert entity is not None
    scoped = entity.scoped_for(frozenset({"VENTA"}))
    query = SemanticQuery(
        entidad="cartera", modo=QueryMode.AGGREGATE, metricas=["saldo"], dimensiones=["lado"]
    )
    compiled = compile_query(query, scoped)
    async with erp_engine.connect() as conn:
        rows = [
            dict(r) for r in (await conn.execute(text(compiled.sql), compiled.params)).mappings()
        ]

    lados = {row["lado"] for row in rows}
    assert lados <= {"Por cobrar a clientes", "Notas crédito a clientes"}
    assert "Por pagar a proveedores" not in lados
