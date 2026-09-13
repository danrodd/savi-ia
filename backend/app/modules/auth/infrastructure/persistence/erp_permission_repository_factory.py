"""Impls de las factories de permisos/plan sobre el registro de bases.

Traducen "id de base" a un repo apuntado al engine de esa base, vía el
`ErpConnectionProvider`. Es el único punto donde `auth` sabe cómo se
resuelve un engine desde un id de base.
"""
from __future__ import annotations

from uuid import UUID

from app.modules.auth.domain.interfaces import (
    PermissionRepository,
    PermissionRepositoryFactory,
    SeoPlanRepository,
    SeoPlanRepositoryFactory,
)
from app.modules.auth.infrastructure.persistence.erp_permission_repository import (
    ErpPermissionRepository,
)
from app.modules.auth.infrastructure.persistence.erp_seo_plan_repository import (
    ErpSeoPlanRepository,
)
from app.modules.erp_databases.infrastructure import ErpConnectionProvider


class ErpPermissionRepositoryFactory(PermissionRepositoryFactory):
    def __init__(self, connections: ErpConnectionProvider) -> None:
        self._connections = connections

    async def for_database_id(self, database_id: UUID) -> PermissionRepository:
        return ErpPermissionRepository(await self._connections.engine_for(database_id))


class ErpSeoPlanRepositoryFactory(SeoPlanRepositoryFactory):
    def __init__(self, connections: ErpConnectionProvider) -> None:
        self._connections = connections

    async def for_database_id(self, database_id: UUID) -> SeoPlanRepository:
        return ErpSeoPlanRepository(await self._connections.engine_for(database_id))
