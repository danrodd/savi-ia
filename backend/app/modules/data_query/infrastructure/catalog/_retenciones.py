"""Retenciones de un documento de compra, por tipo.

Una fila por factura (o devolución) con lo retenido de cada tipo, a partir de
`CuentaPagar.FacturaIndicadorRetencionCompra`. Se une con un `LEFT JOIN
LATERAL` que devuelve exactamente una fila por documento, así que no infla las
sumas de la cabecera.

Medido el 2026-11-25 en frami, imporllantas, farmacias_similares y sur_andina:
- El tipo sale del código de impuesto de la DIAN del indicador
  (`Inventario.IndicadorRetencion.codigoImpuestoHKA`): 05 ReteIVA, 06
  ReteFuente, 07 ReteICA. La descripción no sirve: "RETEFUENE 10%…", "RET. 2.5%
  COMPRAS", "COMPRAS GENERALES 2.5%". Los flags `nacionalMunicipal` y
  `otraRetencion` tampoco: hay ReteICA marcada como nacional.
- Los indicadores sin código son pocos (6 usos en las cuatro bases), pero
  incluyen ReteFuente de verdad ("RETEFUENTE COMPRAS 1,25% ZOMAC" en frami) y
  ReteICA ("RETEICA CALI 3.3 1000"). Solo para ellos se mira la descripción; lo
  que no se reconoce va a "otras retenciones" (p. ej. autorretenciones).
- La suma de las líneas coincide con `FacturaCompra.valorImpuestosRetencion`
  en todas las facturas no anuladas de las cuatro bases.

Prueba del 2026-11-25: al pedir "agrégale la retención en la fuente" a un
informe de compras, el modelo rehízo todo con SQL libre, gastó el tope de
consultas buscando las tablas y la base del IVA salió mal en el Excel.
"""

from __future__ import annotations

from app.modules.data_query.domain.semantic_model import FieldDef, JoinDef, MetricDef

RETENCIONES_ALIAS = "ret"

# Tipo de cada línea: el código DIAN y, solo sin código, la descripción.
_KIND = """CASE
            WHEN ri."codigoImpuestoHKA" = '06' THEN 'fuente'
            WHEN ri."codigoImpuestoHKA" = '05' THEN 'iva'
            WHEN ri."codigoImpuestoHKA" = '07' THEN 'ica'
            WHEN COALESCE(ri."codigoImpuestoHKA", '') <> '' THEN 'otras'
            WHEN ri."descripcion" ~* '(RETE|RTE)\\s*ICA|\\mICA\\M' THEN 'ica'
            WHEN ri."descripcion" ~* '(RETE|RTE)\\s*IVA|\\mIVA\\M' THEN 'iva'
            WHEN ri."descripcion" ~* 'FUENTE|FUENE' THEN 'fuente'
            ELSE 'otras'
        END"""


def retenciones_join(document_id: str) -> JoinDef:
    """`document_id`: la columna con el `idFacturaCompra` del documento."""
    return JoinDef(
        RETENCIONES_ALIAS,
        f"""LEFT JOIN LATERAL (
    SELECT
        SUM(rr."valorRetencion") FILTER (WHERE k.kind = 'fuente') AS retencion_fuente,
        SUM(rr."valorRetencion") FILTER (WHERE k.kind = 'iva') AS retencion_iva,
        SUM(rr."valorRetencion") FILTER (WHERE k.kind = 'ica') AS retencion_ica,
        SUM(rr."valorRetencion") FILTER (WHERE k.kind = 'otras') AS retencion_otras
    FROM "CuentaPagar"."FacturaIndicadorRetencionCompra" rr
    LEFT JOIN "Inventario"."IndicadorRetencion" ri
        ON ri."idIndicadorRetencion" = rr."idIndicadorRetencion"
    CROSS JOIN LATERAL (SELECT {_KIND} AS kind) k
    WHERE rr."idFacturaCompra" = {document_id}
) {RETENCIONES_ALIAS} ON TRUE""",
    )


_PARTS = (
    ("retencion_fuente", "Retención en la fuente"),
    ("retencion_iva", "ReteIVA"),
    ("retencion_ica", "ReteICA"),
    ("retencion_otras", "Otras retenciones"),
)


def retenciones_fields() -> dict[str, FieldDef]:
    """Columnas por tipo. No entran por defecto: se piden por nombre."""
    return {
        name: FieldDef(
            name,
            f"COALESCE({RETENCIONES_ALIAS}.{name}, 0)",
            label,
            requires=(RETENCIONES_ALIAS,),
            default=False,
        )
        for name, label in _PARTS
    }


def retenciones_metrics() -> dict[str, MetricDef]:
    return {
        f"{name}_total": MetricDef(
            f"{name}_total",
            f"SUM(COALESCE({RETENCIONES_ALIAS}.{name}, 0))",
            label,
            requires=(RETENCIONES_ALIAS,),
        )
        for name, label in _PARTS
    }
