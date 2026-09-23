"""Entidades de ventas del modelo semántico.

Basado en la data real de farmacias_similares (ver docs/DB_MAP.md):
las ventas viven en `CuentaCobrar.Factura` + `DetalleFactura`.

Se modelan DOS entidades con granos distintos para evitar el "fan-out"
de joins (que inflaría las sumas):
- `ventas`: grano FACTURA. Montos totales, conteos, ticket. Join a tercero
  es N:1, no infla.
- `ventas_detalle`: grano LÍNEA. Unidades y montos por producto/sucursal.
  El join 1:N a DetalleFactura es necesario y aquí es el grano correcto.

Nombre del cliente: ver `_names.tercero_display_name` — el ERP guarda los
campos vacíos como '' y hay que saltarlos todos.
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

_CLIENTE_NAME = tercero_display_name()

_DATE = (FilterOp.BETWEEN, FilterOp.GTE, FilterOp.LTE, FilterOp.EQ)


# ── Entidad: ventas (grano factura) ─────────────────────────────────────
VENTAS = SemanticEntity(
    name="ventas",
    base_table='"CuentaCobrar"."Factura" f',
    base_filters=('f."anulada" = false',),
    description=(
        "Facturas de venta (cabecera). Úsala para totales facturados, "
        "número de facturas, ticket promedio, IVA y descuentos, agrupados "
        "por periodo o por cliente. Para detalle por PRODUCTO usá "
        "'ventas_detalle'."
    ),
    joins={
        "tercero": JoinDef(
            "tercero",
            'JOIN "Tercero"."Tercero" t ON t."idTercero" = f."idTercero"',
        ),
    },
    metrics={
        "monto_total": MetricDef("monto_total", 'SUM(f."total")', "Total facturado"),
        "num_facturas": MetricDef("num_facturas", "COUNT(*)", "Cantidad de facturas"),
        "ticket_promedio": MetricDef("ticket_promedio", 'AVG(f."total")', "Ticket promedio"),
        "iva_total": MetricDef("iva_total", 'SUM(f."valorImpuestoIva")', "IVA recaudado"),
        "descuento_total": MetricDef(
            "descuento_total", 'SUM(f."descuento")', "Descuentos otorgados"
        ),
        "subtotal_total": MetricDef("subtotal_total", 'SUM(f."subtotal")', "Subtotal"),
    },
    dimensions={
        "dia": DimensionDef("dia", "DATE_TRUNC('day', f.\"fecha\")", "Día"),
        "mes": DimensionDef("mes", "DATE_TRUNC('month', f.\"fecha\")", "Mes"),
        "anio": DimensionDef("anio", "DATE_TRUNC('year', f.\"fecha\")", "Año"),
        "cliente": DimensionDef("cliente", _CLIENTE_NAME, "Cliente", requires=("tercero",)),
    },
    fields={
        "numero": FieldDef("numero", 'f."numero"', "Número"),
        "fecha": FieldDef("fecha", 'f."fecha"', "Fecha"),
        "total": FieldDef("total", 'f."total"', "Total"),
        "subtotal": FieldDef("subtotal", 'f."subtotal"', "Subtotal"),
        "iva": FieldDef("iva", 'f."valorImpuestoIva"', "IVA"),
        "descuento": FieldDef("descuento", 'f."descuento"', "Descuento"),
        "cliente": FieldDef("cliente", _CLIENTE_NAME, "Cliente", requires=("tercero",)),
    },
    filters={
        "fecha": FilterDef("fecha", 'f."fecha"', _DATE, value_type="date"),
        "cliente_id": FilterDef(
            "cliente_id",
            'f."idTercero"',
            (FilterOp.EQ, FilterOp.IN),
            value_type="number",
        ),
        # Por nombre, para "cuánto nos compró X" en una sola consulta. Sin
        # él el modelo tenía que buscar el id en `terceros` y encadenar; si
        # ese primer paso fallaba, contestaba que el cliente no existía.
        "cliente": FilterDef("cliente", _CLIENTE_NAME, (FilterOp.CONTAINS,), requires=("tercero",)),
        "numero": FilterDef("numero", 'f."numero"', (FilterOp.EQ,), value_type="number"),
    },
    record_key="numero",
)


# ── Entidad: ventas_detalle (grano línea) ───────────────────────────────
VENTAS_DETALLE = SemanticEntity(
    name="ventas_detalle",
    base_table='"CuentaCobrar"."Factura" f',
    base_filters=('f."anulada" = false',),
    description=(
        "Líneas de venta (por producto). Úsala para unidades vendidas, "
        "ingresos y costo por producto o por sucursal. Para totales de "
        "factura usá 'ventas'."
    ),
    joins={
        # 'detalle' debe ir primero: 'producto' y 'almacen' dependen de él.
        "detalle": JoinDef(
            "detalle",
            'JOIN "CuentaCobrar"."DetalleFactura" d ON d."idFactura" = f."idFactura"',
        ),
        "producto": JoinDef(
            "producto",
            'JOIN "Inventario"."Producto" p ON p."idProducto" = d."idProducto"',
        ),
        "almacen": JoinDef(
            "almacen",
            'JOIN "Inventario"."Almacen" a ON a."idAlmacen" = d."idAlmacen"',
        ),
        "tercero": JoinDef(
            "tercero",
            'JOIN "Tercero"."Tercero" t ON t."idTercero" = f."idTercero"',
        ),
    },
    metrics={
        "monto_lineas": MetricDef(
            "monto_lineas", 'SUM(d."total")', "Monto de líneas", requires=("detalle",)
        ),
        "unidades": MetricDef(
            "unidades", 'SUM(d."cantidad")', "Unidades vendidas", requires=("detalle",)
        ),
        "costo_total": MetricDef(
            "costo_total",
            'SUM(d."costo" * d."cantidad")',
            "Costo de ventas",
            requires=("detalle",),
        ),
    },
    dimensions={
        "producto": DimensionDef(
            "producto", 'p."descripcion"', "Producto", requires=("detalle", "producto")
        ),
        "sucursal": DimensionDef(
            "sucursal", 'a."descripcion"', "Sucursal", requires=("detalle", "almacen")
        ),
        "mes": DimensionDef("mes", "DATE_TRUNC('month', f.\"fecha\")", "Mes"),
        "cliente": DimensionDef("cliente", _CLIENTE_NAME, "Cliente", requires=("tercero",)),
    },
    fields={},  # entidad analítica: sin modo detalle/registro
    filters={
        "fecha": FilterDef("fecha", 'f."fecha"', _DATE, value_type="date"),
        "producto_id": FilterDef(
            "producto_id",
            'd."idProducto"',
            (FilterOp.EQ, FilterOp.IN),
            requires=("detalle",),
            value_type="number",
        ),
        # Por nombre: "cuánto vendimos de tornillos" abarca muchos productos
        # y no hay un id que lo represente.
        "producto": FilterDef(
            "producto",
            'p."descripcion"',
            (FilterOp.CONTAINS,),
            requires=("detalle", "producto"),
        ),
        "cliente_id": FilterDef("cliente_id", 'f."idTercero"', (FilterOp.EQ,), value_type="number"),
        "cliente": FilterDef("cliente", _CLIENTE_NAME, (FilterOp.CONTAINS,), requires=("tercero",)),
    },
)
