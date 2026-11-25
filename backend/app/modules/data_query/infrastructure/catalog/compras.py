"""Entidades de compras a proveedores.

Tablas `CuentaPagar.FacturaCompra` + `DetalleFacturaCompra` (ver
docs/DB_MAP.md §2.5). Mismo esquema en las tres bases.

Dos entidades con granos distintos, como `ventas`, para no inflar sumas:
- `compras`: grano FACTURA. Totales comprados, número de facturas, por
  proveedor o periodo.
- `compras_detalle`: grano LÍNEA. Unidades y montos por producto o bodega.

Lo que se le DEBE a cada proveedor no está acá: es cartera (lado
'proveedores'). Compras responde qué se compró, cuándo y a quién.

Las devoluciones en compra (documento de tipo 13) se guardan en la misma
tabla, con total POSITIVO. Hasta el 2026-11-25 se sumaban como compras
(imporllantas: 116,6 M de más). Ahora quedan afuera y tienen su propia
entidad, `devoluciones_compra`.
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
from app.modules.data_query.infrastructure.catalog._iva import (
    iva_fields,
    iva_join,
    iva_metrics,
)
from app.modules.data_query.infrastructure.catalog._names import (
    product_search_text,
    tercero_display_name,
    tercero_full_name,
    tercero_search_text,
)
from app.modules.data_query.infrastructure.catalog._retenciones import (
    retenciones_fields,
    retenciones_join,
    retenciones_metrics,
)
from app.modules.data_query.infrastructure.catalog._tercero_fields import (
    contact_dimensions,
    contact_fields,
    municipality_sql,
)

_PROVEEDOR_NAME = tercero_display_name()
_PROVEEDOR_SEARCH = tercero_search_text()

# Documentos de devolución en compra (13). Sin tipo (base de demo) cuentan
# como factura.
PURCHASE_RETURN_TYPES = "(13)"
NOT_A_PURCHASE_RETURN = (
    'fc."idDocumento" NOT IN (SELECT doc."idDocumento" FROM "General"."Documento" doc '
    f'WHERE doc."tipo" IN {PURCHASE_RETURN_TYPES})'
)

_DATE = (FilterOp.BETWEEN, FilterOp.GTE, FilterOp.LTE, FilterOp.EQ)

_TERCERO_JOIN = JoinDef(
    "tercero",
    'JOIN "Tercero"."Tercero" t ON t."idTercero" = fc."idTercero"',
)


# ── Entidad: compras (grano factura) ────────────────────────────────────
COMPRAS = SemanticEntity(
    name="compras",
    base_table='"CuentaPagar"."FacturaCompra" fc',
    base_filters=('fc."anulada" = false', NOT_A_PURCHASE_RETURN),
    required_modules=("CUENTAPAGAR",),
    description=(
        "Facturas de compra a proveedores (cabecera), sin las devoluciones. Úsala "
        "para 'cuánto le compramos al proveedor X', 'cuánto compramos en marzo' y "
        "'principales proveedores'. Las devoluciones en compra están en "
        "'devoluciones_compra': compras netas = compras − devoluciones. El "
        "desglose del IVA por tarifa (base_19, iva_19, base_5, iva_5, base_excluida, "
        "base_exenta, otros_impuestos) y las retenciones por tipo (retencion_fuente, "
        "retencion_iva, retencion_ica, retencion_otras; 'retenciones' es el total) se "
        "piden por nombre en 'campos', o como métrica con sufijo _total. Para lo "
        "que se le DEBE a un proveedor usa 'cartera'. Para detalle por PRODUCTO usa "
        "'compras_detalle'."
    ),
    joins={
        "tercero": _TERCERO_JOIN,
        "iva": iva_join('fc."idFacturaCompra"'),
        "ret": retenciones_join('fc."idFacturaCompra"'),
    },
    metrics={
        "monto_total": MetricDef("monto_total", 'SUM(fc."total")', "Total comprado"),
        "num_facturas": MetricDef("num_facturas", "COUNT(*)", "Cantidad de facturas de compra"),
        "subtotal_total": MetricDef("subtotal_total", 'SUM(fc."subtotal")', "Subtotal"),
        "iva_total": MetricDef("iva_total", 'SUM(fc."valorIva")', "IVA de las compras"),
        **iva_metrics(),
        "retenciones_total": MetricDef(
            "retenciones_total",
            'SUM(COALESCE(fc."valorImpuestosRetencion", 0))',
            "Retenciones de las compras",
        ),
        **retenciones_metrics(),
    },
    dimensions={
        **contact_dimensions(requires=("tercero",)),
        "dia": DimensionDef("dia", "DATE_TRUNC('day', fc.\"fecha\")", "Día"),
        "mes": DimensionDef("mes", "DATE_TRUNC('month', fc.\"fecha\")", "Mes"),
        "anio": DimensionDef("anio", "DATE_TRUNC('year', fc.\"fecha\")", "Año"),
        "proveedor": DimensionDef("proveedor", _PROVEEDOR_NAME, "Proveedor", requires=("tercero",)),
    },
    fields={
        **contact_fields(requires=("tercero",)),
        "municipio": FieldDef(
            "municipio", municipality_sql(), "Municipio", requires=("tercero",), default=False
        ),
        "numero": FieldDef("numero", 'fc."numero"', "Número"),
        "factura_proveedor": FieldDef(
            "factura_proveedor", 'fc."referenciaFacturaProveedor"', "Factura del proveedor"
        ),
        "fecha": FieldDef("fecha", 'fc."fecha"', "Fecha"),
        "vencimiento": FieldDef("vencimiento", 'fc."fechaVencimiento"', "Vencimiento"),
        "subtotal": FieldDef("subtotal", 'fc."subtotal"', "Subtotal"),
        "iva": FieldDef("iva", 'fc."valorIva"', "IVA"),
        "total": FieldDef("total", 'fc."total"', "Total"),
        "proveedor": FieldDef("proveedor", _PROVEEDOR_NAME, "Proveedor", requires=("tercero",)),
        "proveedor_nombre_completo": FieldDef(
            "proveedor_nombre_completo",
            tercero_full_name(),
            "Proveedor (nombre completo)",
            requires=("tercero",),
            default=False,
        ),
        **iva_fields(),
        "retenciones": FieldDef(
            "retenciones",
            'COALESCE(fc."valorImpuestosRetencion", 0)',
            "Retenciones",
            default=False,
        ),
        **retenciones_fields(),
    },
    filters={
        "fecha": FilterDef("fecha", 'fc."fecha"', _DATE, value_type="date"),
        "proveedor": FilterDef(
            "proveedor", _PROVEEDOR_SEARCH, (FilterOp.CONTAINS,), requires=("tercero",)
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
    base_filters=('fc."anulada" = false', NOT_A_PURCHASE_RETURN),
    required_modules=("CUENTAPAGAR",),
    description=(
        "Líneas de compra (por producto), sin las devoluciones. Úsala para 'cuántas unidades de X "
        "compramos', 'qué productos le compramos al proveedor Y' y costo "
        "unitario de compra. Para totales de factura usa 'compras'."
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
        **contact_dimensions(requires=("tercero",)),
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
            "producto", product_search_text(), (FilterOp.CONTAINS,), requires=("producto",)
        ),
        "producto_id": FilterDef(
            "producto_id", 'df."idProducto"', (FilterOp.EQ, FilterOp.IN), value_type="number"
        ),
        "proveedor": FilterDef(
            "proveedor", _PROVEEDOR_SEARCH, (FilterOp.CONTAINS,), requires=("tercero",)
        ),
        "proveedor_id": FilterDef(
            "proveedor_id", 'fc."idTercero"', (FilterOp.EQ,), value_type="number"
        ),
    },
)
