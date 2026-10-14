"""Bases del ERP donde el usuario autenticado tiene acceso.

Alimenta el selector del chat. Aplica D3: una base está "disponible"
para el usuario cuando está activa **y** el `codigo` del usuario existe y
está activo en ella. No basta con que la base exista.

Devuelve solo `id`, `code` y `name`: para elegir un cliente no hace falta
la topología de conexión, y exponerla a un usuario no admin no aporta
nada.
"""
from __future__ import annotations

import asyncio

from app.modules.auth.application.use_cases.resolve_modules_for_database import (
    ResolveModulesForDatabaseUseCase,
)
from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.erp_databases.application.dtos import AvailableDatabaseDTO
from app.modules.erp_databases.domain.interfaces import (
    DatabaseAccessPolicy,
    ErpDatabaseRepository,
)


class ListAvailableDatabasesUseCase:
    def __init__(
        self,
        repository: ErpDatabaseRepository,
        access_resolver: ResolveModulesForDatabaseUseCase,
        access_policy: DatabaseAccessPolicy | None = None,
    ) -> None:
        self._repository = repository
        self._access = access_resolver
        self._policy = access_policy

    async def execute(
        self, login: str, *, identity: AuthenticatedUser | None = None
    ) -> list[AvailableDatabaseDTO]:
        databases = await self._repository.list_all(include_inactive=False)

        # Se chequea el acceso a todas las bases en paralelo: cada una es
        # una consulta a un ERP distinto y hacerlas en serie escalaría mal
        # con muchos clientes registrados.
        checks = await asyncio.gather(
            *(self._access.execute(login, d.id, identity=identity) for d in databases)
        )

        # Además del ERP, SEO Group puede haber acotado las bases de esta persona (Cloud).
        assigned = (
            await self._policy.allowed_databases(
                user_id=identity.id, identity_database_id=identity.erp_database_id
            )
            if (
                self._policy is not None
                and identity is not None
                and identity.erp_database_id is not None
            )
            else None
        )

        return [
            AvailableDatabaseDTO(id=d.id, code=d.code, name=d.name)
            for d, access in zip(databases, checks, strict=True)
            if access.has_access and (assigned is None or d.id in assigned)
        ]
