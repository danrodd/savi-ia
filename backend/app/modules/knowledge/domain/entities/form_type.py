"""Tipos de formulario del ERP — coincide con `form_type_catalog` del JSON v2.

Es enum cerrado: si aparece uno nuevo (improbable), se agrega acá
explícitamente. La validación Pydantic atrapa typos en los archivos.
"""

from __future__ import annotations

from enum import StrEnum


class FormType(StrEnum):
    CRUD = "CRUD"
    CONSULTA = "CONSULTA"
    INFORME = "INFORME"
    PROCESO = "PROCESO"
    TRANSACCION = "TRANSACCION"
