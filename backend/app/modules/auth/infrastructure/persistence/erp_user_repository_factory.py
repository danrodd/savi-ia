"""Impl `UserRepositoryFactory` sobre el registro de bases del ERP.

Traduce "código de cliente" (o id) a un `ErpUserRepository` apuntado al
engine de esa base. Es el único punto donde el módulo `auth` toca el
módulo `erp_databases`.
"""
from __future__ import annotations

from uuid import UUID

from app.modules.auth.domain.interfaces import UserRepository, UserRepositoryFactory
from app.modules.auth.infrastructure.persistence.erp_user_repository import (
    ErpUserRepository,
)
from app.modules.erp_databases.domain.entities import ErpDatabase
from app.modules.erp_databases.domain.exceptions import (
    ErpDatabaseNotFoundError,
    ErpDatabaseUnavailableError,
)
from app.modules.erp_databases.domain.interfaces import ErpDatabaseRepository
from app.modules.erp_databases.domain.value_objects import (
    InvalidDatabaseCodeError,
    normalize_code,
)
from app.modules.erp_databases.infrastructure import ErpConnectionProvider
from app.modules.erp_databases.infrastructure.engine_registry import ErpEngineRegistry


class ErpUserRepositoryFactory(UserRepositoryFactory):
    def __init__(
        self,
        databases: ErpDatabaseRepository,
        registry: ErpEngineRegistry,
        connections: ErpConnectionProvider,
    ) -> None:
        self._databases = databases
        self._registry = registry
        self._connections = connections

    async def for_code(self, code: str | None) -> UserRepository | None:
        if code is None:
            database = await self._databases.get_default()
        else:
            try:
                normalized = normalize_code(code)
            except InvalidDatabaseCodeError:
                # Un código con formato inválido se trata igual que uno
                # inexistente: el login no debe distinguir "no existe" de
                # "está mal escrito".
                return None
            database = await self._databases.get_by_code(normalized)
        return await self._build(database)

    async def for_database_id(self, database_id: UUID) -> UserRepository | None:
        return await self._build(await self._databases.get_by_id(database_id))

    async def _build(self, database: ErpDatabase | None) -> UserRepository | None:
        if database is None or not database.is_usable:
            return None
        try:
            engine = await self._connections.engine_for(database.id)
        except (ErpDatabaseNotFoundError, ErpDatabaseUnavailableError):
            return None
        return ErpUserRepository(engine, erp_database_id=database.id)
