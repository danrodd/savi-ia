"""Singleton del catálogo cargado al boot.

Se carga UNA vez con `init_catalog(root)` (en main.py) y se accede vía
`get_catalog()` desde cualquier parte. Si se intenta usar sin inicializar,
falla loud — preferimos crashear que servir respuestas sin knowledge.

El singleton es inmutable: para refrescar hay que reiniciar el backend
(los archivos viajan en el repo y los cambios se aplican por deploy).
"""

from __future__ import annotations

from pathlib import Path

from app.modules.knowledge.domain.interfaces import KnowledgeCatalog
from app.modules.knowledge.infrastructure.static_catalog import load_static_catalog

_catalog: KnowledgeCatalog | None = None


def init_catalog(root: Path) -> KnowledgeCatalog:
    """Carga el catálogo desde el directorio raíz. Idempotente."""
    global _catalog
    _catalog = load_static_catalog(root)
    return _catalog


def get_catalog() -> KnowledgeCatalog:
    if _catalog is None:
        raise RuntimeError("KnowledgeCatalog no inicializado. Llamá a init_catalog() en main.py.")
    return _catalog
