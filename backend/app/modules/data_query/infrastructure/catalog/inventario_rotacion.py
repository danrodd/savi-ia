"""Entidad de rotación: existencias con su última venta y su última compra.

POR QUÉ EXISTE
--------------
En la demo del 2026-11-11 el usuario pidió "las llantas que no han rotado y
tienen existencias". El modelo pidió el inventario (cortado), las ventas por
referencia (cortadas) y cruzó las dos muestras: dejó por fuera la MICHELIN
FORCE LTX, que llevaba más de un año quieta. Además inventó el criterio
("exactamente 1 unidad vendida").

Acá el cruce lo hace la base, completo, en una sola consulta, y el criterio es
explícito: `dias_sin_venta`. Ver `docs/plataforma/11-resultados-completos.md`.

CÓMO SE CALCULA
---------------
- Existencia: la suma del último saldo de cada almacén (mismo criterio que la
  entidad `inventario`; el ERP solo escribe el mes con movimiento).
- Última venta: la factura de venta más reciente no anulada con el producto.
- Última y primera compra: igual, con las facturas de compra.
- Días sin venta: desde la última venta; si nunca se vendió, desde la primera
  compra (es el tiempo que lleva en bodega). Sin ventas ni compras, NULL.
"""

from __future__ import annotations

from app.modules.data_query.domain.semantic_model import (
    DimensionDef,
    FieldDef,
    FilterDef,
    MetricDef,
    SemanticEntity,
)
from app.modules.data_query.domain.semantic_query import FilterOp
from app.modules.data_query.infrastructure.catalog._names import product_search_text

_NUMBER_OPS = (FilterOp.GT, FilterOp.GTE, FilterOp.LT, FilterOp.LTE, FilterOp.EQ)
_DATE_OPS = (FilterOp.LT, FilterOp.LTE, FilterOp.GT, FilterOp.GTE, FilterOp.BETWEEN)

_BASE = """"Inventario"."Producto" p
JOIN LATERAL (
    SELECT SUM(ultimo."cantidadActual") AS existencia
    FROM (
        SELECT DISTINCT ON (si."idAlmacen") si."cantidadActual"
        FROM "Inventario"."SaldoInventario" si
        WHERE si."idProducto" = p."idProducto"
        ORDER BY si."idAlmacen", si."anio" DESC, si."mes" DESC
    ) ultimo
) s ON true
LEFT JOIN LATERAL (
    SELECT MAX(f."fecha") AS ultima_venta
    FROM "CuentaCobrar"."DetalleFactura" d
    JOIN "CuentaCobrar"."Factura" f ON f."idFactura" = d."idFactura"
    WHERE d."idProducto" = p."idProducto" AND f."anulada" = false
) v ON true
LEFT JOIN LATERAL (
    SELECT MAX(fc."fecha") AS ultima_compra, MIN(fc."fecha") AS primera_compra
    FROM "CuentaPagar"."DetalleFacturaCompra" df
    JOIN "CuentaPagar"."FacturaCompra" fc ON fc."idFacturaCompra" = df."idFacturaCompra"
    WHERE df."idProducto" = p."idProducto" AND fc."anulada" = false
) c ON true"""

_DAYS_WITHOUT_SALE = "(CURRENT_DATE - COALESCE(v.ultima_venta, c.primera_compra)::date)"

INVENTARIO_ROTACION = SemanticEntity(
    name="inventario_rotacion",
    base_table=_BASE,
    base_filters=('p."tipo" = 0',),
    required_modules=("INVENTARIO",),
    description=(
        "Rotación del inventario: por producto, la existencia actual (todas las "
        "bodegas), la fecha de la última venta, la de la última y la primera compra, "
        "y los días sin venta. Úsala para 'productos sin movimiento', 'baja "
        "rotación', 'inventario quieto' o 'qué compré hace años y sigue en bodega'. "
        "Criterio explícito: filtra por 'dias_sin_venta' (ej. >= 365 para más de un "
        "año) y 'existencia' > 0, y dile al usuario el criterio que usaste. "
        "'dias_sin_venta' cuenta desde la última venta, o desde la primera compra si "
        "el producto nunca se vendió. No incluye servicios."
    ),
    metrics={
        "productos": MetricDef("productos", "COUNT(*)", "Productos"),
        "unidades": MetricDef("unidades", "SUM(s.existencia)", "Unidades en existencia"),
    },
    dimensions={
        "anio_ultima_venta": DimensionDef(
            "anio_ultima_venta", "EXTRACT(YEAR FROM v.ultima_venta)::int", "Año de la última venta"
        ),
    },
    fields={
        "codigo": FieldDef("codigo", 'p."codigo"', "Código"),
        "producto": FieldDef("producto", 'p."descripcion"', "Producto"),
        "existencia": FieldDef("existencia", "s.existencia", "Existencia"),
        "ultima_venta": FieldDef("ultima_venta", "v.ultima_venta::date", "Última venta"),
        "ultima_compra": FieldDef("ultima_compra", "c.ultima_compra::date", "Última compra"),
        "dias_sin_venta": FieldDef("dias_sin_venta", _DAYS_WITHOUT_SALE, "Días sin venta"),
        "primera_compra": FieldDef(
            "primera_compra", "c.primera_compra::date", "Primera compra", default=False
        ),
    },
    filters={
        "producto": FilterDef("producto", product_search_text(), (FilterOp.CONTAINS,)),
        "codigo": FilterDef("codigo", 'p."codigo"', (FilterOp.EQ, FilterOp.CONTAINS)),
        "existencia": FilterDef("existencia", "s.existencia", _NUMBER_OPS, value_type="number"),
        "dias_sin_venta": FilterDef(
            "dias_sin_venta", _DAYS_WITHOUT_SALE, _NUMBER_OPS, value_type="number"
        ),
        "ultima_venta": FilterDef("ultima_venta", "v.ultima_venta", _DATE_OPS, value_type="date"),
        "ultima_compra": FilterDef(
            "ultima_compra", "c.ultima_compra", _DATE_OPS, value_type="date"
        ),
    },
)
