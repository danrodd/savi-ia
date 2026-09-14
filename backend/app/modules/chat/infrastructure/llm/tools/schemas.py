"""JSON Schema de los argumentos de cada tool.

Los valores enumerados salen de los tipos del dominio (`QueryMode`,
`FilterOp`, `KNOWLEDGE_TIPOS`), no se copian a mano: si el dominio agrega
un valor, el schema lo refleja solo.

El schema es el contrato que ve el modelo, y los proveedores lo validan
antes de llamar la tool. Por eso tiene que ser completo aunque los
handlers también validen por su cuenta.
"""

from typing import Any

from app.modules.chat.infrastructure.llm.tools.knowledge import KNOWLEDGE_TIPOS
from app.modules.data_query.domain.semantic_query import FilterOp, QueryMode

INFO_EMPRESA_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}}

_FILTER_VALUE: dict[str, Any] = {
    "anyOf": [
        {"type": "string"},
        {"type": "number"},
        {"type": "boolean"},
        {"type": "array", "items": {"anyOf": [{"type": "string"}, {"type": "number"}]}},
    ],
    "description": "Valor a comparar. Lista de dos elementos para 'entre'; lista para 'en'.",
}

CONSULTAR_DATOS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "consulta": {
            "type": "object",
            "properties": {
                "entidad": {"type": "string"},
                "modo": {"type": "string", "enum": [m.value for m in QueryMode]},
                "metricas": {"type": "array", "items": {"type": "string"}},
                "dimensiones": {"type": "array", "items": {"type": "string"}},
                "campos": {"type": "array", "items": {"type": "string"}},
                "filtros": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "campo": {"type": "string"},
                            "op": {"type": "string", "enum": [o.value for o in FilterOp]},
                            "valor": _FILTER_VALUE,
                        },
                        "required": ["campo", "op", "valor"],
                    },
                },
                "orden": {
                    "type": "object",
                    "properties": {
                        "campo": {"type": "string"},
                        "dir": {"type": "string", "enum": ["asc", "desc"]},
                    },
                    "required": ["campo"],
                },
                "limite": {"type": "integer", "minimum": 1},
            },
            "required": ["entidad", "modo"],
        }
    },
    "required": ["consulta"],
}

CONSULTAR_LIBRE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "sql": {"type": "string", "description": "Un único SELECT."},
        "pregunta_usuario": {
            "type": "string",
            "description": "Pregunta original del usuario, para auditoría.",
        },
    },
    "required": ["sql", "pregunta_usuario"],
}

CONSULTAR_CONOCIMIENTO_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "tipo": {"type": "string", "enum": list(KNOWLEDGE_TIPOS)},
        "consulta": {
            "type": "string",
            "description": "Texto de la búsqueda. Vacío para 'modulos_disponibles'.",
        },
    },
    "required": ["tipo", "consulta"],
}
