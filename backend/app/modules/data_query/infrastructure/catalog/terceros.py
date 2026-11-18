"""Entidad de terceros (clientes y proveedores).

Tabla `Tercero.Tercero`. Los datos de contacto y las cuentas bancarias
dependen del permiso del usuario en el ERP (ver `_tercero_fields.py` y
`docs/plataforma/10-datos-por-permiso.md`). El `id` se expone para que el
agente pueda encadenar: buscar cliente por nombre → obtener id → consultar
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
from app.modules.data_query.infrastructure.catalog._names import tercero_display_name
from app.modules.data_query.infrastructure.catalog._tercero_fields import (
    tercero_detail_dimensions,
    tercero_detail_fields,
    tercero_detail_filters,
)

_NAME = tercero_display_name()


TERCEROS = SemanticEntity(
    name="terceros",
    base_table='"Tercero"."Tercero" t',
    base_filters=(),
    description=(
        "Directorio de clientes y proveedores. Úsala para BUSCAR un cliente "
        "por nombre (modo detalle, filtro 'nombre' contiene) y obtener su "
        "id, o para contar terceros por tipo, municipio o vendedor. Los campos de "
        "contacto (identificación, teléfono, celular, correo, dirección) y las cuentas "
        "bancarias se piden por nombre en 'campos'; si no aparecen en la lista de "
        "campos, el usuario no tiene permiso para verlos. "
        "'activo' y 'bloqueado' son estados INDEPENDIENTES del ERP: un tercero "
        "puede estar activo y bloqueado a la vez. Para 'bloqueados' filtra "
        "bloqueado=true (nunca activo=false); para 'inactivos', activo=false."
    ),
    metrics={
        "cantidad": MetricDef("cantidad", "COUNT(*)", "Cantidad de terceros"),
    },
    dimensions={
        "es_cliente": DimensionDef("es_cliente", 't."cliente"', "Es cliente"),
        "es_proveedor": DimensionDef("es_proveedor", 't."proveedor"', "Es proveedor"),
        "activo": DimensionDef("activo", 't."estado"', "Activo"),
        "bloqueado": DimensionDef("bloqueado", 't."bloqueoTercero"', "Bloqueado"),
        **tercero_detail_dimensions(),
    },
    fields={
        "id": FieldDef("id", 't."idTercero"', "ID"),
        "nombre": FieldDef("nombre", _NAME, "Nombre"),
        "es_cliente": FieldDef("es_cliente", 't."cliente"', "Es cliente"),
        "es_proveedor": FieldDef("es_proveedor", 't."proveedor"', "Es proveedor"),
        "activo": FieldDef("activo", 't."estado"', "Activo"),
        # Bloqueo y estado son columnas distintas en el ERP. Sin este campo,
        # "¿qué proveedores están bloqueados?" solo podía responderse con
        # 'activo', y los modelos listaban los inactivos como si fueran los
        # bloqueados (medido: Claude y gpt-6-luna; el único bloqueado real de
        # farmacias, COPHARCOL, está activo).
        "bloqueado": FieldDef("bloqueado", 't."bloqueoTercero"', "Bloqueado"),
        # El ERP guarda vacío como '': NULL se muestra como "sin motivo".
        "motivo_bloqueo": FieldDef(
            "motivo_bloqueo", "NULLIF(TRIM(t.\"motivoBloqueo\"), '')", "Motivo del bloqueo"
        ),
        **tercero_detail_fields(),
    },
    filters={
        "nombre": FilterDef("nombre", _NAME, (FilterOp.CONTAINS,)),
        "id": FilterDef("id", 't."idTercero"', (FilterOp.EQ, FilterOp.IN), value_type="number"),
        "es_cliente": FilterDef("es_cliente", 't."cliente"', (FilterOp.EQ,), value_type="bool"),
        "es_proveedor": FilterDef(
            "es_proveedor", 't."proveedor"', (FilterOp.EQ,), value_type="bool"
        ),
        "activo": FilterDef("activo", 't."estado"', (FilterOp.EQ,), value_type="bool"),
        "bloqueado": FilterDef(
            "bloqueado", 't."bloqueoTercero"', (FilterOp.EQ,), value_type="bool"
        ),
        **tercero_detail_filters(),
    },
    record_key="id",
)
