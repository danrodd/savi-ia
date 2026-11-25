"""Desglose del IVA por tarifa de un documento de compra.

Una fila por factura (o devolución) con la base y el IVA de cada tarifa, a
partir de sus líneas (`CuentaPagar.DetalleFacturaCompra`). Se une con un
`LEFT JOIN LATERAL` que devuelve exactamente una fila por documento, así que
no infla las sumas de la cabecera.

Medido el 2026-11-25 en imporllantas, frami y la base de demo:
- La base es el `subtotal` de la línea. `valorGravadoIva` NO sirve como base:
  trae base + IVA, y las líneas al 0 % también se registran ahí.
- Exento y excluido son ambos 0 %; los distingue el indicador de IVA de la línea
  (`Inventario.IndicadorIva.descripcion`: 'EXENTO', 'EXCLUIDO').
- La suma del IVA de las líneas coincide con el `valorIva` de la cabecera.
"""

from __future__ import annotations

from app.modules.data_query.domain.semantic_model import FieldDef, JoinDef, MetricDef

IVA_ALIAS = "iva"


def iva_join(document_id: str) -> JoinDef:
    """`document_id`: la columna con el `idFacturaCompra` del documento."""
    return JoinDef(
        IVA_ALIAS,
        f"""LEFT JOIN LATERAL (
    SELECT
        SUM(dd."subtotal") FILTER (WHERE dd."porcentajeIva" = 19) AS base_19,
        SUM(dd."valorIva") FILTER (WHERE dd."porcentajeIva" = 19) AS iva_19,
        SUM(dd."subtotal") FILTER (WHERE dd."porcentajeIva" = 5) AS base_5,
        SUM(dd."valorIva") FILTER (WHERE dd."porcentajeIva" = 5) AS iva_5,
        SUM(dd."subtotal") FILTER (
            WHERE dd."porcentajeIva" = 0
              AND UPPER(COALESCE(ii."descripcion", '')) LIKE '%EXENT%'
        ) AS base_exenta,
        SUM(dd."subtotal") FILTER (
            WHERE dd."porcentajeIva" = 0
              AND UPPER(COALESCE(ii."descripcion", '')) NOT LIKE '%EXENT%'
        ) AS base_excluida,
        SUM(dd."subtotal") FILTER (WHERE dd."porcentajeIva" NOT IN (0, 5, 19)) AS base_otras,
        SUM(dd."valorIva") FILTER (WHERE dd."porcentajeIva" NOT IN (0, 5, 19)) AS iva_otras,
        SUM(COALESCE(dd."ipoConsumo", 0) + COALESCE(dd."valorImpuestoSaludable", 0))
            AS otros_impuestos
    FROM "CuentaPagar"."DetalleFacturaCompra" dd
    LEFT JOIN "Inventario"."IndicadorIva" ii ON ii."idIndicadorIva" = dd."idIndicadorIva"
    WHERE dd."idFacturaCompra" = {document_id}
) {IVA_ALIAS} ON TRUE""",
    )


_PARTS = (
    ("base_19", "Base gravada 19 %"),
    ("iva_19", "IVA 19 %"),
    ("base_5", "Base gravada 5 %"),
    ("iva_5", "IVA 5 %"),
    ("base_excluida", "Base excluida"),
    ("base_exenta", "Base exenta"),
    ("base_otras", "Base gravada a otras tarifas"),
    ("iva_otras", "IVA a otras tarifas"),
    ("otros_impuestos", "Otros impuestos (consumo, saludables)"),
)


def iva_fields() -> dict[str, FieldDef]:
    """Columnas del desglose. No entran por defecto: se piden por nombre."""
    return {
        name: FieldDef(
            name, f"COALESCE({IVA_ALIAS}.{name}, 0)", label, requires=(IVA_ALIAS,), default=False
        )
        for name, label in _PARTS
    }


def iva_metrics() -> dict[str, MetricDef]:
    return {
        f"{name}_total": MetricDef(
            f"{name}_total", f"SUM(COALESCE({IVA_ALIAS}.{name}, 0))", label, requires=(IVA_ALIAS,)
        )
        for name, label in _PARTS
    }
