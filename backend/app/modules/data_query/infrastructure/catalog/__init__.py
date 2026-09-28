"""Registro central del catálogo semántico.

Para agregar una entidad nueva: definila en su módulo y registrala en
`_ENTITIES`. El compilador y la tool MCP la toman automáticamente.
"""

from __future__ import annotations

from collections.abc import Collection

from app.modules.data_query.domain.semantic_model import SemanticEntity
from app.modules.data_query.infrastructure.catalog.cartera import CARTERA
from app.modules.data_query.infrastructure.catalog.compras import COMPRAS, COMPRAS_DETALLE
from app.modules.data_query.infrastructure.catalog.inventario import INVENTARIO
from app.modules.data_query.infrastructure.catalog.terceros import TERCEROS
from app.modules.data_query.infrastructure.catalog.ventas import VENTAS, VENTAS_DETALLE

_ENTITIES: dict[str, SemanticEntity] = {
    VENTAS.name: VENTAS,
    VENTAS_DETALLE.name: VENTAS_DETALLE,
    TERCEROS.name: TERCEROS,
    CARTERA.name: CARTERA,
    INVENTARIO.name: INVENTARIO,
    COMPRAS.name: COMPRAS,
    COMPRAS_DETALLE.name: COMPRAS_DETALLE,
}


def get_entity(name: str) -> SemanticEntity | None:
    return _ENTITIES.get(name)


def list_entities(modules: Collection[str] | None = None) -> list[SemanticEntity]:
    """Las que puede consultar quien tiene `modules` (`None` = todas)."""
    return [entity for entity in _ENTITIES.values() if entity.allowed_for(modules)]


def entity_names() -> list[str]:
    return list(_ENTITIES.keys())
