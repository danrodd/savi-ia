"""Notas de devolución en venta y en compra.

El ERP guarda la devolución como un documento más en la misma tabla de la
factura, con total POSITIVO:

- en venta, `CuentaCobrar.Factura` con documento de tipo 14 (DV, DVE);
- en compra, `CuentaPagar.FacturaCompra` con documento de tipo 13 (DC).

`CuentaCobrar.FacturaDevolucion` y `CuentaPagar.FacturaCompraDevolucion`
enlazan la devolución (`idDevolucion`) con la factura que devuelve
(`idFactura` / `idFacturaCompra`). Una devolución puede enlazar más de una
factura: el número de la factura relacionada se arma con `string_agg` para no
multiplicar filas.

`ventas` y `compras` excluyen estos documentos; las ventas o compras netas son
la entidad menos su devolución.
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
from app.modules.data_query.infrastructure.catalog._iva import iva_fields, iva_join, iva_metrics
from app.modules.data_query.infrastructure.catalog._names import (
    tercero_display_name,
    tercero_full_name,
    tercero_search_text,
)
from app.modules.data_query.infrastructure.catalog._tercero_fields import contact_fields
from app.modules.data_query.infrastructure.catalog.compras import PURCHASE_RETURN_TYPES
from app.modules.data_query.infrastructure.catalog.ventas import SALES_RETURN_TYPES

_DATE = (FilterOp.BETWEEN, FilterOp.GTE, FilterOp.LTE, FilterOp.EQ)
_NAME = tercero_display_name()
_SEARCH = tercero_search_text()


def _document_code(alias: str) -> str:
    return (
        f'(SELECT doc."codigo" FROM "General"."Documento" doc '
        f'WHERE doc."idDocumento" = {alias}."idDocumento")'
    )


# ── Devoluciones en venta ───────────────────────────────────────────────
DEVOLUCIONES_VENTA = SemanticEntity(
    name="devoluciones_venta",
    base_table='"CuentaCobrar"."Factura" f',
    base_filters=(
        'f."anulada" = false',
        'f."idDocumento" IN (SELECT doc."idDocumento" FROM "General"."Documento" doc '
        f'WHERE doc."tipo" IN {SALES_RETURN_TYPES})',
    ),
    description=(
        "Notas de devolución en venta (lo que los clientes devolvieron). Úsala "
        "para 'devoluciones de clientes del mes', 'cuánto nos devolvió el cliente X' "
        "y para calcular ventas netas (ventas − devoluciones_venta). Trae la factura "
        "de venta que se devuelve en 'factura_relacionada'."
    ),
    joins={
        "tercero": JoinDef(
            "tercero",
            'JOIN "Tercero"."Tercero" t ON t."idTercero" = f."idTercero"',
        ),
    },
    metrics={
        "monto_total": MetricDef("monto_total", 'SUM(f."total")', "Total devuelto"),
        "num_devoluciones": MetricDef("num_devoluciones", "COUNT(*)", "Cantidad de devoluciones"),
        "subtotal_total": MetricDef("subtotal_total", 'SUM(f."subtotal")', "Subtotal devuelto"),
        "iva_total": MetricDef("iva_total", 'SUM(f."valorImpuestoIva")', "IVA devuelto"),
    },
    dimensions={
        "dia": DimensionDef("dia", "DATE_TRUNC('day', f.\"fecha\")", "Día"),
        "mes": DimensionDef("mes", "DATE_TRUNC('month', f.\"fecha\")", "Mes"),
        "anio": DimensionDef("anio", "DATE_TRUNC('year', f.\"fecha\")", "Año"),
        "cliente": DimensionDef("cliente", _NAME, "Cliente", requires=("tercero",)),
    },
    fields={
        **contact_fields(requires=("tercero",)),
        "documento": FieldDef("documento", _document_code("f"), "Documento"),
        "numero": FieldDef("numero", 'f."numero"', "Número"),
        "fecha": FieldDef("fecha", 'f."fecha"', "Fecha"),
        "cliente": FieldDef("cliente", _NAME, "Cliente", requires=("tercero",)),
        "cliente_nombre_completo": FieldDef(
            "cliente_nombre_completo",
            tercero_full_name(),
            "Cliente (nombre completo)",
            requires=("tercero",),
            default=False,
        ),
        "factura_relacionada": FieldDef(
            "factura_relacionada",
            '(SELECT string_agg(fo."numero"::text, \', \' ORDER BY fo."numero") '
            'FROM "CuentaCobrar"."FacturaDevolucion" fd '
            'JOIN "CuentaCobrar"."Factura" fo ON fo."idFactura" = fd."idFactura" '
            'WHERE fd."idDevolucion" = f."idFactura")',
            "Factura relacionada",
        ),
        "subtotal": FieldDef("subtotal", 'f."subtotal"', "Subtotal"),
        "iva": FieldDef("iva", 'f."valorImpuestoIva"', "IVA"),
        "total": FieldDef("total", 'f."total"', "Total"),
    },
    filters={
        "fecha": FilterDef("fecha", 'f."fecha"', _DATE, value_type="date"),
        "cliente": FilterDef("cliente", _SEARCH, (FilterOp.CONTAINS,), requires=("tercero",)),
        "cliente_id": FilterDef(
            "cliente_id", 'f."idTercero"', (FilterOp.EQ, FilterOp.IN), value_type="number"
        ),
        "identificacion": FilterDef(
            "identificacion",
            'TRIM(t."numeroIdentificacion")',
            (FilterOp.EQ,),
            requires=("tercero",),
        ),
        "numero": FilterDef("numero", 'f."numero"', (FilterOp.EQ,), value_type="number"),
    },
    record_key="numero",
    detail_max_rows=50,
)


# ── Devoluciones en compra ──────────────────────────────────────────────
DEVOLUCIONES_COMPRA = SemanticEntity(
    name="devoluciones_compra",
    base_table='"CuentaPagar"."FacturaCompra" fc',
    base_filters=(
        'fc."anulada" = false',
        'fc."idDocumento" IN (SELECT doc."idDocumento" FROM "General"."Documento" doc '
        f'WHERE doc."tipo" IN {PURCHASE_RETURN_TYPES})',
    ),
    required_modules=("CUENTAPAGAR",),
    description=(
        "Notas de devolución en compra (lo que se le devolvió a los proveedores). "
        "Úsala para 'devoluciones a proveedores del mes' y para compras netas "
        "(compras − devoluciones_compra). Trae la factura de compra que se devuelve "
        "en 'factura_relacionada' y el mismo desglose del IVA por tarifa que "
        "'compras' (base_19, iva_19, base_5, iva_5, base_excluida, base_exenta), "
        "que se pide por nombre en 'campos'."
    ),
    joins={
        "tercero": JoinDef(
            "tercero",
            'JOIN "Tercero"."Tercero" t ON t."idTercero" = fc."idTercero"',
        ),
        "iva": iva_join('fc."idFacturaCompra"'),
    },
    metrics={
        "monto_total": MetricDef("monto_total", 'SUM(fc."total")', "Total devuelto"),
        "num_devoluciones": MetricDef("num_devoluciones", "COUNT(*)", "Cantidad de devoluciones"),
        "subtotal_total": MetricDef("subtotal_total", 'SUM(fc."subtotal")', "Subtotal devuelto"),
        "iva_total": MetricDef("iva_total", 'SUM(fc."valorIva")', "IVA devuelto"),
        **iva_metrics(),
    },
    dimensions={
        "dia": DimensionDef("dia", "DATE_TRUNC('day', fc.\"fecha\")", "Día"),
        "mes": DimensionDef("mes", "DATE_TRUNC('month', fc.\"fecha\")", "Mes"),
        "anio": DimensionDef("anio", "DATE_TRUNC('year', fc.\"fecha\")", "Año"),
        "proveedor": DimensionDef("proveedor", _NAME, "Proveedor", requires=("tercero",)),
    },
    fields={
        **contact_fields(requires=("tercero",)),
        "documento": FieldDef("documento", _document_code("fc"), "Documento"),
        "numero": FieldDef("numero", 'fc."numero"', "Número"),
        "fecha": FieldDef("fecha", 'fc."fecha"', "Fecha"),
        "proveedor": FieldDef("proveedor", _NAME, "Proveedor", requires=("tercero",)),
        "proveedor_nombre_completo": FieldDef(
            "proveedor_nombre_completo",
            tercero_full_name(),
            "Proveedor (nombre completo)",
            requires=("tercero",),
            default=False,
        ),
        "factura_relacionada": FieldDef(
            "factura_relacionada",
            '(SELECT string_agg(fo."numero"::text, \', \' ORDER BY fo."numero") '
            'FROM "CuentaPagar"."FacturaCompraDevolucion" fd '
            'JOIN "CuentaPagar"."FacturaCompra" fo ON fo."idFacturaCompra" = fd."idFacturaCompra" '
            'WHERE fd."idDevolucion" = fc."idFacturaCompra")',
            "Factura de compra relacionada",
        ),
        "subtotal": FieldDef("subtotal", 'fc."subtotal"', "Subtotal"),
        "iva": FieldDef("iva", 'fc."valorIva"', "IVA"),
        "total": FieldDef("total", 'fc."total"', "Total"),
        **iva_fields(),
    },
    filters={
        "fecha": FilterDef("fecha", 'fc."fecha"', _DATE, value_type="date"),
        "proveedor": FilterDef("proveedor", _SEARCH, (FilterOp.CONTAINS,), requires=("tercero",)),
        "proveedor_id": FilterDef(
            "proveedor_id", 'fc."idTercero"', (FilterOp.EQ, FilterOp.IN), value_type="number"
        ),
        "identificacion": FilterDef(
            "identificacion",
            'TRIM(t."numeroIdentificacion")',
            (FilterOp.EQ,),
            requires=("tercero",),
        ),
        "numero": FilterDef("numero", 'fc."numero"', (FilterOp.EQ,), value_type="number"),
    },
    record_key="numero",
    detail_max_rows=50,
)
