"""Resuelve los módulos de un usuario **en una base del ERP concreta** (D3).

Es la pieza que impide la escalada de privilegios entre clientes. El
`idUsuario` no sirve entre bases, así que el usuario se busca por su
`codigo` (login, estable porque el esquema es el mismo) en la base que se
va a consultar, y los permisos se leen de ESA base.

Si el `codigo` no existe en la base, o existe pero está inactivo, el
usuario **no tiene acceso** a esa base: no se hereda ni el `is_admin` ni
los módulos de la base donde se autenticó.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.modules.auth.application.use_cases.resolve_user_modules import (
    ResolveUserModulesUseCase,
)
from app.modules.auth.domain.interfaces import (
    PermissionRepositoryFactory,
    SeoPlanRepositoryFactory,
    UserRepositoryFactory,
)
from app.modules.auth.domain.value_objects import ModuleCode


@dataclass(frozen=True, slots=True)
class DatabaseAccess:
    """Resultado de resolver el acceso de un usuario a una base.

    `has_access=False` cuando el usuario no existe o está inactivo en esa
    base. En ese caso `modules` está vacío y `user_id_in_database` es
    `None`: no hay identidad que resolver ahí.
    """

    has_access: bool
    modules: frozenset[ModuleCode]
    user_id_in_database: int | None = None
    is_admin_in_database: bool = False
    # Hash de los módulos, para que el frontend detecte cambios sin traerse
    # el bootstrap entero. Vacío cuando no hay acceso: no hay nada que versionar.
    version: str = ""


class ResolveModulesForDatabaseUseCase:
    def __init__(
        self,
        user_repository_factory: UserRepositoryFactory,
        permission_repo_factory: PermissionRepositoryFactory,
        seo_plan_repo_factory: SeoPlanRepositoryFactory,
    ) -> None:
        self._users = user_repository_factory
        self._permissions = permission_repo_factory
        self._plans = seo_plan_repo_factory

    async def execute(self, login: str, database_id: UUID) -> DatabaseAccess:
        repository = await self._users.for_database_id(database_id)
        if repository is None:
            # La base no existe o no se puede usar: sin acceso, sin filtrar
            # nada. El caller decide si es 404 o 409.
            return DatabaseAccess(has_access=False, modules=frozenset())

        found = await repository.find_by_login(login.strip().upper())
        if found is None or not found.user.is_active:
            # El codigo no existe en esta base, o está inactivo: sin acceso.
            # NO se heredan permisos de la base de identidad.
            return DatabaseAccess(has_access=False, modules=frozenset())

        # Con la identidad de ESTA base (su idUsuario, su is_admin),
        # resolvemos los módulos contra los permisos de ESTA base.
        permissions = await self._permissions.for_database_id(database_id)
        plans = await self._plans.for_database_id(database_id)
        resolver = ResolveUserModulesUseCase(permissions, plans)
        resolution = await resolver.execute(
            found.user.id, is_admin=found.user.is_admin
        )

        return DatabaseAccess(
            has_access=True,
            modules=resolution.modules,
            user_id_in_database=found.user.id,
            is_admin_in_database=found.user.is_admin,
            version=resolution.version,
        )
