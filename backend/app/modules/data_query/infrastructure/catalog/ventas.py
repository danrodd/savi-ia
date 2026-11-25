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

Las devoluciones en venta (documento de tipo 14: DV, DVE) se guardan en la
misma tabla, con total POSITIVO. Hasta el 2026-11-25 se sumaban como ventas
(imporllantas: 294 M de más; frami: 1.297 M). Ahora quedan afuera y tienen su
propia entidad, `devoluciones_venta`.
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
from app.modules.data_query.infrastructure.catalog._names import (
    product_search_text,
    tercero_display_name,
    tercero_full_name,
    tercero_search_text,
)
from app.modules.data_query.infrastructure.catalog._tercero_fields import (
    contact_dimensions,
    contact_fields,
    municipality_sql,
)

_CLIENTE_NAME = tercero_display_name()
# El vendedor es el empleado que figura en la factura: otro tercero, con su
# propio alias para no chocar con el del cliente.
_VENDEDOR_NAME = tercero_display_name("v")
_VENDEDOR_JOIN = JoinDef(
    "vendedor",
    'LEFT JOIN "Tercero"."Tercero" v ON v."idTercero" = f."idTerceroEmpleado"',
)

_DATE = (FilterOp.BETWEEN, FilterOp.GTE, FilterOp.LTE, FilterOp.EQ)

# Documentos de devolución en venta (14). Sin tipo (base de demo) cuentan
# como factura.
SALES_RETURN_TYPES = "(14)"
NOT_A_SALES_RETURN = (
    'f."idDocumento" NOT IN (SELECT doc."idDocumento" FROM "General"."Documento" doc '
    f'WHERE doc."tipo" IN {SALES_RETURN_TYPES})'
)
_CLIENTE_SEARCH = tercero_search_text()
_VENDEDOR_SEARCH = tercero_search_text("v")


# ── Entidad: ventas (grano factura) ─────────────────────────────────────
VENTAS = SemanticEntity(
    name="ventas",
    base_table='"CuentaCobrar"."Factura" f',
    base_filters=('f."anulada" = false', NOT_A_SALES_RETURN),
    description=(
        "Facturas de venta (cabecera), sin las devoluciones. Úsala para totales facturados, "
        "número de facturas, ticket promedio, IVA y descuentos, agrupados "
        "por periodo, por cliente o por vendedor. Para detalle por PRODUCTO "
        "usa 'ventas_detalle'. Las devoluciones en venta están en "
        "'devoluciones_venta': ventas netas = ventas − devoluciones."
    ),
    joins={
        "tercero": JoinDef(
            "tercero",
            'JOIN "Tercero"."Tercero" t ON t."idTercero" = f."idTercero"',
        ),
        "vendedor": _VENDEDOR_JOIN,
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
        **contact_dimensions(requires=("tercero",)),
        "dia": DimensionDef("dia", "DATE_TRUNC('day', f.\"fecha\")", "Día"),
        "mes": DimensionDef("mes", "DATE_TRUNC('month', f.\"fecha\")", "Mes"),
        "anio": DimensionDef("anio", "DATE_TRUNC('year', f.\"fecha\")", "Año"),
        "cliente": DimensionDef("cliente", _CLIENTE_NAME, "Cliente", requires=("tercero",)),
        "vendedor": DimensionDef("vendedor", _VENDEDOR_NAME, "Vendedor", requires=("vendedor",)),
    },
    fields={
        **contact_fields(requires=("tercero",)),
        "municipio": FieldDef(
            "municipio", municipality_sql(), "Municipio", requires=("tercero",), default=False
        ),
        "numero": FieldDef("numero", 'f."numero"', "Número"),
        "fecha": FieldDef("fecha", 'f."fecha"', "Fecha"),
        "total": FieldDef("total", 'f."total"', "Total"),
        "subtotal": FieldDef("subtotal", 'f."subtotal"', "Subtotal"),
        "iva": FieldDef("iva", 'f."valorImpuestoIva"', "IVA"),
        "descuento": FieldDef("descuento", 'f."descuento"', "Descuento"),
        "cliente": FieldDef("cliente", _CLIENTE_NAME, "Cliente", requires=("tercero",)),
        "cliente_nombre_completo": FieldDef(
            "cliente_nombre_completo",
            tercero_full_name(),
            "Cliente (nombre completo)",
            requires=("tercero",),
            default=False,
        ),
        "vendedor": FieldDef("vendedor", _VENDEDOR_NAME, "Vendedor", requires=("vendedor",)),
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
        "cliente": FilterDef(
            "cliente", _CLIENTE_SEARCH, (FilterOp.CONTAINS,), requires=("tercero",)
        ),
        # "Cuánto vendió Mateo" por el nombre del vendedor.
        "vendedor": FilterDef(
            "vendedor", _VENDEDOR_SEARCH, (FilterOp.CONTAINS,), requires=("vendedor",)
        ),
        "numero": FilterDef("numero", 'f."numero"', (FilterOp.EQ,), value_type="number"),
    },
    record_key="numero",
)


# ── Entidad: ventas_detalle (grano línea) ───────────────────────────────
VENTAS_DETALLE = SemanticEntity(
    name="ventas_detalle",
    base_table='"CuentaCobrar"."Factura" f',
    base_filters=('f."anulada" = false', NOT_A_SALES_RETURN),
    description=(
        "Líneas de venta (por producto). Úsala para unidades vendidas, "
        "ingresos y costo por producto, por sucursal o por vendedor. Para "
        "totales de factura usa 'ventas'."
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
        "vendedor": _VENDEDOR_JOIN,
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
        **contact_dimensions(requires=("tercero",)),
        "producto": DimensionDef(
            "producto", 'p."descripcion"', "Producto", requires=("detalle", "producto")
        ),
        "sucursal": DimensionDef(
            "sucursal", 'a."descripcion"', "Sucursal", requires=("detalle", "almacen")
        ),
        "mes": DimensionDef("mes", "DATE_TRUNC('month', f.\"fecha\")", "Mes"),
        "cliente": DimensionDef("cliente", _CLIENTE_NAME, "Cliente", requires=("tercero",)),
        "vendedor": DimensionDef("vendedor", _VENDEDOR_NAME, "Vendedor", requires=("vendedor",)),
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
            product_search_text(),
            (FilterOp.CONTAINS,),
            requires=("detalle", "producto"),
        ),
        "cliente_id": FilterDef("cliente_id", 'f."idTercero"', (FilterOp.EQ,), value_type="number"),
        "cliente": FilterDef(
            "cliente", _CLIENTE_SEARCH, (FilterOp.CONTAINS,), requires=("tercero",)
        ),
        # "Cuánto vendió Mateo" por el nombre del vendedor.
        "vendedor": FilterDef(
            "vendedor", _VENDEDOR_SEARCH, (FilterOp.CONTAINS,), requires=("vendedor",)
        ),
    },
)
