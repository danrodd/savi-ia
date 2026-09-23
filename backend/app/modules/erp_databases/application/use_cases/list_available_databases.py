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
from app.modules.erp_databases.domain.interfaces import ErpDatabaseRepository


class ListAvailableDatabasesUseCase:
    def __init__(
        self,
        repository: ErpDatabaseRepository,
        access_resolver: ResolveModulesForDatabaseUseCase,
    ) -> None:
        self._repository = repository
        self._access = access_resolver

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

        return [
            AvailableDatabaseDTO(id=d.id, code=d.code, name=d.name)
            for d, access in zip(databases, checks, strict=True)
            if access.has_access
        ]
