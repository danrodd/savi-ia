"""Puertos que producen repos de permisos/plan apuntados a una base.

Igual que `UserRepositoryFactory`: con varias bases de clientes no se
puede inyectar un repo ya resuelto, porque cuál usar depende de la base
que se va a consultar, y eso se sabe recién dentro del caso de uso.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from app.modules.auth.domain.interfaces.permission_repository import (
    PermissionRepository,
)
from app.modules.auth.domain.interfaces.seo_plan_repository import SeoPlanRepository


class PermissionRepositoryFactory(ABC):
    @abstractmethod
    async def for_database_id(self, database_id: UUID) -> PermissionRepository: ...


class SeoPlanRepositoryFactory(ABC):
    @abstractmethod
    async def for_database_id(self, database_id: UUID) -> SeoPlanRepository: ...
