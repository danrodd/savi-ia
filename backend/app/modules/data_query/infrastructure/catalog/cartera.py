"""Entidad de cartera: saldos pendientes por documento.

Tabla `Cartera.FacturaTercero` (ver docs/DB_MAP.md §2.4). Cubre las dos
puntas de la deuda: lo que los clientes le deben a la empresa y lo que la
empresa les debe a sus proveedores.

POR QUÉ ESTA ENTIDAD EXISTE
---------------------------
Antes de modelarla, "¿cuál es nuestra cartera vencida?" se resolvía con
`consultar_libre` y cada proveedor de IA escribía su propio SQL. Medido en
la batería de validación: Gemini respondió $2.211 M (solo clientes) y
OpenAI $10.906 M (todo junto) — ambos "correctos" para su interpretación,
con 5x de diferencia, y sin decirle al usuario cuál habían usado.

Modelarla fija tres cosas:
- El SQL lo escribimos nosotros: misma pregunta, mismo número, siempre.
- Queda disponible para usuarios comunes. `consultar_libre` es solo para
  administradores, así que hasta ahora esta pregunta era incontestable
  para un usuario normal.
- La ambigüedad se vuelve visible: la dimensión `tipo` traduce el entero a
  una etiqueta legible, así la respuesta dice de qué está hablando.

EL MAPEO DE `tipoDocumento`
---------------------------
No es una FK: es un enum de la aplicación. Los valores se dedujeron
cruzando los saldos reales contra `General.Documento`:

| Valor | Documentos que agrupa                                  | Lado      |
|-------|--------------------------------------------------------|-----------|
| 2     | Factura de venta electrónica                           | Cliente   |
| 3     | Factura proveedor, acreedores, ajustes CxP, soporte    | Proveedor |
| 7     | Comprobantes de pago a proveedores                     | Proveedor |
| 9     | Notas de contabilidad, legalización de costos, NC compras | Proveedor |
| 14    | Notas crédito de facturación (CEDIS)                   | Cliente   |
| 15    | Factura proveedor otros acreedores, documento soporte 2 | Proveedor |

OJO CON LAS NOTAS CRÉDITO (tipo 14): tienen `valorSaldo` positivo, pero
conceptualmente REDUCEN lo que el cliente debe. Por eso no se suman a la
cartera de clientes: quedan en su propia categoría, visibles en el
desglose. Si el negocio define que deben restar, se cambia acá y en un
solo lugar — que es precisamente la ventaja de modelarlo.
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

_TERCERO_NAME = (
    'COALESCE(NULLIF(t."nombreComercial", \'\'), t."razonSocial", '
    'NULLIF(TRIM(CONCAT_WS(\' \', t."primerNombre", t."primerApellido")), \'\'))'
)

_DATE_OPS = (FilterOp.BETWEEN, FilterOp.GTE, FilterOp.LTE, FilterOp.EQ)

# Traducción del enum a lenguaje de negocio. Se emite como dimensión para
# que el modelo NO tenga que interpretar el entero — y para que la
# respuesta al usuario diga de qué lado de la deuda está hablando.
_TIPO_LABEL = """CASE ft."tipoDocumento"
        WHEN 2 THEN 'Por cobrar a clientes'
        WHEN 14 THEN 'Notas crédito a clientes'
        WHEN 3 THEN 'Por pagar a proveedores'
        WHEN 7 THEN 'Pagos a proveedores'
        WHEN 9 THEN 'Otros por pagar (contable)'
        WHEN 15 THEN 'Otros por pagar (acreedores)'
        ELSE 'Sin clasificar'
    END"""

# Agrupación gruesa, para responder "cuánto nos deben" contra "cuánto
# debemos" sin que el usuario tenga que conocer los seis tipos.
#
# Las notas crédito (14) van en su PROPIO bucket y no dentro de Clientes:
# tienen saldo positivo pero reducen la deuda del cliente, así que
# sumarlas ahí infla lo por cobrar (~$97 M sobre ~$2.194 M medidos). Que
# aparezcan aparte obliga a mirarlas en vez de esconderlas en un total.
_LADO_LABEL = """CASE
        WHEN ft."tipoDocumento" = 2 THEN 'Por cobrar a clientes'
        WHEN ft."tipoDocumento" = 14 THEN 'Notas crédito a clientes'
        WHEN ft."tipoDocumento" IN (3, 7, 9, 15) THEN 'Por pagar a proveedores'
        ELSE 'Sin clasificar'
    END"""

_VENCIDA = 'ft."fechaVencimientoCuota" < NOW()'


CARTERA = SemanticEntity(
    name="cartera",
    base_table='"Cartera"."FacturaTercero" ft',
    # Cartera = deuda VIVA. Un documento saldado no es cartera, igual que
    # una factura anulada no es una venta.
    base_filters=('ft."valorSaldo" > 0',),
    description=(
        "Saldos pendientes de cobro y de pago. Úsala para 'cartera "
        "vencida', 'cuánto nos deben los clientes', 'cuánto le debemos a "
        "proveedores' y antigüedad de la deuda.\n"
        "REGLA OBLIGATORIA: esta entidad mezcla DOS deudas opuestas — lo "
        "que los clientes deben a la empresa y lo que la empresa debe a "
        "sus proveedores. Un total sin separar suma las dos y NO significa "
        "nada. Siempre: (a) agrupá por la dimensión 'lado', o (b) filtrá "
        "por 'lado' si el usuario pidió una sola punta. Si la pregunta no "
        "aclara cuál quiere, devolvé el desglose por 'lado' y que elija.\n"
        "Para las ventas facturadas usá 'ventas', que es otra cosa."
    ),
    joins={
        "tercero": JoinDef(
            "tercero",
            'JOIN "Tercero"."Tercero" t ON t."idTercero" = ft."idTercero"',
        ),
    },
    metrics={
        "saldo": MetricDef("saldo", 'SUM(ft."valorSaldo")', "Saldo pendiente"),
        "saldo_vencido": MetricDef(
            "saldo_vencido",
            f'SUM(CASE WHEN {_VENCIDA} THEN ft."valorSaldo" ELSE 0 END)',
            "Saldo vencido",
        ),
        "documentos": MetricDef("documentos", "COUNT(*)", "Cantidad de documentos"),
        "valor_original": MetricDef(
            "valor_original", 'SUM(ft."valorDocumento")', "Valor original"
        ),
        "valor_pagado": MetricDef("valor_pagado", 'SUM(ft."valorPagado")', "Valor pagado"),
    },
    dimensions={
        "lado": DimensionDef("lado", _LADO_LABEL, "Clientes o proveedores"),
        "tipo": DimensionDef("tipo", _TIPO_LABEL, "Tipo de documento"),
        "tercero": DimensionDef(
            "tercero", _TERCERO_NAME, "Cliente o proveedor", requires=("tercero",)
        ),
        "mes_vencimiento": DimensionDef(
            "mes_vencimiento",
            "DATE_TRUNC('month', ft.\"fechaVencimientoCuota\")",
            "Mes de vencimiento",
        ),
    },
    fields={
        "numero": FieldDef("numero", 'ft."numero"', "Número"),
        "cuota": FieldDef("cuota", 'ft."cuota"', "Cuota"),
        "fecha_factura": FieldDef("fecha_factura", 'ft."fechaFactura"', "Fecha del documento"),
        "fecha_vencimiento": FieldDef(
            "fecha_vencimiento", 'ft."fechaVencimientoCuota"', "Vencimiento"
        ),
        "saldo": FieldDef("saldo", 'ft."valorSaldo"', "Saldo"),
        "tipo": FieldDef("tipo", _TIPO_LABEL, "Tipo de documento"),
        "tercero": FieldDef(
            "tercero", _TERCERO_NAME, "Cliente o proveedor", requires=("tercero",)
        ),
    },
    filters={
        "fecha_vencimiento": FilterDef(
            "fecha_vencimiento",
            'ft."fechaVencimientoCuota"',
            _DATE_OPS,
            value_type="date",
        ),
        "fecha_factura": FilterDef(
            "fecha_factura", 'ft."fechaFactura"', _DATE_OPS, value_type="date"
        ),
        # Filtrar por `lado` es lo primero que intenta el modelo cuando el
        # usuario pide una sola punta ("cuánto nos deben los clientes").
        # Sin este filtro tenía que conocer los enteros de `tipoDocumento`,
        # y terminaba devolviendo el total mezclado.
        "lado": FilterDef("lado", f"({_LADO_LABEL})", (FilterOp.EQ, FilterOp.CONTAINS)),
        "tipo_documento": FilterDef(
            "tipo_documento",
            'ft."tipoDocumento"',
            (FilterOp.EQ, FilterOp.IN),
            value_type="number",
        ),
        "tercero_id": FilterDef(
            "tercero_id", 'ft."idTercero"', (FilterOp.EQ, FilterOp.IN), value_type="number"
        ),
        "tercero": FilterDef(
            "tercero", _TERCERO_NAME, (FilterOp.CONTAINS,), requires=("tercero",)
        ),
        # `vencida=true` es el filtro que se quiere el 90% de las veces, y
        # ahorra que el modelo tenga que calcular la fecha de hoy.
        "vencida": FilterDef(
            "vencida", f"({_VENCIDA})", (FilterOp.EQ,), value_type="bool"
        ),
    },
    detail_max_rows=30,
)
