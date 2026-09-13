"""Resolución de "id de base → engine listo para consultar".

Es el reemplazo directo de `get_erp_engine()`: el único lugar del código
que sabe cómo pasar de un `erp_database_id` a una conexión, validando
antes que la base se pueda usar.

Se expone como provider de proceso —igual que el catálogo de knowledge—
porque los consumidores incluyen las tools MCP, que corren dentro de una
clausura del turno y no tienen acceso al grafo de dependencias de
FastAPI.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine

from app.modules.erp_databases.domain.entities import ErpDatabase
from app.modules.erp_databases.domain.exceptions import (
    ErpDatabaseNotFoundError,
    ErpDatabaseUnavailableError,
)
from app.modules.erp_databases.domain.interfaces import ErpDatabaseRepository
from app.modules.erp_databases.infrastructure.engine_registry import (
    ErpEngineRegistry,
)


class ErpConnectionProvider:
    def __init__(
        self,
        repository: ErpDatabaseRepository,
        registry: ErpEngineRegistry,
    ) -> None:
        self._repository = repository
        self._registry = registry

    async def resolve(self, database_id: UUID | None) -> ErpDatabase:
        """Devuelve la base pedida, o la default si `database_id` es None.

        Levanta si no existe o no se puede usar. **No** abre conexión:
        sirve para validar antes de empezar un turno, que es justo lo que
        necesita `POST /chat` para poder devolver un 4xx limpio antes de
        abrir el `StreamingResponse`.
        """
        if database_id is None:
            database = await self._repository.get_default()
            if database is None:
                raise ErpDatabaseNotFoundError(
                    "No hay ninguna base de datos del ERP configurada."
                )
        else:
            database = await self._repository.get_by_id(database_id)
            if database is None:
                raise ErpDatabaseNotFoundError(
                    "La base de datos del ERP indicada no existe."
                )

        _ensure_usable(database)
        return database

    async def engine_for(self, database_id: UUID | None) -> AsyncEngine:
        """Resuelve y devuelve el engine, creándolo si hace falta."""
        database = await self.resolve(database_id)
        return await self._registry.get(database)

    async def invalidate(self, database_id: UUID) -> None:
        await self._registry.invalidate(database_id)


def _ensure_usable(database: ErpDatabase) -> None:
    """Motivos separados a propósito.

    "Está desactivada" y "hay que re-cargar la contraseña" llevan a
    acciones distintas del administrador; un mensaje genérico obligaría a
    adivinar cuál de las dos es.
    """
    if database.is_deleted:
        raise ErpDatabaseUnavailableError(
            str(database.id),
            f"La base de datos '{database.name}' fue eliminada.",
        )
    if not database.is_active:
        raise ErpDatabaseUnavailableError(
            str(database.id),
            f"La base de datos '{database.name}' está desactivada.",
        )
    if database.credentials_unreadable:
        raise ErpDatabaseUnavailableError(
            str(database.id),
            f"Las credenciales de '{database.name}' no se pueden leer. "
            "Un administrador debe volver a ingresar la contraseña.",
        )


# ── Provider de proceso ──────────────────────────────────────────────

_provider: ErpConnectionProvider | None = None


def init_connection_provider(provider: ErpConnectionProvider) -> None:
    global _provider
    _provider = provider


def get_connection_provider() -> ErpConnectionProvider:
    if _provider is None:
        raise RuntimeError(
            "ErpConnectionProvider no inicializado. Llamá a "
            "init_connection_provider() en el arranque."
        )
    return _provider


async def get_erp_engine_for(database_id: UUID | None) -> AsyncEngine:
    """Atajo para los consumidores que solo necesitan el engine.

    Reemplaza a `get_erp_engine()` en las tools MCP y los executors.
    """
    return await get_connection_provider().engine_for(database_id)
