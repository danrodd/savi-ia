"""Entidades de compras a proveedores.

Tablas `CuentaPagar.FacturaCompra` + `DetalleFacturaCompra` (ver
docs/DB_MAP.md §2.5). Mismo esquema en las tres bases.

Dos entidades con granos distintos, como `ventas`, para no inflar sumas:
- `compras`: grano FACTURA. Totales comprados, número de facturas, por
  proveedor o periodo.
- `compras_detalle`: grano LÍNEA. Unidades y montos por producto o bodega.

Lo que se le DEBE a cada proveedor no está acá: es cartera (lado
'proveedores'). Compras responde qué se compró, cuándo y a quién.
"""

from __future__ import annotations

from app.modules.data_query.domain.semantic_model import (
    DimensionDef,
    FieldDef,
    FilterDef,
    JoinDef,
    MetricDef,
    SemanticEntity,
)
from app.modules.data_query.domain.semantic_query import FilterOp
from app.modules.data_query.infrastructure.catalog._names import tercero_display_name

_PROVEEDOR_NAME = tercero_display_name()

_DATE = (FilterOp.BETWEEN, FilterOp.GTE, FilterOp.LTE, FilterOp.EQ)

_TERCERO_JOIN = JoinDef(
    "tercero",
    'JOIN "Tercero"."Tercero" t ON t."idTercero" = fc."idTercero"',
)


# ── Entidad: compras (grano factura) ────────────────────────────────────
COMPRAS = SemanticEntity(
    name="compras",
    base_table='"CuentaPagar"."FacturaCompra" fc',
    base_filters=('fc."anulada" = false',),
    required_modules=("CUENTAPAGAR",),
    description=(
        "Facturas de compra a proveedores (cabecera). Úsala para 'cuánto le "
        "compramos al proveedor X', 'cuánto compramos en marzo' y 'principales "
        "proveedores'. Para lo que se le DEBE a un proveedor usá 'cartera'. "
        "Para detalle por PRODUCTO usá 'compras_detalle'."
    ),
    joins={"tercero": _TERCERO_JOIN},
    metrics={
        "monto_total": MetricDef("monto_total", 'SUM(fc."total")', "Total comprado"),
        "num_facturas": MetricDef("num_facturas", "COUNT(*)", "Cantidad de facturas de compra"),
        "subtotal_total": MetricDef("subtotal_total", 'SUM(fc."subtotal")', "Subtotal"),
        "iva_total": MetricDef("iva_total", 'SUM(fc."valorIva")', "IVA de las compras"),
    },
    dimensions={
        "dia": DimensionDef("dia", "DATE_TRUNC('day', fc.\"fecha\")", "Día"),
        "mes": DimensionDef("mes", "DATE_TRUNC('month', fc.\"fecha\")", "Mes"),
        "anio": DimensionDef("anio", "DATE_TRUNC('year', fc.\"fecha\")", "Año"),
        "proveedor": DimensionDef("proveedor", _PROVEEDOR_NAME, "Proveedor", requires=("tercero",)),
    },
    fields={
        "numero": FieldDef("numero", 'fc."numero"', "Número"),
        "factura_proveedor": FieldDef(
            "factura_proveedor", 'fc."referenciaFacturaProveedor"', "Factura del proveedor"
        ),
        "fecha": FieldDef("fecha", 'fc."fecha"', "Fecha"),
        "vencimiento": FieldDef("vencimiento", 'fc."fechaVencimiento"', "Vencimiento"),
        "total": FieldDef("total", 'fc."total"', "Total"),
        "proveedor": FieldDef("proveedor", _PROVEEDOR_NAME, "Proveedor", requires=("tercero",)),
    },
    filters={
        "fecha": FilterDef("fecha", 'fc."fecha"', _DATE, value_type="date"),
        "proveedor": FilterDef(
            "proveedor", _PROVEEDOR_NAME, (FilterOp.CONTAINS,), requires=("tercero",)
        ),
        "proveedor_id": FilterDef(
            "proveedor_id", 'fc."idTercero"', (FilterOp.EQ, FilterOp.IN), value_type="number"
        ),
        "numero": FilterDef("numero", 'fc."numero"', (FilterOp.EQ,), value_type="number"),
        "factura_proveedor": FilterDef(
            "factura_proveedor", 'fc."referenciaFacturaProveedor"', (FilterOp.EQ,)
        ),
    },
    record_key="numero",
)


# ── Entidad: compras_detalle (grano línea) ──────────────────────────────
COMPRAS_DETALLE = SemanticEntity(
    name="compras_detalle",
    base_table=(
        '"CuentaPagar"."FacturaCompra" fc\n'
        'JOIN "CuentaPagar"."DetalleFacturaCompra" df '
        'ON df."idFacturaCompra" = fc."idFacturaCompra"'
    ),
    base_filters=('fc."anulada" = false',),
    required_modules=("CUENTAPAGAR",),
    description=(
        "Líneas de compra (por producto). Úsala para 'cuántas unidades de X "
        "compramos', 'qué productos le compramos al proveedor Y' y costo "
        "unitario de compra. Para totales de factura usá 'compras'."
    ),
    joins={
        "producto": JoinDef(
            "producto",
            'JOIN "Inventario"."Producto" p ON p."idProducto" = df."idProducto"',
        ),
        "almacen": JoinDef(
            "almacen",
            'JOIN "Inventario"."Almacen" a ON a."idAlmacen" = df."idAlmacen"',
        ),
        "tercero": _TERCERO_JOIN,
    },
    metrics={
        "unidades": MetricDef("unidades", 'SUM(df."cantidad")', "Unidades compradas"),
        "monto_lineas": MetricDef("monto_lineas", 'SUM(df."total")', "Monto de líneas"),
        # Ponderado por cantidad: el promedio simple de precios le da el
        # mismo peso a una línea de 1 unidad que a una de 1.000.
        "costo_unitario_promedio": MetricDef(
            "costo_unitario_promedio",
            'SUM(df."subtotal") / NULLIF(SUM(df."cantidad"), 0)',
            "Costo unitario promedio",
        ),
    },
    dimensions={
        "producto": DimensionDef("producto", 'p."descripcion"', "Producto", requires=("producto",)),
        "sucursal": DimensionDef(
            "sucursal", 'a."descripcion"', "Sucursal / bodega", requires=("almacen",)
        ),
        "mes": DimensionDef("mes", "DATE_TRUNC('month', fc.\"fecha\")", "Mes"),
        "proveedor": DimensionDef("proveedor", _PROVEEDOR_NAME, "Proveedor", requires=("tercero",)),
    },
    fields={},  # entidad analítica: sin modo detalle/registro
    filters={
        "fecha": FilterDef("fecha", 'fc."fecha"', _DATE, value_type="date"),
        "producto": FilterDef(
            "producto", 'p."descripcion"', (FilterOp.CONTAINS,), requires=("producto",)
        ),
        "producto_id": FilterDef(
            "producto_id", 'df."idProducto"', (FilterOp.EQ, FilterOp.IN), value_type="number"
        ),
        "proveedor": FilterDef(
            "proveedor", _PROVEEDOR_NAME, (FilterOp.CONTAINS,), requires=("tercero",)
        ),
        "proveedor_id": FilterDef(
            "proveedor_id", 'fc."idTercero"', (FilterOp.EQ,), value_type="number"
        ),
    },
)
