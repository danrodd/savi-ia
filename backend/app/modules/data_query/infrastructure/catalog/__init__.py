"""Registro central del catálogo semántico.

Para agregar una entidad nueva: definila en su módulo y registrala en
`_ENTITIES`. El compilador y la tool MCP la toman automáticamente.
"""
from __future__ import annotations

from app.modules.data_query.domain.semantic_model import SemanticEntity
from app.modules.data_query.infrastructure.catalog.terceros import TERCEROS
from app.modules.data_query.infrastructure.catalog.ventas import VENTAS, VENTAS_DETALLE

_ENTITIES: dict[str, SemanticEntity] = {
    VENTAS.name: VENTAS,
    VENTAS_DETALLE.name: VENTAS_DETALLE,
    TERCEROS.name: TERCEROS,
}


def get_entity(name: str) -> SemanticEntity | None:
    return _ENTITIES.get(name)


def list_entities() -> list[SemanticEntity]:
    return list(_ENTITIES.values())


def entity_names() -> list[str]:
    return list(_ENTITIES.keys())
