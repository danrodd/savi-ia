"""Anticipos de clientes y a proveedores.

Tabla `Contabilidad.Anticipo`: cada fila trae su valor, lo cruzado contra
facturas y el saldo pendiente (`valorAnticipo`, `valorCruce`,
`saldoAnticipo`). Los cruces viven en `Cartera.CruceAnticipoCliente` y
`CruceAnticipoProveedor`; no hace falta leerlos para el saldo.

De quién es el anticipo lo dice `General.Documento.tipo`, no el código del
documento: los códigos cambian por cliente (imporllantas usa AC/AP; frami,
AC, ACC, AP, DACC y DAP). Medido el 2026-11-25 en ambas bases:

- 17 = anticipo de cliente
- 18 = anticipo a proveedor
- 46 = devolución de anticipo de cliente
- 47 = devolución de anticipo a proveedor

Antes de esta entidad, preguntar por los anticipos de un tercero hacía que el
modelo revisara cartera, no los encontrara y respondiera que no había nada
(reporte de soporte del 2026-11-24).
"""

from __future__ import annotations

from app.modules.data_query.domain.semantic_model import (
    DimensionDef,
    FieldDef,
    FilterDef,
    JoinDef,
    MetricDef,
    RowScope,
    SemanticEntity,
)
from app.modules.data_query.domain.semantic_query import FilterOp
from app.modules.data_query.infrastructure.catalog._names import (
    tercero_full_name,
    tercero_search_text,
)
from app.modules.data_query.infrastructure.catalog._tercero_fields import contact_fields

_DATE = (FilterOp.BETWEEN, FilterOp.GTE, FilterOp.LTE, FilterOp.EQ)

_TIPO = (
    '(SELECT doc."tipo" FROM "General"."Documento" doc WHERE doc."idDocumento" = an."idDocumento")'
)

_TIPO_LABEL = f"""CASE {_TIPO}
        WHEN 17 THEN 'Anticipo de cliente'
        WHEN 18 THEN 'Anticipo a proveedor'
        WHEN 46 THEN 'Devolución de anticipo de cliente'
        WHEN 47 THEN 'Devolución de anticipo a proveedor'
        ELSE 'Otro'
    END"""

# Clave del filtro `tipo`: palabras que no se contienen entre sí.
_TIPO_KEY = f"""CASE {_TIPO}
        WHEN 17 THEN 'cliente'
        WHEN 18 THEN 'proveedor'
        WHEN 46 THEN 'devolucion cliente'
        WHEN 47 THEN 'devolucion proveedor'
        ELSE 'otro'
    END"""

_NAME = tercero_full_name()

ANTICIPOS = SemanticEntity(
    name="anticipos",
    base_table='"Contabilidad"."Anticipo" an',
    base_filters=('an."anulado" = false',),
    # Los de clientes con Cuentas por Cobrar, Ventas o Contabilidad; los de
    # proveedores, con Cuentas por Pagar o Contabilidad (como cartera).
    row_scopes=(
        RowScope(
            f"{_TIPO} IN (17, 46)",
            ("CUENTACOBRAR", "VENTA", "CONTABILIDAD"),
            "los anticipos de clientes",
        ),
        RowScope(
            f"{_TIPO} IN (18, 47)",
            ("CUENTAPAGAR", "CONTABILIDAD"),
            "los anticipos a proveedores",
        ),
    ),
    description=(
        "Anticipos de clientes y a proveedores (módulo de Contabilidad): dinero "
        "recibido o entregado antes de facturar. Cada anticipo trae su valor, lo "
        "cruzado contra facturas y el saldo pendiente de cruzar. Úsala para "
        "'¿el tercero X tiene anticipos?', 'anticipos pendientes sin cruzar' "
        "(filtro pendiente=true) y totales por tercero o por mes. Filtra por "
        "'identificacion' (NIT o cédula, sin dígito de verificación) o por "
        "'tercero' (nombre). Los anticipos NO aparecen en 'cartera': que un "
        "tercero no tenga cartera no dice nada de sus anticipos."
    ),
    joins={
        "tercero": JoinDef(
            "tercero",
            'JOIN "Tercero"."Tercero" t ON t."idTercero" = an."idTercero"',
        ),
    },
    metrics={
        "valor_total": MetricDef(
            "valor_total", 'SUM(an."valorAnticipo")', "Valor de los anticipos"
        ),
        "cruzado_total": MetricDef("cruzado_total", 'SUM(an."valorCruce")', "Valor cruzado"),
        "saldo_pendiente": MetricDef(
            "saldo_pendiente", 'SUM(an."saldoAnticipo")', "Saldo pendiente de cruzar"
        ),
        "num_anticipos": MetricDef("num_anticipos", "COUNT(*)", "Cantidad de anticipos"),
    },
    dimensions={
        "tipo": DimensionDef("tipo", _TIPO_LABEL, "Tipo de anticipo"),
        "tercero": DimensionDef("tercero", _NAME, "Tercero", requires=("tercero",)),
        "mes": DimensionDef("mes", "DATE_TRUNC('month', an.\"fecha\")", "Mes"),
        "anio": DimensionDef("anio", "DATE_TRUNC('year', an.\"fecha\")", "Año"),
    },
    fields={
        **contact_fields(requires=("tercero",)),
        "tipo": FieldDef("tipo", _TIPO_LABEL, "Tipo"),
        "documento": FieldDef(
            "documento",
            '(SELECT doc."codigo" FROM "General"."Documento" doc '
            'WHERE doc."idDocumento" = an."idDocumento")',
            "Documento",
        ),
        "numero": FieldDef("numero", 'an."numero"', "Número"),
        "fecha": FieldDef("fecha", 'an."fecha"', "Fecha"),
        "tercero": FieldDef("tercero", _NAME, "Tercero", requires=("tercero",)),
        "valor": FieldDef("valor", 'an."valorAnticipo"', "Valor del anticipo"),
        "cruzado": FieldDef("cruzado", 'an."valorCruce"', "Valor cruzado"),
        "saldo": FieldDef("saldo", 'an."saldoAnticipo"', "Saldo pendiente"),
        "detalle": FieldDef("detalle", "NULLIF(TRIM(an.\"detalle\"), '')", "Detalle"),
    },
    filters={
        "tipo": FilterDef("tipo", _TIPO_KEY, (FilterOp.CONTAINS,)),
        "fecha": FilterDef("fecha", 'an."fecha"', _DATE, value_type="date"),
        "tercero": FilterDef(
            "tercero", tercero_search_text(), (FilterOp.CONTAINS,), requires=("tercero",)
        ),
        "tercero_id": FilterDef(
            "tercero_id", 'an."idTercero"', (FilterOp.EQ, FilterOp.IN), value_type="number"
        ),
        # Buscar por NIT no lo muestra: se puede filtrar sin permiso de contacto.
        "identificacion": FilterDef(
            "identificacion",
            'TRIM(t."numeroIdentificacion")',
            (FilterOp.EQ,),
            requires=("tercero",),
        ),
        "pendiente": FilterDef(
            "pendiente", '(an."saldoAnticipo" > 0)', (FilterOp.EQ,), value_type="bool"
        ),
        "numero": FilterDef("numero", 'an."numero"', (FilterOp.EQ,), value_type="number"),
    },
    detail_max_rows=50,
)
