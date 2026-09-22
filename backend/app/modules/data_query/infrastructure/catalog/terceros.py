"""Entidad de terceros (clientes y proveedores).

Tabla `Tercero.Tercero`. CONFIDENCIALIDAD (DB_MAP): nunca exponemos
teléfono, celular, email, dirección ni número de identificación. Sólo
nombre, id e indicadores de rol. El `id` se expone para que el agente
pueda encadenar: buscar cliente por nombre → obtener id → consultar
ventas filtrando por ese id.
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

_NAME = (
    'COALESCE(NULLIF(t."nombreComercial", \'\'), t."razonSocial", '
    'NULLIF(TRIM(CONCAT_WS(\' \', t."primerNombre", t."primerApellido")), \'\'))'
)


TERCEROS = SemanticEntity(
    name="terceros",
    base_table='"Tercero"."Tercero" t',
    base_filters=(),
    description=(
        "Directorio de clientes y proveedores. Úsala para BUSCAR un cliente "
        "por nombre (modo detalle, filtro 'nombre' contiene) y obtener su "
        "id, o para contar terceros por tipo. Nunca expone datos de contacto."
    ),
    metrics={
        "cantidad": MetricDef("cantidad", "COUNT(*)", "Cantidad de terceros"),
    },
    dimensions={
        "es_cliente": DimensionDef("es_cliente", 't."cliente"', "Es cliente"),
        "es_proveedor": DimensionDef("es_proveedor", 't."proveedor"', "Es proveedor"),
    },
    fields={
        "id": FieldDef("id", 't."idTercero"', "ID"),
        "nombre": FieldDef("nombre", _NAME, "Nombre"),
        "es_cliente": FieldDef("es_cliente", 't."cliente"', "Es cliente"),
        "es_proveedor": FieldDef("es_proveedor", 't."proveedor"', "Es proveedor"),
        "activo": FieldDef("activo", 't."activo"', "Activo"),
    },
    filters={
        "nombre": FilterDef("nombre", _NAME, (FilterOp.CONTAINS,)),
        "id": FilterDef("id", 't."idTercero"', (FilterOp.EQ,), value_type="number"),
        "es_cliente": FilterDef(
            "es_cliente", 't."cliente"', (FilterOp.EQ,), value_type="bool"
        ),
        "es_proveedor": FilterDef(
            "es_proveedor", 't."proveedor"', (FilterOp.EQ,), value_type="bool"
        ),
        "activo": FilterDef("activo", 't."activo"', (FilterOp.EQ,), value_type="bool"),
    },
    record_key="id",
)
